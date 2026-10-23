"""Builds a searchable in-memory index of every record in the OpenMW load order,
plus a health report (missing masters, missing meshes/icons, dirty edits)."""
import hashlib
import os
import pickle
import re
import struct
import threading
import time
import zlib
from collections import defaultdict

from esm import PluginFile, bsa_entries, iter_subrecords, read_openmw_config, zstr
from nif import MeshIndex

# The record index cache: what reading a plugin file derives (its records' ids, names, search text,
# crcs, which cells and lists use what, which meshes and icons it names) kept in cache/records/, one
# file per plugin, so the next start reads the cache instead of the plugin. Bump when the derived
# shape changes (a Nexus user with a 2,000-plugin list waited an hour at every start).
INDEX_VERSION = 1
PLUGIN_EXTS = ('.esm', '.esp', '.omwaddon', '.omwgame')

TYPE_NAMES = {
    'ACTI': 'Activators', 'ALCH': 'Potions', 'APPA': 'Apparatus', 'ARMO': 'Armor',
    'BODY': 'Body Parts', 'BOOK': 'Books & Scrolls', 'BSGN': 'Birthsigns', 'CELL': 'Cells',
    'CLAS': 'Classes', 'CLOT': 'Clothing', 'CONT': 'Containers', 'CREA': 'Creatures',
    'DIAL': 'Dialogue Topics', 'DOOR': 'Doors', 'ENCH': 'Enchantments', 'FACT': 'Factions',
    'GLOB': 'Globals', 'GMST': 'Game Settings', 'INFO': 'Dialogue Lines', 'INGR': 'Ingredients',
    'LAND': 'Landscape', 'LEVC': 'Leveled Creatures', 'LEVI': 'Leveled Items', 'LIGH': 'Lights',
    'LOCK': 'Lockpicks', 'LTEX': 'Land Textures', 'MGEF': 'Magic Effects', 'MISC': 'Misc Items',
    'NPC_': 'NPCs', 'PGRD': 'Path Grids', 'PROB': 'Probes', 'RACE': 'Races', 'REGN': 'Regions',
    'REPA': 'Repair Tools', 'SCPT': 'Scripts', 'SKIL': 'Skills', 'SNDG': 'Sound Generators',
    'SOUN': 'Sounds', 'SPEL': 'Spells', 'SSCR': 'Start Scripts', 'STAT': 'Statics', 'WEAP': 'Weapons',
}
TYPE_GROUPS = [
    ('Characters', ['NPC_', 'CREA', 'LEVC', 'CLAS', 'RACE', 'FACT', 'BSGN', 'BODY']),
    ('Items', ['WEAP', 'ARMO', 'CLOT', 'MISC', 'BOOK', 'ALCH', 'INGR', 'APPA', 'LOCK', 'PROB', 'REPA', 'LIGH', 'LEVI']),
    ('World', ['CELL', 'STAT', 'ACTI', 'DOOR', 'CONT', 'REGN', 'LAND', 'LTEX', 'PGRD']),
    ('Magic', ['SPEL', 'ENCH', 'MGEF']),
    ('Quests & Dialogue', ['DIAL', 'INFO', 'SCPT', 'SSCR', 'GLOB']),
    ('Other', ['GMST', 'SKIL', 'SOUN', 'SNDG']),
]

SKILLS = ['Block', 'Armorer', 'Medium Armor', 'Heavy Armor', 'Blunt Weapon', 'Long Blade', 'Axe', 'Spear',
          'Athletics', 'Enchant', 'Destruction', 'Alteration', 'Illusion', 'Conjuration', 'Mysticism',
          'Restoration', 'Alchemy', 'Unarmored', 'Security', 'Sneak', 'Acrobatics', 'Light Armor',
          'Short Blade', 'Marksman', 'Mercantile', 'Speechcraft', 'Hand-to-hand']
ATTRIBUTES = ['Strength', 'Intelligence', 'Willpower', 'Agility', 'Speed', 'Endurance', 'Personality', 'Luck']
EFFECT_GMST = (
    'WaterBreathing SwiftSwim WaterWalking Shield FireShield LightningShield FrostShield Burden Feather Jump '
    'Levitate SlowFall Lock Open FireDamage ShockDamage FrostDamage DrainAttribute DrainHealth DrainSpellpoints '
    'DrainFatigue DrainSkill DamageAttribute DamageHealth DamageMagicka DamageFatigue DamageSkill Poison '
    'WeaknesstoFire WeaknesstoFrost WeaknesstoShock WeaknesstoMagicka WeaknesstoCommonDisease '
    'WeaknesstoBlightDisease WeaknesstoCorprusDisease WeaknesstoPoison WeaknesstoNormalWeapons '
    'DisintegrateWeapon DisintegrateArmor Invisibility Chameleon Light Sanctuary NightEye Charm Paralyze '
    'Silence Blind Sound CalmHumanoid CalmCreature FrenzyHumanoid FrenzyCreature DemoralizeHumanoid '
    'DemoralizeCreature RallyHumanoid RallyCreature Dispel Soultrap Telekinesis Mark Recall DivineIntervention '
    'AlmsiviIntervention DetectAnimal DetectEnchantment DetectKey SpellAbsorption Reflect CureCommonDisease '
    'CureBlightDisease CureCorprusDisease CurePoison CureParalyzation RestoreAttribute RestoreHealth '
    'RestoreSpellPoints RestoreFatigue RestoreSkill FortifyAttribute FortifyHealth FortifySpellpoints '
    'FortifyFatigue FortifySkill FortifyMagickaMultiplier AbsorbAttribute AbsorbHealth AbsorbSpellPoints '
    'AbsorbFatigue AbsorbSkill ResistFire ResistFrost ResistShock ResistMagicka ResistCommonDisease '
    'ResistBlightDisease ResistCorprusDisease ResistPoison ResistNormalWeapons ResistParalysis RemoveCurse '
    'TurnUndead SummonScamp SummonClannfear SummonDaedroth SummonDremora SummonAncestralGhost '
    'SummonSkeletalMinion SummonLeastBonewalker SummonGreaterBonewalker SummonBonelord SummonWingedTwilight '
    'SummonHunger SummonGoldenSaint SummonFlameAtronach SummonFrostAtronach SummonStormAtronach FortifyAttackBonus '
    'CommandCreatures CommandHumanoids BoundDagger BoundLongsword BoundMace BoundBattleAxe BoundSpear '
    'BoundLongbow EXTRASPELL BoundCuirass BoundHelm BoundBoots BoundShield BoundGloves Corpus Vampirism '
    'SummonCenturionSphere SunDamage StuntedMagicka SummonFabricant SummonCreature01 SummonCreature02 '
    'SummonCreature03 SummonCreature04 SummonCreature05').split()

