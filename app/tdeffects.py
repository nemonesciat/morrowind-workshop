"""Tamriel Data's own magic effects in the Workshop's spell, enchantment and potion editors (2026-10-23).

Morrowind's list of magic effects is built into the engine: a spell, an enchantment or a potion names its
effects by number (0 to 142), and a plugin cannot add a number. Tamriel Data adds its effects (summon a
Devourer, Kyne's Intervention, Blink, Passwall, Banish Daedra, Reflect Damage...) in OpenMW with a script that
runs as the game loads (scripts/TamrielData/load_magic.lua, OpenMW's `openmw.content`): it makes each effect
from a vanilla one (its template, for the looks and sounds) under an id like "T_mysticism_Blink", then puts
those effects into its own spells and enchantments, whose records carry the template's effect meanwhile.

The Workshop does the same for the mod: an effect of Tamriel Data's in a spell, enchantment or potion is
written into the record as its template's effect (so the record is a valid one, and the effect falls back to
the template where Tamriel Data isn't loaded), and the mod gets a load script of its own, "td_effects",
that puts the real effect in when the game loads, after Tamriel Data has made it. The script is the record
of which effect is whose: the editors read it back.

What Tamriel Data makes on OpenMW is read from its own files (MWSE/mods/TamrielData/magicdata.lua for the
effects, l10n/TamrielData/en.yaml for their names, and load_magic.lua for which of them it makes there: the
summons, the interventions and the misc effects it adds; not the bound armour and weapons, which UESP lists
as not supported on OpenMW)."""
import re

SCRIPT = 'td_effects'
BEGIN = '-- WORKSHOP EFFECTS BEGIN (kept by the Workshop: the spell, enchantment and potion editors write this list)'
END = '-- WORKSHOP EFFECTS END'
SCHOOLS = {'alteration': 'Alteration', 'conjuration': 'Conjuration', 'destruction': 'Destruction', 'illusion': 'Illusion',
           'mysticism': 'Mysticism', 'restoration': 'Restoration', 'summon': 'Conjuration', 'intervention': 'Mysticism',
           'bound': 'Conjuration'}
KIND_OF = {'SPEL': 'spell', 'ENCH': 'enchantment', 'ALCH': 'potion'}
RANGES = ['self', 'touch', 'target']

LUA = '''-- Made by Morrowind Workshop: Tamriel Data's magic effects, and your own, in this mod's spells, enchantments
-- and potions. Morrowind's records can only name the engine's own effects, so each record carries a stand-in
-- effect, and this script, run as the game loads (after Tamriel Data and my_effects.lua have made theirs),
-- puts the real one in. Needs OpenMW 0.50 or newer; without it (or Tamriel Data, for its effects) the stand-in stays.
local content = require('openmw.content')

%s
%s

local RANGE = { self = content.RANGE.Self, touch = content.RANGE.Touch, target = content.RANGE.Target }
local LISTS = { spell = 'spells', enchantment = 'enchantments', potion = 'potions' }

local function exists(id)
  local ok, rec = pcall(function() return content.magicEffects.records[id] end)
  return ok and rec ~= nil
end

local function apply(kind, id, rows)
  local list = content[LISTS[kind]]
  local rec = list and list.records[id]
  if not rec then return end
  local effects, changed = {}, false
  for i = 1, 8 do
    local e = rec.effects[i]
    if not e then break end
    local r = rows[i]
    if r and exists(r.id) then
      effects[i] = { id = r.id, range = RANGE[r.range], area = r.area, duration = r.duration,
                     magnitudeMin = r.min, magnitudeMax = r.max }
      changed = true
    else
      effects[i] = { id = e.id, range = e.range, area = e.area, duration = e.duration,
                     magnitudeMin = e.magnitudeMin, magnitudeMax = e.magnitudeMax,
                     affectedSkill = e.affectedSkill, affectedAttribute = e.affectedAttribute }
    end
  end
  if changed then rec.effects = effects end
end

return {
  engineHandlers = {
    onContentFilesLoaded = function()
      for _, w in ipairs(wanted) do
        local ok, err = pcall(apply, w[1], w[2], w[3])
        if not ok then print('[Workshop] Tamriel Data effect for ' .. tostring(w[2]) .. ': ' .. tostring(err)) end
      end
    end,
  },
}
'''

_cache = {}


def _read(db, path):
    """A loose file of the game's data folders, the last folder that has it (as OpenMW reads them)."""
    import os
    for d in reversed(list((db.config or {}).get('data') or [])):
        p = os.path.join(d, *path.split('/'))
        if os.path.isfile(p):
            try:
                with open(p, encoding='utf-8', errors='replace') as f:
                    return f.read()
            except OSError:
                return None
    return None


