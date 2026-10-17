"""Lua scripts for OpenMW: written in the Workshop, kept in the project, put into the game as files
next to the mod with a .omwscripts list (see Project.lua_outputs). Each script runs as one kind
(global, on the player, on every NPC, ...) or on the particular objects you choose."""
import re

import lua_check
from editing import EditError, commit, _require_project

KINDS = [
    ('CUSTOM', 'Only the objects I choose', 'Runs on the particular NPCs, creatures or objects you list below.'),
    ('GLOBAL', 'Global', 'Runs once for the whole game: the world, quests, giving and moving things.'),
    ('PLAYER', 'Player', 'Runs on the player: messages on screen, keys, the camera, quest updates.'),
    ('NPC', 'Every NPC', 'A copy runs on each NPC while they are near the player.'),
    ('CREATURE', 'Every creature', 'A copy runs on each creature while it is near the player.'),
    ('ACTIVATOR', 'Every activator', 'Runs on activators (levers, signs, shrines...).'),
    ('CONTAINER', 'Every container', 'Runs on chests, barrels, sacks...'),
    ('DOOR', 'Every door', 'Runs on doors.'),
    ('MENU', 'Main menu', 'Runs in the main menu (settings pages), even before a game is loaded.'),
]
KIND_IDS = [k[0] for k in KINDS]

TEMPLATES = [
    {'id': 'welcome', 'label': 'Message when the game loads', 'kind': 'PLAYER', 'text': '''-- Shows a message each time a game is loaded or started.
local ui = require('openmw.ui')

return {
    engineHandlers = {
        onActive = function()
            ui.showMessage('Welcome back to Vvardenfell!')
        end,
    },
}
'''},
    {'id': 'key', 'label': 'Do something when a key is pressed', 'kind': 'PLAYER', 'text': '''-- Press K in game to see the message.
local ui = require('openmw.ui')

return {
    engineHandlers = {
        onKeyPress = function(key)
            if key.symbol == 'k' then
                ui.showMessage('You pressed K.')
            end
        end,
    },
}
'''},
    {'id': 'gift', 'label': 'Give the player items in a new game', 'kind': 'GLOBAL', 'text': '''-- When a new game starts, the player gets these items.
local world = require('openmw.world')
local types = require('openmw.types')

local gifts = {
    { id = 'gold_001', count = 100 },
    { id = 'p_restore_health_s', count = 2 },
}

return {
    engineHandlers = {
        onNewGame = function()
            local player = world.players[1]
            if not player then return end
            for _, g in ipairs(gifts) do
                world.createObject(g.id, g.count):moveInto(types.Actor.inventory(player))
            end
        end,
    },
}
'''},
    {'id': 'quest', 'label': 'React when a quest moves on', 'kind': 'PLAYER', 'text': '''-- When the quest reaches this stage, the player sees a message.
local ui = require('openmw.ui')

local QUEST = 'a1_1_findspymaster'    -- the quest's ID (lower case)
local STAGE = 10

return {
    engineHandlers = {
        onQuestUpdate = function(questId, stage)
            if questId == QUEST and stage == STAGE then
                ui.showMessage('The story moves on...')
            end
        end,
    },
}
'''},
    {'id': 'used', 'label': 'Something happens when an object is used', 'kind': 'CUSTOM', 'text': '''-- Put this on the objects you choose (below). When the player uses one, they see a message.
local self = require('openmw.self')

return {
    engineHandlers = {
        onActivated = function(actor)
            -- the player's own scripts show it on screen
            actor:sendEvent('ShowMessage', { message = 'You touch the ' .. self.recordId .. '.' })
        end,
    },
}
'''},
    {'id': 'counter', 'label': 'Remember something in saved games', 'kind': 'GLOBAL', 'text': '''-- Counts how many days have passed since the mod was added, and keeps the count in saved games.
local core = require('openmw.core')

local state = { days = 0, lastDay = nil }

return {
    engineHandlers = {
        onUpdate = function()
            local day = math.floor(core.getGameTime() / (24 * 3600))
            if state.lastDay and day > state.lastDay then
                state.days = state.days + (day - state.lastDay)
            end
            state.lastDay = day
        end,
        onSave = function() return state end,
        onLoad = function(saved) if saved then state = saved end end,
    },
}
'''},
    {'id': 'blank', 'label': 'Empty script', 'kind': 'GLOBAL', 'text': '''return {
    engineHandlers = {
    },
}
'''},
]