ENUMS = {
    ('WEAP', 'Weapon Type'): ['Short Blade', 'Long Blade (1H)', 'Long Blade (2H)', 'Blunt (1H)', 'Blunt (2H Close)',
                             'Blunt (2H Wide)', 'Spear', 'Axe (1H)', 'Axe (2H)', 'Bow', 'Crossbow', 'Thrown',
                             'Arrow', 'Bolt'],
    ('ARMO', 'Armor Type'): ['Helmet', 'Cuirass', 'Left Pauldron', 'Right Pauldron', 'Greaves', 'Boots',
                            'Left Gauntlet', 'Right Gauntlet', 'Shield', 'Left Bracer', 'Right Bracer'],
    ('CLOT', 'Clothing Type'): ['Pants', 'Shoes', 'Shirt', 'Belt', 'Robe', 'Right Glove', 'Left Glove', 'Skirt',
                               'Ring', 'Amulet'],
    ('SPEL', 'Spell Type'): ['Spell', 'Ability', 'Blight Disease', 'Disease', 'Curse', 'Power'],
    ('ENCH', 'Enchant Type'): ['Cast Once', 'Cast When Strikes', 'Cast When Used', 'Constant Effect'],
    ('CREA', 'Creature Type'): ['Creature', 'Daedra', 'Undead', 'Humanoid'],
    ('APPA', 'Apparatus Type'): ['Mortar & Pestle', 'Alembic', 'Calcinator', 'Retort'],
    ('DIAL', 'Dialogue Type'): ['Topic', 'Voice', 'Greeting', 'Persuasion', 'Journal'],
    ('INFO', 'Dialogue Type'): ['Topic', 'Voice', 'Greeting', 'Persuasion', 'Journal'],
    ('BOOK', 'Teaches Skill'): SKILLS,
    ('BODY', 'Body Part'): ['Head', 'Hair', 'Neck', 'Chest', 'Groin', 'Hand', 'Wrist', 'Forearm', 'Upper arm', 'Foot',
                            'Ankle', 'Knee', 'Upper leg', 'Clavicle', 'Tail'],
    ('BODY', 'Part Type'): ['Skin', 'Clothing', 'Armor'],
    ('BODY', 'Vampire'): ['No', 'Yes (vampire version)'],
    ('SNDG', 'Sound Type'): ['Left footstep', 'Right footstep', 'Swimming (left)', 'Swimming (right)', 'Moan', 'Roar',
                             'Scream', 'Landing'],
    ('SKIL', 'Specialization'): ['Combat', 'Magic', 'Stealth'],
    ('MGEF', 'School'): ['Alteration', 'Conjuration', 'Destruction', 'Illusion', 'Mysticism', 'Restoration'],
}

STRUCTS = {
    ('WEAP', 'WPDT'): ('<fihhffhBBBBBBi', ['Weight', 'Value', 'Weapon Type', 'Condition', 'Speed', 'Reach',
                                          'Enchant Points', 'Chop Min', 'Chop Max', 'Slash Min', 'Slash Max',
                                          'Thrust Min', 'Thrust Max', 'Flags']),
    ('ARMO', 'AODT'): ('<ifiiii', ['Armor Type', 'Weight', 'Value', 'Condition', 'Enchant Points', 'Armor Rating']),
    ('CLOT', 'CTDT'): ('<ifhh', ['Clothing Type', 'Weight', 'Value', 'Enchant Points']),
    ('MISC', 'MCDT'): ('<fii', ['Weight', 'Value', 'Is Key']),
    ('BOOK', 'BKDT'): ('<fiiii', ['Weight', 'Value', 'Is Scroll', 'Teaches Skill', 'Enchant Points']),
    ('ALCH', 'ALDT'): ('<fii', ['Weight', 'Value', 'Auto Calculate']),
    ('APPA', 'AADT'): ('<iffi', ['Apparatus Type', 'Quality', 'Weight', 'Value']),
    ('LOCK', 'LKDT'): ('<fifi', ['Weight', 'Value', 'Quality', 'Uses']),
    ('PROB', 'PBDT'): ('<fifi', ['Weight', 'Value', 'Quality', 'Uses']),
    ('REPA', 'RIDT'): ('<fiif', ['Weight', 'Value', 'Uses', 'Quality']),
    ('LIGH', 'LHDT'): ('<fiiiBBBBi', ['Weight', 'Value', 'Duration', 'Radius', 'Red', 'Green', 'Blue', None, 'Flags']),
    ('INGR', 'IRDT'): ('<fi4i4i4i', ['Weight', 'Value'] + ['Effect %d' % i for i in range(1, 5)]
                       + ['Skill %d' % i for i in range(1, 5)] + ['Attribute %d' % i for i in range(1, 5)]),
    ('SPEL', 'SPDT'): ('<iii', ['Spell Type', 'Cost', 'Flags']),
    ('ENCH', 'ENDT'): ('<iiii', ['Enchant Type', 'Cost', 'Charge', 'Auto Calculate']),
    ('CONT', 'CNDT'): ('<f', ['Capacity']),
    ('CELL', 'DATA'): ('<iii', ['Flags', 'Grid X', 'Grid Y']),
    ('CELL', 'WHGT'): ('<f', ['Water Height']),
    ('CELL', 'INTV'): ('<i', ['Water Height']),
    ('CELL', 'AMBI'): ('<4B4B4Bf', ['Ambient R', 'Ambient G', 'Ambient B', None, 'Sunlight R', 'Sunlight G',
                                     'Sunlight B', None, 'Fog R', 'Fog G', 'Fog B', None, 'Fog Density']),
    ('GLOB', 'FLTV'): ('<f', ['Value']),
    ('GMST', 'INTV'): ('<i', ['Value']),
    ('GMST', 'FLTV'): ('<f', ['Value']),
    ('LEVI', 'DATA'): ('<i', ['Flags']),
    ('LEVC', 'DATA'): ('<i', ['Flags']),
    ('LEVI', 'NNAM'): ('<B', ['Chance None (%)']),
    ('LEVC', 'NNAM'): ('<B', ['Chance None (%)']),
    ('LEVI', 'INDX'): ('<i', ['Entry Count']),
    ('LEVC', 'INDX'): ('<i', ['Entry Count']),
    ('SOUN', 'DATA'): ('<BBB', ['Volume', 'Min Range', 'Max Range']),
    ('CREA', 'NPDT'): ('<24i', ['Creature Type', 'Level'] + ATTRIBUTES + ['Health', 'Magicka', 'Fatigue', 'Soul',
                                                                       'Combat', 'Magic', 'Stealth',
                                                                       'Attack 1 Min', 'Attack 1 Max',
                                                                       'Attack 2 Min', 'Attack 2 Max',
                                                                       'Attack 3 Min', 'Attack 3 Max', 'Gold']),
    ('CREA', 'XSCL'): ('<f', ['Scale']),
    ('INFO', 'DATA'): ('<iibbbb', ['Dialogue Type', 'Disposition', 'Speaker Rank', 'Speaker Sex', 'Player Rank', None]),
    ('DIAL', 'DATA'): ('<B', ['Dialogue Type']),
    ('SKIL', 'INDX'): ('<i', ['Skill Index']),
    ('SKIL', 'SKDT'): ('<ii4f', ['Governing Attribute', 'Specialization', 'Use Value 1', 'Use Value 2',
                                 'Use Value 3', 'Use Value 4']),
    ('MGEF', 'INDX'): ('<i', ['Effect Index']),
    ('MGEF', 'MEDT'): ('<ifiiiifff', ['School', 'Base Cost', 'Flags', 'Light Red', 'Light Blue', 'Light Green', 'Speed',
                                      'Size', 'Size Cap']),
    ('BODY', 'BYDT'): ('<BBBB', ['Body Part', 'Vampire', 'Flags', 'Part Type']),
    ('SCPT', 'SCHD'): ('<32s5i', [None, 'Shorts', 'Longs', 'Floats', 'Compiled Size', 'Locals Size']),
    ('LTEX', 'INTV'): ('<i', ['Index']),
    ('SNDG', 'DATA'): ('<i', ['Sound Type']),
    ('REGN', 'CNAM'): ('<4B', ['Map Red', 'Map Green', 'Map Blue', None]),
}
for _t in ('NPC_', 'CREA', 'CONT'):
    STRUCTS[(_t, 'FLAG')] = ('<i', ['Flags'])