def effects(db):
    """Tamriel Data's effects that OpenMW makes, as the editors list effects: [{index: "T_..", name, school, cost,
    skill False, attribute False, magnitude, duration, td: True, template: the vanilla effect's number, icon,
    enchanting, spellmaking}], or [] when Tamriel Data (with its OpenMW scripts) isn't in the load order."""
    mine = []
    try:
        import myeffects
        mine = myeffects.effects(db)          # (the mod's own: Create > New magic effect)
    except Exception as e:
        print('my magic effects:', e)
    if _cache.get('recs') is db.recs:
        return _cache['out'] + mine
    out = []
    md = _read(db, 'MWSE/mods/TamrielData/magicdata.lua')
    lm = _read(db, 'scripts/TamrielData/load_magic.lua')
    if md and lm:
        names = {}
        for m in re.finditer(r'^Magic_(\w+):\s*"([^"]*)"', _read(db, 'l10n/TamrielData/en.yaml') or '', re.M):
            names[m.group(1)] = m.group(2)
        vanilla = {re.sub(r'[^a-z]', '', n.lower()): i for i, n in db.effect_names.items()}
        import items
        vinfo = {e['index']: e for e in items.effects(db, vanilla_only=True)}

        def block(name):
            m = re.search(r'local %s = \{(.*?)\n\}' % name, md, re.S)
            return m.group(1) if m else ''

        def strs(line):
            return re.findall(r'"((?:[^"\\]|\\.)*)"|([\d.]+)', line)

        def add(eid, key, cost, icon, template, mag=None, dur=None, ench=True, spell=True):
            t = vanilla.get(re.sub(r'[^a-z]', '', (template or '').lower()))
            if t is None:
                return
            tv = vinfo.get(t) or {}
            school = SCHOOLS.get(eid.split('_')[1].lower(), tv.get('school', ''))
            # (no English name for it: its id's last part, spaced, "T_mysticism_SlowTime" -> "Slow Time")
            pretty = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', eid.split('_')[-1])
            out.append({'index': eid, 'name': names.get(key) or pretty, 'school': school, 'cost': round(float(cost), 2),
                        'skill': False, 'attribute': False,
                        'magnitude': tv.get('magnitude', True) if mag is None else mag,
                        'duration': tv.get('duration', True) if dur is None else dur,
                        'td': True, 'template': t, 'icon': icon, 'enchanting': ench, 'spellmaking': spell})
        if re.search(r'addSummons\(\)', lm):
            for line in block('td_summon_effects').splitlines():
                v = [a or b for a, b in strs(line)]
                if len(v) >= 7 and v[0].startswith('T_'):
                    add(v[0], v[1], v[3], v[4], 'summonbear' if v[6] == 'callBear' else v[6])
        if re.search(r'addInterventionEffects\(\)', lm):
            for line in block('td_intervention_effects').splitlines():
                v = [a or b for a, b in strs(line)]
                if len(v) >= 4 and v[0].startswith('T_'):
                    add(v[0], v[1], v[2], v[3], 'divineintervention')
        misc = {}
        for line in block('td_misc_effects').splitlines():
            m = re.match(r'\s*(T_\w+)\s*=\s*\{(.*)\}', line)
            if m:
                misc[m.group(1)] = [a or b for a, b in strs(m.group(2))]
        for m in re.finditer(r'^\s*addMiscEffect\(\'(T_\w+)\',\s*\{(.*?)\}\)', lm, re.M | re.S):
            eid, params = m.group(1), m.group(2)
            v = misc.get(eid)
            if not v or len(v) < 5 or 'Helper' in eid or 'CorruptionSummon' in eid:
                continue
            flag = lambda k: (None if not re.search(k + r'\s*=', params) else bool(re.search(k + r'\s*=\s*true', params)))
            add(eid, v[0], v[1], v[2], v[4], mag=flag('hasMagnitude'), dur=flag('hasDuration'),
                ench=flag('allowsEnchanting') is not False, spell=flag('allowsSpellmaking') is not False)
    _cache.update(recs=db.recs, out=out)
    return out + mine


def by_id(db):
    return {e['index']: e for e in effects(db)}


def is_td(v):
    """An effect named by its id (Tamriel Data's "T_...", or the mod's own), not by the engine's number."""
    return isinstance(v, str) and not v.strip().lstrip('-').isdigit()


# ------------------------------------------------------------------ the mod's load script: the record of who uses what
def script(db):
    p = db.project
    return next((s for s in (p.lua if p else []) if s.get('name') == SCRIPT), None)