def _check_name(name):
    name = (name or '').strip()
    if not re.match(r'^[A-Za-z0-9_][A-Za-z0-9_\- ]{0,40}$', name):
        raise EditError('Script names can use letters, numbers, spaces, - and _ (up to 40), e.g. "welcome message".')
    return re.sub(r'\s+', '_', name.lower())


def listing(db):
    _require_project(db)
    p = db.project
    out = []
    for s in p.lua:
        probs = lua_check.check(s.get('text') or '', s.get('kind') or 'GLOBAL')
        out.append({'name': s['name'], 'kind': s.get('kind') or 'GLOBAL', 'attach': s.get('attach') or [],
                    'path': p.lua_path(s), 'lines': (s.get('text') or '').count('\n') + 1,
                    'errors': sum(1 for x in probs if x['level'] == 'error'),
                    'warnings': sum(1 for x in probs if x['level'] == 'warning')})
    return {'scripts': out, 'omwscripts': p.lua_omwscripts() if p.lua else None, 'kinds': KINDS,
            'templates': [{k: t[k] for k in ('id', 'label', 'kind')} for t in TEMPLATES]}


def _find(p, name):
    s = next((s for s in p.lua if s['name'] == (name or '').lower()), None)
    if s is None:
        raise EditError('Your mod has no Lua script called "%s".' % name)
    return s


def read(db, name):
    _require_project(db)
    p = db.project
    s = _find(p, name)
    return dict(s, path=p.lua_path(s), problems=lua_check.check(s.get('text') or '', s.get('kind') or 'GLOBAL'))


def create(db, name, template='blank'):
    _require_project(db)
    p = db.project
    key = _check_name(name)
    if any(s['name'] == key for s in p.lua):
        raise EditError('There is already a Lua script called "%s".' % key)
    t = next((t for t in TEMPLATES if t['id'] == template), TEMPLATES[-1])
    s = {'name': key, 'kind': t['kind'], 'attach': [], 'text': t['text']}
    p.lua.append(s)
    commit(db, 'Made the Lua script "%s" (%s)' % (key, t['label'].lower()))
    return read(db, key)


def save(db, name, o):
    _require_project(db)
    p = db.project
    s = _find(p, name)
    kind = (o.get('kind') or s.get('kind') or 'GLOBAL').upper()
    if kind not in KIND_IDS:
        raise EditError('Unknown kind of script.')
    attach = []
    for a in o.get('attach') or []:
        a = (a or '').strip()
        if not a:
            continue
        ri = db.resolve_id(a)
        if ri is None:
            raise EditError('There is nothing called "%s" to put the script on.' % a)
        if db.recs[ri][0] in ('GMST', 'GLOB', 'DIAL', 'INFO', 'SCPT', 'CELL', 'REGN', 'SPEL', 'ENCH', 'MGEF', 'SKIL',
                              'CLAS', 'FACT', 'RACE', 'BSGN', 'SOUN', 'LTEX', 'LAND', 'PGRD', 'BODY', 'SNDG', 'LEVI', 'LEVC'):
            raise EditError('"%s" is not something in the world, so a script can\'t run on it.' % a)
        attach.append(db.recs[ri][1])
    new = {'name': s['name'], 'kind': kind, 'attach': attach, 'text': o.get('text', s.get('text', ''))}
    new_name = o.get('rename')
    if new_name:
        key = _check_name(new_name)
        if key != s['name'] and any(x['name'] == key for x in p.lua):
            raise EditError('There is already a Lua script called "%s".' % key)
        new['name'] = key
    if new == {k: s.get(k) for k in new}:
        return read(db, s['name'])
    s.clear()
    s.update(new)
    commit(db, 'Changed the Lua script "%s"' % s['name'])
    return read(db, s['name'])


def delete(db, name):
    _require_project(db)
    p = db.project
    s = _find(p, name)
    p.lua.remove(s)
    commit(db, 'Removed the Lua script "%s"' % s['name'])
    return {'ok': True}


def check_text(text, kind, attach=False):
    return lua_check.check(text or '', 'LOCAL' if attach else (kind or 'GLOBAL'))