for _t in ('NPC_', 'CREA'):
    STRUCTS[(_t, 'AIDT')] = ('<BBBBBBBBi', ['Hello', None, 'Fight', 'Flee', 'Alarm', None, None, None, 'Services'])
    STRUCTS[(_t, 'AI_W')] = ('<hh', ['Wander Distance', 'Wander Duration (hours)'])

LABELS = {
    'NAME': 'ID', 'FNAM': 'Name', 'MODL': 'Model', 'ITEX': 'Icon', 'SCRI': 'Script', 'ENAM': 'Enchantment',
    'RNAM': 'Race', 'CNAM': 'Class', 'ANAM': 'Faction', 'BNAM': 'Head', 'KNAM': 'Hair', 'NPCS': 'Spell',
    'TEXT': 'Text', 'DESC': 'Description', 'RGNN': 'Region', 'SCTX': 'Script Text', 'STRV': 'Value',
    'SNAM': 'Sound', 'DNAM': 'Destination Cell', 'INAM': 'Line ID', 'PNAM': 'Previous Line', 'NNAM': 'Next Line',
    'ONAM': 'Speaker Actor', 'SCVR': 'Condition', 'XSCL': 'Scale', 'CNDT': 'Condition', 'NPCO': 'Carries',
    'TNAM': 'Sound', 'PTEX': 'Image', 'INDX': 'Index',
    'CSND': 'Casting Sound', 'BSND': 'Bolt Sound', 'HSND': 'Hit Sound', 'ASND': 'Area Sound',
    'CVFX': 'Casting Visual', 'BVFX': 'Bolt Visual', 'HVFX': 'Hit Visual', 'AVFX': 'Area Visual',
}
INFO_LABELS = {'RNAM': 'Speaker Race', 'CNAM': 'Speaker Class', 'ANAM': 'Speaker Cell', 'FNAM': 'Speaker Faction',
               'DNAM': 'Player Faction', 'SNAM': 'Voice File', 'NAME': 'Response', 'BNAM': 'Result Script',
               'QSTN': 'Quest Name', 'QSTF': 'Quest Finished', 'QSTR': 'Quest Restart'}
ARMOR_PART_LABELS = {'BNAM': 'Male Part', 'CNAM': 'Female Part', 'INDX': 'Body Slot'}

CELL_REF_RE = re.compile(rb'FRMR\x04\x00\x00\x00[\s\S]{4}NAME([\s\S]{4})')

CELL_PREFIXES = ('FRMR', 'MVRF')


def _id_of(tag, data):
    """Return (id, display name, extra) for a record."""
    name = ''
    rid = ''
    extra = ''
    if tag == 'SCPT':
        for st, sd in iter_subrecords(data):
            if st == 'SCHD':
                rid = zstr(sd[:32])
            elif st == 'SCTX':
                first = sd[:200].split(b'\n')
                extra = ' '.join(zstr(x).strip() for x in first[:3])
                break
        return rid, '', extra
    for st, sd in iter_subrecords(data):
        if st == 'NAME' and not rid:
            rid = zstr(sd)
        elif st == 'FNAM' and not name:
            name = zstr(sd)
        elif st == 'MODL' and not extra:
            extra = zstr(sd)
        elif st == 'INDX' and tag in ('SKIL', 'MGEF') and len(sd) >= 4:
            rid = str(struct.unpack_from('<i', sd)[0])
        elif st == 'STRV':
            name = zstr(sd)
        elif st in ('INTV', 'FLTV') and tag in ('GMST', 'GLOB') and len(sd) >= 4:
            name = str(round(struct.unpack_from('<f' if st == 'FLTV' else '<i', sd)[0], 4))
        elif tag == 'NPC_' and st in ('RNAM', 'CNAM', 'ANAM'):
            extra = (extra + ' ' + zstr(sd)).strip() if st != 'RNAM' else zstr(sd) + ' ' + extra
    if tag == 'NPC_':
        extra = extra.strip()
    return rid, name, extra


class VirtualFile:
    """Stands in for a plugin file: holds the project's records in memory."""

    def __init__(self):
        self.slots = {}

    def record_at(self, offset):
        return self.slots[offset]

    def close(self):
        pass


def _cache_dir():
    from project import APP_DIR
    return os.path.join(APP_DIR, 'cache', 'records')


def _cache_path(path):
    h = hashlib.md5(os.path.normcase(os.path.abspath(path)).encode('utf-8')).hexdigest()[:10]
    return os.path.join(_cache_dir(), '%s.%s.pkl' % (os.path.basename(path), h))


def _file_stamp(path):
    st = os.stat(path)
    return st.st_size, int(st.st_mtime)