def wanted(db):
    """{(kind, record id lower case): {position (1..8): {id, range, area, duration, min, max}}} the script holds."""
    s = script(db)
    out = {}
    if not s:
        return out
    m = re.search(re.escape(BEGIN) + r'\n(.*?)' + re.escape(END), s.get('text') or '', re.S)
    for line in (m.group(1) if m else '').splitlines():
        h = re.match(r'\s*\{\s*"(\w+)",\s*"((?:[^"\\]|\\.)*)",\s*\{(.*)\}\s*\},?\s*$', line)
        if not h:
            continue
        rows = {}
        for r in re.finditer(r'\[(\d)\]\s*=\s*\{\s*id\s*=\s*"([A-Za-z]\w*)",\s*range\s*=\s*"(\w+)",\s*area\s*=\s*(\d+),\s*duration\s*=\s*(\d+),'
                             r'\s*min\s*=\s*(\d+),\s*max\s*=\s*(\d+)\s*\}', h.group(3)):
            rows[int(r.group(1))] = {'id': r.group(2), 'range': r.group(3), 'area': int(r.group(4)), 'duration': int(r.group(5)),
                                     'min': int(r.group(6)), 'max': int(r.group(7))}
        if rows:
            out[(h.group(1), h.group(2).replace('\\"', '"').lower())] = (h.group(2).replace('\\"', '"'), rows)
    return out


def _text(table):
    lines = []
    for (kind, _low), (rid, rows) in sorted(table.items()):
        cells = ', '.join('[%d] = { id = "%s", range = "%s", area = %d, duration = %d, min = %d, max = %d }' % (
            n, r['id'], r['range'], r['area'], r['duration'], r['min'], r['max']) for n, r in sorted(rows.items()))
        lines.append('  { "%s", "%s", { %s } },' % (kind, rid.replace('"', '\\"'), cells))
    return 'local wanted = {\n' + BEGIN + '\n' + '\n'.join(lines) + ('\n' if lines else '') + END + '\n}'


def _write(db, table):
    p = db.project
    s = script(db)
    if not table:
        if s is not None:
            p.lua.remove(s)
        return
    body = _text(table)
    if s is None:
        s = {'name': SCRIPT, 'kind': 'LOAD', 'attach': [], 'text': ''}
        p.lua.append(s)
    s['kind'] = 'LOAD'
    s['text'] = LUA % ('', body)


def remember(db, tag, rid, effs):
    """After a spell, enchantment or potion was written with these effects (as the editors give them): keep the
    script's list for it in step (add its Tamriel Data effects, or drop it). No commit."""
    kind = KIND_OF.get(tag)
    if not kind or not rid:
        return
    table = wanted(db)
    rows = {}
    for n, e in enumerate(effs or [], 1):
        if is_td(e.get('effect')):
            rows[n] = {'id': e['effect'], 'range': RANGES[max(0, min(2, int(e.get('range', 0) or 0)))],
                       'area': int(e.get('area', 0) or 0), 'duration': int(e.get('duration', 0) or 0),
                       'min': int(e.get('min', 1) or 0), 'max': int(e.get('max', e.get('min', 1)) or 0)}
    key = (kind, rid.lower())
    if rows and not db.project.lua_allowed():
        # (a plain .esp carries no Lua: the script that puts these effects in as the game loads would never be
        # written, and the record would keep its stand-ins. The user's Hat of Wild Wizardry in Easy Start.esp
        # showed Fortify Attack where Fortify Casting was picked)
        names = sorted({by_id(db).get(r['id'], {}).get('name', r['id']) for r in rows.values()})
        raise EditError('%s %s put in by an OpenMW script as the game loads, and a plain .esp like %s can\'t carry scripts, so '
                        'the game would show %s stand-in instead. Use Save as… on My mod to make the mod an .omwaddon (it keeps '
                        'everything), or pick one of the game\'s own effects.' % (
                            ', '.join(names), 'is' if len(names) == 1 else 'are', db.project.plugin,
                            'its' if len(names) == 1 else 'their'))
    if rows:
        table[key] = (rid, rows)
    elif key not in table:
        return
    else:
        del table[key]
    _write(db, table)


def overlay(db, tag, rid, effs):
    """The effects of a record as the editors show them: where the script puts one of Tamriel Data's effects in,
    that one instead of its stand-in."""
    kind = KIND_OF.get(tag)
    got = wanted(db).get((kind, (rid or '').lower())) if kind else None
    if not got:
        return effs
    out = []
    for n, e in enumerate(effs, 1):
        r = got[1].get(n)
        out.append(dict(e, effect=r['id'], skill=-1, attribute=-1) if r else e)
    return out