class Database:
    def __init__(self):
        self.project = None
        self.overlay = {}
        self.dead = set()
        self.proj_pidx = None
        self.state = 'idle'
        self.progress = {'step': 'Starting', 'done': 0, 'total': 1}
        self.error = None
        self.lock = threading.Lock()
        self.adding = None          # plugins being added to the end of the load order right now
        self.last_add = None        # what the last incremental add did (for the page's note)
        self.reset()

    def reset(self):
        for f in getattr(self, 'files', []):
            if f:
                f.close()
        self.config = {}
        self.plugins = []          # dicts: name, path, header, counts, missing
        self.files = []            # PluginFile objects (index matches plugins)
        self.recs = []             # (tag, id, name, pidx, offset, extra, flags)
        self.search_text = []      # lowercased "id name extra"
        self.by_key = defaultdict(list)   # (tag, idlower) -> [rec idx]
        self.by_id = defaultdict(list)    # idlower -> [rec idx] (any type, for link resolution)
        self.used_in = defaultdict(set)   # idlower -> {rec idx of cell/npc/container/list}
        self.dial_infos = defaultdict(list)  # dial rec idx -> [info rec idx]
        self.info_dial = {}               # info rec idx -> dial rec idx
        self.assets = set()
        self.asset_sources = []
        self.issues = []
        self.effect_names = {}
        self.type_counts = defaultdict(int)
        self.winner = bytearray()
        self._crcs = None

    # ---------- loading ----------
    def load_async(self):
        t = threading.Thread(target=self._load_safe, daemon=True)
        t.start()

    def _load_safe(self):
        try:
            self.state = 'loading'
            self._load()
            self.state = 'ready'
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error = '%s: %s' % (type(e).__name__, e)
            self.state = 'error'

    def _find_file(self, name):
        for d in reversed(self.config['data']):
            p = os.path.join(d, name)
            if os.path.isfile(p):
                return p
        return None

    def _scan_assets(self):
        self.progress = {'step': 'Scanning meshes and icons', 'done': 0, 'total': 1}
        assets = set()
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.meshes = MeshIndex(os.path.join(app_dir, 'cache', 'mesh_sizes.json'))
        # the folder your mods (and the Library's files) live in counts too, last: OpenMW always reads it
        mine = os.environ.get('WORKSHOP_PLUGIN_DIR') or self.config.get('data_local')
        dirs = list(self.config['data'])
        if mine and os.path.normcase(os.path.abspath(mine)) not in {os.path.normcase(os.path.abspath(d)) for d in dirs}:
            dirs.append(mine)
        for d in dirs:
            if not os.path.isdir(d):
                continue
            n_before = len(assets)
            for sub in os.listdir(d):
                if sub.lower() not in ('meshes', 'icons', 'textures', 'sound'):
                    continue
                root_len = len(d) + 1
                is_mesh = sub.lower() in ('meshes', 'textures', 'sound')     # (sounds too, to play them)
                for root, _dirs, fnames in os.walk(os.path.join(d, sub)):
                    rel = root[root_len:].replace('\\', '/').lower()
                    for fn in fnames:
                        rp = rel + '/' + fn.lower()
                        assets.add(rp)
                        if is_mesh:
                            self.meshes.loose[rp] = os.path.join(root, fn)
            self.asset_sources.append({'kind': 'folder', 'path': d, 'files': len(assets) - n_before})
        for a in self.config['archives']:
            p = self._find_file(a)
            if not p:
                self.issues.append({'severity': 'error', 'kind': 'Missing archive', 'plugin': a,
                                    'detail': 'openmw.cfg lists "%s" as an archive but it is not in any data folder.' % a,
                                    'items': []})
                continue
            try:
                entries = bsa_entries(p)
                lst = [e[0] for e in entries]
                assets.update(lst)
                for name, off, size in entries:
                    if name.startswith(('meshes/', 'textures/', 'sound/')):
                        self.meshes.packed[name] = (p, off, size)
                self.asset_sources.append({'kind': 'archive', 'path': p, 'files': len(lst)})
            except Exception as e:
                self.issues.append({'severity': 'warning', 'kind': 'Unreadable archive', 'plugin': a,
                                    'detail': str(e), 'items': []})
        self.assets = assets

    def _asset_ok(self, folder, path):
        p = (folder + '/' + path.replace('\\', '/')).lower()
        if p in self.assets:
            return True
        base, ext = os.path.splitext(p)
        if ext in ('.tga', '.bmp') and base + '.dds' in self.assets:
            return True   # OpenMW falls back to .dds textures
        return False

    def _load(self):
        self.reset()
        t0 = time.time()
        from project import load_settings
        self.config = read_openmw_config(load_settings().get('openmw_install'))
        self._scan_assets()
        proj_plugin = self.project.plugin.lower() if self.project else None
        self.cfg_content_all = list(self.config['content'])
        # the plugin being edited is shown from the project itself, not from its compiled file
        self.config['content'] = [c for c in self.config['content'] if c.lower() != proj_plugin]
        content = [c for c in self.config['content'] if os.path.splitext(c)[1].lower() in PLUGIN_EXTS]
        scripts_only = [c for c in self.config['content'] if c not in content]
        self._crcs = {}
        self.load_from_cache = 0
        self._read_plugins(content, content, [])
        for s in scripts_only:
            self.plugins.append(self._lua_entry(s))
            self.files.append(None)
        self._resolve_effect_names()
        self.winner = bytearray(len(self.recs))
        for lst in self.by_key.values():
            self.winner[lst[-1]] = 1
        self.overlay = {}
        self.dead = set()
        self.proj_pidx = None
        if self.project:
            self.attach_project(self.project)
            try:
                # make sure the plugin file matches the project (e.g. after the game had it locked)
                import editing
                editing.build(self)
            except Exception as e:
                print('Could not write the plugin:', e)
        self.progress = {'step': 'Done', 'done': 1, 'total': 1}
        self.load_seconds = round(time.time() - t0, 1)

    def _lua_entry(self, name):
        return {'name': name, 'path': self._find_file(name), 'header': {}, 'counts': {}, 'records': 0,
                'size': 0, 'overrides': 0, 'new': 0, 'dirty': 0, 'missing_assets': 0, 'problems': [], 'lua_only': True}

    def _read_plugins(self, names, content, loaded_names, before_project=False):
        """Read these plugin files, in order, into the index: from the record cache when the file is
        unchanged, else parsed (and cached). `content` is the whole content list (for the master
        notes); `loaded_names` what is loaded already (extended here)."""
        sizes = {}
        for c in names:
            p = self._find_file(c)
            sizes[c] = os.path.getsize(p) if p else 0
        total = sum(sizes.values()) or 1
        done_bytes = 0
        n_all = len(names)
        low_content = [x.lower() for x in content]
        for n, c in enumerate(names):
            path = self._find_file(c)
            entry = {'name': c, 'path': path, 'header': {}, 'counts': {}, 'records': 0, 'size': sizes[c],
                     'overrides': 0, 'new': 0, 'dirty': 0, 'missing_assets': 0, 'problems': []}
            if not path:
                entry['problems'].append('File not found in any data folder')
                self.issues.append({'severity': 'error', 'kind': 'Missing plugin', 'plugin': c,
                                    'detail': 'openmw.cfg enables "%s" but the file is not in any data folder. '
                                              'OpenMW will refuse to start, or skip it.' % c, 'items': []})
                self.plugins.append(entry)
                self.files.append(None)
                continue
            step = 'Reading %s of %s: %s' % (format(n + 1, ','), format(n_all, ','), c)
            self.progress = {'step': step, 'done': done_bytes, 'total': total}
            pf = PluginFile(path)
            payload = self._payload(pf, c, step, done_bytes, total)
            entry['header'] = pf.header
            low_loaded = [x.lower() for x in loaded_names]
            for m in pf.header['masters']:
                if m.lower() not in low_loaded:
                    later = m.lower() in low_content
                    msg = ('is loaded after it - move "%s" higher in the load order.' % m) if later else 'is not enabled or not installed.'
                    entry['problems'].append('Needs master "%s", which %s' % (m, msg))
                    self.issues.append({'severity': 'error', 'kind': 'Missing master', 'plugin': c,
                                        'detail': '"%s" requires "%s", which %s' % (c, m, msg), 'items': []})
            self.plugins.append(entry)
            self.files.append(pf)
            pidx = len(self.plugins) - 1
            self._merge_plugin(payload, pidx, entry, before_project)
            done_bytes += sizes[c]
            loaded_names.append(c)

    def _payload(self, pf, name, step, done_bytes, total):
        """What a plugin file's records derive to: from the cache when the file is unchanged, else
        parsed from the file and written to the cache."""
        cp = _cache_path(pf.path)
        try:
            size, mtime = _file_stamp(pf.path)
        except OSError:
            size, mtime = -1, -1
        try:
            with open(cp, 'rb') as f:
                pl = pickle.load(f)
            if pl.get('version') == INDEX_VERSION and pl.get('size') == size and pl.get('mtime') == mtime:
                self.load_from_cache += 1
                return pl
        except (OSError, EOFError, ValueError, pickle.UnpicklingError, AttributeError, TypeError):
            pass
        pl = self._parse_plugin(pf, name, step, done_bytes, total)
        pl.update({'version': INDEX_VERSION, 'size': size, 'mtime': mtime, 'path': pf.path})
        try:
            os.makedirs(_cache_dir(), exist_ok=True)
            tmp = cp + '.%d.tmp' % os.getpid()
            with open(tmp, 'wb') as f:
                pickle.dump(pl, f, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(tmp, cp)
        except OSError as e:
            print('Could not write the record cache for %s: %s' % (name, e))
        return pl

    def _parse_plugin(self, pf, pname, step, done_bytes, total):
        """Read every record of a plugin file. Pure: nothing here depends on the other plugins, the
        data folders or the position in the load order, so the result can be cached."""
        recs, crcs = [], []
        used_in = defaultdict(list)      # object id -> [local rec idx] (cells, lists, inventories)
        assets = []                      # (local rec idx, kind, folder, path as written)
        dial = []                        # (info local idx, dial local idx)
        counts = defaultdict(int)
        current_dial = None
        dial_id = ''
        tick = 0
        for tag, offset, flags, data in pf.records():
            tick += 1
            if tick % 4000 == 0:
                self.progress = {'step': step, 'done': done_bytes + offset, 'total': total}
            ri = len(recs)
            if tag == 'CELL':
                rid, name, extra, key = self._cell_info(data)
                for m in CELL_REF_RE.finditer(data):
                    size = struct.unpack('<I', m.group(1))[0]
                    obj = zstr(data[m.end():m.end() + size]).lower()
                    used_in[obj].append(ri)
            elif tag == 'LAND':
                xy = struct.unpack_from('<ii', data, 8) if data[:4] == b'INTV' else (0, 0)
                rid, name, extra, key = '%d, %d' % xy, '', '', '%d,%d' % xy
            elif tag == 'PGRD':
                rid, name, extra = _id_of(tag, data[:200])
                dd = data.find(b'DATA')
                gx = struct.unpack_from('<ii', data, dd + 8) if dd >= 0 else (0, 0)
                if not rid:
                    rid = '%d, %d' % gx
                # outdoors many cells share a name (a region's): the game tells them apart by grid
                key = ('#%d,%d' % gx) if gx != (0, 0) else rid.lower()
            elif tag == 'INFO':
                inam, text, extra = '', '', ''
                for st, sd in iter_subrecords(data):
                    if st == 'INAM':
                        inam = zstr(sd)
                    elif st == 'NAME':
                        text = zstr(sd)
                    elif st == 'ONAM' and not extra:
                        extra = zstr(sd)
                rid, name = inam, text[:300]
                extra = (dial_id + ' ' + extra).strip()
                key = (dial_id + '|' + inam).lower()
                if current_dial is not None:
                    dial.append((ri, current_dial))
            else:
                rid, name, extra = _id_of(tag, data)
                key = rid.lower()
                if tag in ('NPC_', 'CREA', 'CONT'):
                    for st, sd in iter_subrecords(data):
                        if st == 'NPCO' and len(sd) >= 36:
                            used_in[zstr(sd[4:36]).lower()].append(ri)
                        elif st == 'NPCS':
                            used_in[zstr(sd).lower()].append(ri)
                elif tag in ('LEVI', 'LEVC'):
                    for st, sd in iter_subrecords(data):
                        if st in ('INAM', 'CNAM'):
                            used_in[zstr(sd).lower()].append(ri)
            if tag == 'DIAL':
                current_dial, dial_id = ri, rid
            # the meshes and icons it names (checked against the data folders when loaded)
            if tag not in ('CELL', 'LAND', 'PGRD', 'INFO', 'DIAL', 'GMST', 'GLOB', 'SCPT', 'TES3'):
                for st, sd in iter_subrecords(data):
                    if st == 'MODL':
                        mp = zstr(sd)
                        if mp:
                            assets.append((ri, 'Mesh', 'meshes', mp))
                    elif st == 'ITEX' and tag != 'LTEX':
                        ip = zstr(sd)
                        if ip:
                            assets.append((ri, 'Icon', 'icons', ip))
            crcs.append(zlib.crc32(data))
            recs.append((tag, rid, name, offset, extra, flags, key))
            counts[tag] += 1
        # (the search text is rebuilt from the records when loaded: a third of the cache file otherwise)
        return {'recs': recs, 'crcs': crcs, 'used': dict(used_in), 'assets': assets,
                'dial': dial, 'counts': dict(counts)}

    def _merge_plugin(self, pl, pidx, entry, before_project=False):
        """Put a plugin's parsed records into the index as plugin `pidx`: overrides and dirty edits
        against what is loaded before it, the missing meshes and icons against the data folders.
        `before_project`: the mod being edited is loaded already and stays last (its records keep
        winning), so this plugin's versions slot in just before them."""
        recs, stext, by_key, by_id, used_in = self.recs, self.search_text, self.by_key, self.by_id, self.used_in
        crcs = self._crcs
        base = len(recs)
        proj = self.proj_pidx if before_project else None
        new = over = dirty = 0
        pcrcs = pl['crcs']
        for i, (tag, rid, name, offset, extra, flags, key) in enumerate(pl['recs']):
            ri = base + i
            crc = pcrcs[i]
            prev = by_key.get((tag, key))
            if prev:
                over += 1
                last = prev[-1]
                if proj is not None and recs[last][3] == proj:
                    last = prev[-2] if len(prev) > 1 else None
                    prev.insert(len(prev) - 1, ri)
                else:
                    prev.append(ri)
                if last is not None and crcs.get(last) == crc:
                    dirty += 1
            else:
                new += 1
                by_key[(tag, key)] = [ri]
            crcs[ri] = crc
            if rid:
                lst = by_id[rid.lower()]
                if proj is not None and lst and recs[lst[-1]][3] == proj:
                    lst.insert(len(lst) - 1, ri)
                else:
                    lst.append(ri)
            recs.append((tag, rid, name, pidx, offset, extra, flags, key))
            stext.append(('%s\t%s\t%s' % (rid, name, extra)).lower())
        for obj, lst in pl['used'].items():
            used_in[obj].update(base + x for x in lst)
        for ii, di in pl['dial']:
            self.dial_infos[base + di].append(base + ii)
            self.info_dial[base + ii] = base + di
        counts = pl['counts']
        for tag, n in counts.items():
            self.type_counts[tag] += n
        missing = defaultdict(list)
        prec = pl['recs']
        for i, kind, folder, p in pl['assets']:
            if not self._asset_ok(folder, p):
                missing[(kind, folder + '/' + p.replace('\\', '/'))].append(prec[i][1])
        entry['overrides'], entry['new'], entry['dirty'] = over, new, dirty
        entry['counts'] = dict(counts)
        entry['records'] = len(prec)
        entry['missing_assets'] = len(missing)
        if missing:
            items = [{'kind': k[0], 'path': k[1], 'used_by': sorted(set(v))[:8], 'uses': len(v)}
                     for k, v in sorted(missing.items(), key=lambda kv: (-len(kv[1]), kv[0][1]))]
            n_mesh = sum(1 for i in items if i['kind'] == 'Mesh')
            n_icon = len(items) - n_mesh
            parts = []
            if n_mesh:
                parts.append('%d mesh%s' % (n_mesh, 'es' if n_mesh != 1 else ''))
            if n_icon:
                parts.append('%d icon%s' % (n_icon, 's' if n_icon != 1 else ''))
            official = entry['name'].lower() in ('morrowind.esm', 'tribunal.esm', 'bloodmoon.esm')
            self.issues.append({
                'severity': 'info' if official else 'warning', 'kind': 'Missing files', 'plugin': entry['name'],
                'detail': '%s referenced by this plugin could not be found in your data folders or archives. %s'
                          % (' and '.join(parts).capitalize(),
                             'Bethesda left these unused references in the original game. They are harmless.'
                             if official else
                             'In-game these show as invisible objects, red/yellow "!" markers or blank icons.'),
                'items': items})
        if entry['dirty']:
            official = entry['name'].lower() in ('tribunal.esm', 'bloodmoon.esm')
            self.issues.append({'severity': 'info', 'kind': 'Identical copies', 'plugin': entry['name'],
                                'detail': '%d records are exact copies of what an earlier file already defines '
                                          '("dirty edits"). %s' % (entry['dirty'],
                                          'This is normal for Bethesda\'s own expansions - nothing to fix.' if official else
                                          'Usually harmless, but they can silently undo changes from plugins '
                                          'loaded between them.'), 'items': []})

    def _cell_info(self, data):
        name, region, flags, gx, gy = '', '', 0, 0, 0
        for st, sd in iter_subrecords(data):
            if st == 'NAME':
                name = zstr(sd)
            elif st == 'DATA' and len(sd) >= 12:
                flags, gx, gy = struct.unpack_from('<iii', sd)
            elif st == 'RGNN':
                region = zstr(sd)
            elif st in CELL_PREFIXES:
                break
        if flags & 1:
            return name, '', 'interior', name.lower()
        rid = '%s (%d, %d)' % (name or region or 'Wilderness', gx, gy)
        return rid, '', 'exterior ' + region, '#%d,%d' % (gx, gy)

    def _resolve_effect_names(self, start=0):
        for i, g in enumerate(EFFECT_GMST):
            lst = self.by_key.get(('GMST', ('sEffect' + g).lower()))
            self.effect_names[i] = self.recs[lst[-1]][2] if lst else g
        # name MGEF records by their effect
        for ri in range(start, len(self.recs)):
            r = self.recs[ri]
            if r is None:
                continue
            if r[0] == 'MGEF' and r[1].lstrip('-').isdigit():
                n = self.effect_names.get(int(r[1]), '')
                self.recs[ri] = r[:2] + (n,) + r[3:]
                self.search_text[ri] = ('%s\t%s\t%s' % (r[1], n, r[5])).lower()
            elif r[0] == 'SKIL' and r[1].isdigit() and int(r[1]) < len(SKILLS):
                n = SKILLS[int(r[1])]
                self.recs[ri] = r[:2] + (n,) + r[3:]
                self.search_text[ri] = ('%s\t%s\t%s' % (r[1], n, r[5])).lower()

    # ---------- the load order changed ----------
    def apply_order(self, order):
        """The load order was saved as `order`. Plugins switched on at the end of the list are read and
        added to what is loaded (quick, no loading screen); any other change reads everything again
        (from the record cache, so quick too). Returns what was chosen, for the page."""
        from loadorder import INTERNAL
        old = [c.lower() for c in getattr(self, 'cfg_content_all', []) if c.lower() not in INTERNAL]
        new = [o.lower() for o in order]
        proj = self.project.plugin.lower() if self.project else None
        tail = list(order[len(old):]) if len(new) > len(old) and new[:len(old)] == old else None
        if tail and self.state == 'ready' and self.adding is None and proj not in new[len(old):]:
            self.adding = tail
            self.last_add = None
            threading.Thread(target=self._add_safe, args=(tail,), daemon=True).start()
            return {'mode': 'added', 'added': tail}
        self.state = 'loading'
        self.load_async()
        return {'mode': 'reload'}

    def _add_safe(self, names):
        try:
            self._add(names)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print('Could not add %s to what is loaded (%s); reading everything again.' % (', '.join(names), e))
            self.adding = None
            self.state = 'loading'
            self._load_safe()
        finally:
            self.adding = None

    def _add(self, names):
        """Append these plugins (the end of the new load order) to the index without a full reload."""
        t0 = time.time()
        start = len(self.recs)
        content = [c for c in names if os.path.splitext(c)[1].lower() in PLUGIN_EXTS]
        before = [p['name'] for p in self.plugins if not p.get('lua_only') and not p.get('project')]
        # new list objects: whatever keyed a cache on this load's lists starts afresh
        self.recs = list(self.recs)
        self.search_text = list(self.search_text)
        first = len(self.plugins)
        self._read_plugins(content, before + content, before, before_project=self.proj_pidx is not None)
        for s in names:
            if s not in content:
                self.plugins.append(self._lua_entry(s))
                self.files.append(None)
        self._resolve_effect_names(start)
        winner = bytearray(len(self.recs))
        for lst in self.by_key.values():
            winner[lst[-1]] = 1
        self.winner = winner
        self.cfg_content_all = list(getattr(self, 'cfg_content_all', [])) + list(names)
        self.config['content'] = list(self.config.get('content', [])) + list(names)
        if self.project:
            self.sync_project()
            try:
                import editing
                editing.build(self)
            except Exception as e:
                print('Could not write the plugin:', e)
        n = len(self.recs) - start
        self.last_add = {'names': list(names), 'records': n, 'seconds': round(time.time() - t0, 1),
                         'problems': [{'plugin': p['name'], 'text': t} for p in self.plugins[first:]
                                      for t in p.get('problems', [])],
                         'stamp': time.time()}
        self.progress = {'step': 'Done', 'done': 1, 'total': 1}

    # ---------- project overlay ----------
    def attach_project(self, project):
        self.project = project
        if self.proj_pidx is None:
            self.plugins.append({'name': project.plugin, 'path': None,
                                 'header': {'masters': [], 'author': project.author,
                                            'description': project.description},
                                 'counts': {}, 'records': 0, 'size': 0, 'overrides': 0, 'new': 0, 'dirty': 0,
                                 'missing_assets': 0, 'problems': [], 'project': True})
            self.files.append(VirtualFile())
            self.proj_pidx = len(self.plugins) - 1
        self.sync_project()

    def plugin_index(self, name_lower):
        for n, p in enumerate(self.plugins):
            if p['name'].lower() == name_lower and not p.get('lua_only'):
                return n
        return None

    def compute_masters(self):
        # only the files the mod really uses (see release.lean_masters); the broad list below is the fallback
        try:
            import release
            return release.lean_masters(self)
        except Exception as e:
            print('Could not work out the lean master list (%s); using the full one.' % e)
            return self._compute_masters_full()

    def _compute_masters_full(self):
        p = self.project
        need = set()
        for r in p.records.values():
            for v in self.by_key.get((r['tag'], r['key']), []):
                if self.recs[v][3] != self.proj_pidx and v not in self.dead:
                    need.add(self.recs[v][3])
        for ck, c in p.cells.items():
            if not c['refs']:
                continue
            for v in self.by_key.get(('CELL', ck), []):
                if self.recs[v][3] != self.proj_pidx and v not in self.dead:
                    need.add(self.recs[v][3])
            for r in c['refs'].values():
                if r['origin'] != p.plugin.lower():
                    pi = self.plugin_index(r['origin'])
                    if pi is not None:
                        need.add(pi)
                else:
                    # something we placed: the plugin that defines the object is needed too
                    from project import unb64
                    for t, d in r['subs']:
                        if t == 'NAME':
                            ri = self.resolve_id(zstr(unb64(d)))
                            if ri is not None and self.recs[ri][3] != self.proj_pidx:
                                need.add(self.recs[ri][3])
                            break
        stack = list(need)
        while stack:
            pi = stack.pop()
            for m in self.plugins[pi]['header'].get('masters', []):
                mi = self.plugin_index(m.lower())
                if mi is not None and mi not in need:
                    need.add(mi)
                    stack.append(mi)
        out = []
        for i in sorted(need):
            pl = self.plugins[i]
            out.append((pl['name'], pl['size'] or (os.path.getsize(pl['path']) if pl['path'] else 0)))
        return out

    def sync_project(self):
        from project import unb64
        p = self.project
        masters = self.compute_masters()
        self.proj_masters = masters
        self.plugins[self.proj_pidx]['header']['masters'] = [m for m, _s in masters]
        lower = [m.lower() for m, _s in masters]
        wanted = {}
        for r in p.records.values():
            wanted[(r['tag'], r['key'])] = (r['flags'], unb64(r['data']))
        for ck, c in p.cells.items():
            if c['refs'] or c.get('props'):      # (props: the place's own settings were changed, e.g. lighting)
                wanted[('CELL', ck)] = (c.get('flags', 0), p.cell_bytes(c, lower))
        for k in list(self.overlay):
            if k not in wanted:
                self._overlay_remove(k)
        # DIAL before INFO so lines attach to their topic
        for k in sorted(wanted, key=lambda k: k[0] == 'INFO'):
            flags, data = wanted[k]
            self._overlay_put(k, flags, data)
        self.plugins[self.proj_pidx]['records'] = len(wanted)

    def _overlay_put(self, k, flags, data):
        tag, key = k
        vf = self.files[self.proj_pidx]
        if tag == 'CELL':
            rid, name, extra, _key = self._cell_info(data)
        elif tag == 'INFO':
            inam, text, speaker = '', '', ''
            for st, sd in iter_subrecords(data):
                if st == 'INAM':
                    inam = zstr(sd)
                elif st == 'NAME':
                    text = zstr(sd)
                elif st == 'ONAM' and not speaker:
                    speaker = zstr(sd)
            dial_id = key.split('|', 1)[0]
            dlst = self.by_key.get(('DIAL', dial_id)) or []
            dial_name = self.recs[dlst[-1]][1] if dlst else dial_id
            rid, name, extra = inam, text[:300], (dial_name + ' ' + speaker).strip()
        else:
            rid, name, extra = _id_of(tag, data)
            if tag == 'MGEF' and rid.lstrip('-').isdigit():
                name = self.effect_names.get(int(rid), '')
            elif tag == 'SKIL' and rid.isdigit() and int(rid) < len(SKILLS):
                name = SKILLS[int(rid)]
        ri = self.overlay.get(k)
        if ri is None:
            ri = len(self.recs)
            lst = self.by_key[k]
            if lst:
                self.winner[lst[-1]] = 0
            lst.append(ri)
            self.winner.append(1)
            self.recs.append(None)
            self.search_text.append('')
            if rid:
                self.by_id[rid.lower()].append(ri)
            self.overlay[k] = ri
            self.type_counts[tag] += 1
            if tag == 'INFO':
                dlst = self.by_key.get(('DIAL', key.split('|', 1)[0])) or []
                if dlst:
                    self.info_dial[ri] = dlst[-1]
                    self.dial_infos[dlst[-1]].append(ri)
        vf.slots[ri] = (tag, flags, bytes(data))
        self.recs[ri] = (tag, rid, name, self.proj_pidx, ri, extra, flags, key)
        self.search_text[ri] = ('%s\t%s\t%s' % (rid, name, extra)).lower()
        if tag == 'CELL':
            for m in CELL_REF_RE.finditer(data):
                size = struct.unpack('<I', m.group(1))[0]
                self.used_in[zstr(data[m.end():m.end() + size]).lower()].add(ri)
        elif tag in ('NPC_', 'CREA', 'CONT', 'LEVI', 'LEVC'):
            for st, sd in iter_subrecords(data):
                if st == 'NPCO' and len(sd) >= 36:
                    self.used_in[zstr(sd[4:36]).lower()].add(ri)
                elif st == 'NPCS' or (tag in ('LEVI', 'LEVC') and st in ('INAM', 'CNAM')):
                    self.used_in[zstr(sd).lower()].add(ri)

    def _overlay_remove(self, k):
        ri = self.overlay.pop(k)
        lst = self.by_key.get(k, [])
        if ri in lst:
            lst.remove(ri)
        self.winner[ri] = 0
        if lst:
            self.winner[lst[-1]] = 1
        self.dead.add(ri)
        rid = self.recs[ri][1].lower()
        if ri in self.by_id.get(rid, []):
            self.by_id[rid].remove(ri)
        self.type_counts[k[0]] -= 1
        self.files[self.proj_pidx].slots.pop(ri, None)

    def ref_origin(self, pidx, frmr):
        upper = frmr >> 24
        masters = self.plugins[pidx]['header'].get('masters', [])
        if upper and upper <= len(masters):
            return masters[upper - 1].lower()
        return self.plugins[pidx]['name'].lower()

    def cell_refs(self, cell_key, without_project=False):
        """All references in a cell merged across plugins: refkey -> {origin, idx, subs, pidx}."""
        from project import split_cell
        refs = {}
        header = None
        for v in self.by_key.get(('CELL', cell_key), []):
            if v in self.dead:
                continue
            r = self.recs[v]
            if without_project and r[3] == self.proj_pidx:
                continue
            _t, _f, data = self.files[r[3]].record_at(r[4])
            hdr, lst = split_cell(data)
            if r[3] != self.proj_pidx:
                header = (hdr, r[6])
            for ref in lst:
                origin = self.ref_origin(r[3], ref['frmr'])
                idx = ref['frmr'] & 0xFFFFFF
                refs['%s|%d' % (origin, idx)] = {'origin': origin, 'idx': idx, 'subs': ref['subs'], 'pidx': r[3]}
        return refs, header

    def resolve_id(self, rid):
        lst = self.by_id.get(rid.lower()) if rid else None
        if not lst:
            return None
        for i in reversed(lst):
            if self.winner[i] and self.recs[i][0] not in ('INFO', 'CELL', 'DIAL'):
                return i
        return None

    # ---------- queries ----------
    def search(self, q='', types=None, plugin=None, offset=0, limit=200, only_new=False, sort=''):
        terms = [t for t in q.lower().split() if t]
        recs, st = self.recs, self.search_text
        types = set(types) if types else None
        pidx = None
        if plugin not in (None, ''):
            pidx = int(plugin)
        winner = self.winner
        # Show only the winning (last-loaded) version of each record unless filtering by plugin
        # (while a plugin is being added at the end of the load order the lists grow; the winners
        # are settled last, so only what has them is searched)
        matches = []
        for i in range(min(len(recs), len(winner))):
            r = recs[i]
            if types and r[0] not in types:
                continue
            if pidx is None:
                if not winner[i]:
                    continue
            elif r[3] != pidx or i in self.dead:
                continue
            if terms:
                s = st[i]
                ok = True
                for t in terms:
                    if t not in s:
                        ok = False
                        break
                if not ok:
                    continue
            matches.append(i)
        if terms:
            q1 = terms[0]

            def rank(i):
                rid = recs[i][1].lower()
                nm = (recs[i][2] or '').lower()
                if rid == q1 or nm == q1:
                    return 0
                if rid.startswith(q1) or nm.startswith(q1):
                    return 1
                return 2
            matches.sort(key=rank)
        # the ones the game places most first (the placing search: the common bookshelf before its
        # twenty variants, so there is less to scroll past)
        if sort == 'uses':
            used = self.used_in
            matches.sort(key=lambda i: -len(used.get(recs[i][1].lower(), ())))
        # sorted by a column of the list ("-name": the other way round)
        col = (sort or '').lstrip('-')
        if col in ('id', 'name', 'type', 'plugin', 'extra'):
            plugins = self.plugins
            get = {'id': lambda i: recs[i][1].lower(), 'name': lambda i: (recs[i][2] or recs[i][1]).lower(),
                   'type': lambda i: recs[i][0], 'plugin': lambda i: plugins[recs[i][3]]['name'].lower(),
                   'extra': lambda i: str(recs[i][5] or '').lower()}[col]
            matches.sort(key=get, reverse=sort.startswith('-'))
        return {'total': len(matches), 'rows': [self._row(i) for i in matches[offset:offset + limit]]}

    def key_of(self, i):
        r = self.recs[i]
        return (r[0], r[7])

    def versions(self, i):
        return self.by_key.get(self.key_of(i)) or [i]

    def _row(self, i):
        r = self.recs[i]
        lst = self.versions(i)
        return {'i': i, 'type': r[0], 'id': r[1], 'name': r[2], 'plugin': self.plugins[r[3]]['name'],
                'extra': r[5], 'versions': len(lst), 'deleted': bool(r[6] & 0x20),
                'mine': r[3] == self.proj_pidx}

    def record(self, i):
        from decode import decode_record
        return decode_record(self, i)

    def summary(self):
        return {
            'state': self.state, 'progress': self.progress, 'error': self.error,
            'records': len(self.recs), 'seconds': getattr(self, 'load_seconds', None),
            'from_cache': getattr(self, 'load_from_cache', 0),
            # plugins being added at the end of the load order right now, and what the last add did
            'adding': self.adding, 'last_add': self.last_add,
            # (what went wrong while reading the load order, said on screen when the load ends: a Nexus user
            # with a 2,000-plugin list wished the Workshop had told them about a missing esp instead of
            # "running in the background silently"; it was only on the Health check page)
            'load_problems': [{'plugin': p['name'], 'text': t} for p in self.plugins for t in p.get('problems', [])][:12],
            'types': [{'group': g, 'types': [{'tag': t, 'label': TYPE_NAMES[t], 'count': self.type_counts.get(t, 0)}
                                             for t in ts]} for g, ts in TYPE_GROUPS],
            'plugins': [{'index': n, 'name': p['name'], 'records': p['records'], 'lua_only': p.get('lua_only', False),
                         'problems': p['problems'], 'project': p.get('project', False)}
                        for n, p in enumerate(self.plugins)],
            'project': self.project_summary(),
        }

    def project_summary(self):
        p = self.project
        if not p:
            return None
        stack = getattr(p, 'undo_stack', None)
        if stack:
            import editing
            last = stack[-1]
            undo_note = editing.note_label(p, last[1], last[2] if len(last) > 2 else None)
        else:
            undo_note = ''
        return {'name': p.name, 'plugin': p.plugin, 'author': p.author, 'description': p.description,
                'changes': p.change_count(), 'pidx': self.proj_pidx,
                'masters': [m for m, _s in getattr(self, 'proj_masters', [])],
                'undo_depth': len(stack or []),
                'plugin_pending': bool(getattr(p, 'pending_write', None)),
                'undo_note': undo_note,
                # a plugin opened as the mod itself (adopt.py): saved into that file; a plain .esp takes no Lua
                'source': getattr(p, 'source', None), 'plain_esp': not p.lua_allowed(),
                'enabled_in_cfg': p.plugin.lower() in [c.lower() for c in getattr(self, 'cfg_content_all', [])]}
