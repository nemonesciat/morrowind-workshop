"""MWScript: a checker that explains mistakes in plain words, a function reference, and saving scripts.

OpenMW compiles scripts from their text when the game starts, so a script only needs its text,
its name and its list of local variables. The checker here catches the usual mistakes (missing
endif, undeclared variables, unknown IDs, misspelled commands) before the game does."""
import re
import struct

from editing import EditError, commit, _require_project
from esm import ENC, iter_subrecords, zstr
from project import join_subs, zs

# ------------------------------------------------------------------ the function reference
# args: codes for each argument, required | optional. i object/any ID, q quest or topic, S script, c cell name,
# f faction, p spell, s text/sound/animation, n number or variable, x axis (X, Y or Z), * any number of anything
# value: True if it gives back a value (can be used in "if" and "set ... to")
F = {}
CATS = {}


def _f(cat, name, args='', value=False, desc='', ref=True):
    F[name.lower()] = {'name': name, 'args': args, 'value': value, 'cat': cat, 'desc': desc, 'ref': ref}
    CATS.setdefault(cat, []).append(name)


E = 'Events (use in "if")'
for _n, _d in [('OnActivate', 'True once when the player (or anyone) activates this object. While a script uses OnActivate, the object no longer does its normal thing unless you call Activate.'),
               ('OnDeath', 'True once when this actor dies.'), ('OnKnockout', 'True once when this actor is knocked out.'),
               ('OnMurder', 'True once when this actor is murdered.'), ('OnPCAdd', 'True once when the player picks this item up (or gets it).'),
               ('OnPCDrop', 'True once when the player drops this item.'), ('OnPCEquip', 'True once when the player equips this item.'),
               ('OnPCHitMe', 'True once when the player hits this actor.'), ('OnPCRepair', 'True once when the player repairs this item.'),
               ('OnPCSoulGemUse', 'True once when the player uses this soul gem.'), ('OnRepair', 'True once when this item is repaired.'),
               ('MenuMode', 'True while a menu (inventory, dialogue, ...) is open. Most scripts start with: if ( MenuMode == 1 ) return endif'),
               ('CellChanged', 'True for one frame after the player moves to another place.'),
               ('SayDone', 'True when this actor has finished speaking.'),
               ('GetButtonPressed', 'Which button of the last MessageBox was clicked (0, 1, ...), or -1 while none yet.'),
               ('ScriptRunning', 'True if a global script is running. ScriptRunning MyScript'),
               ('HitOnMe', 'True once when this actor is hit with the given weapon. HitOnMe "iron dagger"'),
               ('HitAttemptOnMe', 'True once when someone tries to hit this actor with the given weapon.')]:
    _f(E, _n, {'ScriptRunning': 'S', 'HitOnMe': 'i', 'HitAttemptOnMe': 'i'}.get(_n, ''), True, _d)

I = 'Items'
_f(I, 'AddItem', 'in', desc='Give an item: player->AddItem "gold_001" 50')
_f(I, 'RemoveItem', 'in', desc='Take an item away: player->RemoveItem "misc_quill" 1')
_f(I, 'GetItemCount', 'i', True, 'How many of an item they carry: if ( player->GetItemCount "misc_quill" > 0 )')
_f(I, 'Equip', 'i', desc='Make this actor equip an item they carry.')
_f(I, 'HasItemEquipped', 'i', True, 'True if this actor wears/holds the item.')
_f(I, 'Drop', 'in', desc='This actor drops an item.')
_f(I, 'AddSoulGem', 'ii', desc='Give a filled soul gem: AddSoulGem "creature id" "Misc_SoulGem_Grand"')
_f(I, 'RemoveSoulGem', 'i|n', desc='Remove a soul gem filled with this creature.')
_f(I, 'HasSoulGem', 'i', True, 'Number of soul gems filled with this creature.')
_f(I, 'DropSoulGem', 'i', desc='Drop a soul gem filled with this creature.')
_f(I, 'GetArmorType', 'n', True, 'Kind of armor worn in a slot.')
_f(I, 'GetWeaponType', '', True, 'Kind of weapon held (-1 none).')
_f(I, 'AddToLevItem', 'sin', desc='Add an item to a leveled list: AddToLevItem "list" "item" level', ref=False)
_f(I, 'RemoveFromLevItem', 'si|n', desc='Remove an item from a leveled list.', ref=False)
_f(I, 'AddToLevCreature', 'sin', desc='Add a creature to a leveled creature list.', ref=False)
_f(I, 'RemoveFromLevCreature', 'si|n', desc='Remove a creature from a leveled creature list.', ref=False)

Q = 'Quests & dialogue'
_f(Q, 'Journal', 'qn|n', desc='Set a quest stage (adds the journal entry): Journal "MyQuest" 10', ref=False)
_f(Q, 'SetJournalIndex', 'qn', desc='Set a quest stage without adding a journal entry.', ref=False)
_f(Q, 'GetJournalIndex', 'q', True, 'The current stage of a quest: if ( GetJournalIndex "MyQuest" >= 10 )', ref=False)
_f(Q, 'AddTopic', 'q', desc='Let the player ask about a topic: AddTopic "lost ring"', ref=False)
_f(Q, 'ForceGreeting', '', desc='This actor walks up and starts talking to the player.')
_f(Q, 'Goodbye', '', desc='(In dialogue results) end the conversation; the player must click Goodbye.', ref=False)
_f(Q, 'Choice', '*', desc='(In dialogue results) offer answers: Choice "Yes" 1 "No" 2', ref=False)
_f(Q, 'ClearInfoActor', '', desc='(In dialogue results) don\'t show this line in the journal under the speaker.', ref=False)
_f(Q, 'GetDisposition', '', True, 'How much this actor likes the player (0-100).')
_f(Q, 'SetDisposition', 'n', desc='Set how much this actor likes the player.')
_f(Q, 'ModDisposition', 'n', desc='Change how much this actor likes the player by an amount.')
_f(Q, 'Say', 'ss', desc='Play a voice file with a subtitle: Say "vo\\d\\m\\Hlo_DM001.mp3" "Hello."')
_f(Q, 'MessageBox', '*', desc='Show a message: MessageBox "Hello %g" myvar   (buttons: MessageBox "Open it?" "Yes" "No")', ref=False)
_f(Q, 'GetFactionReaction', 'ff', True, 'How two factions feel about each other.', ref=False)
_f(Q, 'SetFactionReaction', 'ffn', desc='Set how two factions feel about each other.', ref=False)
_f(Q, 'ModFactionReaction', 'ffn', desc='Change how two factions feel about each other.', ref=False)

A = 'Actors & AI'
_f(A, 'AIWander', 'nnn|nnnnnnnnnn', desc='Wander: AIWander range duration time [idle chances…]. AIWander 0 0 0 = stand still.')
_f(A, 'AITravel', 'nnn|nnnnnnnnnnn', desc='Walk to a spot: AITravel x y z')
_f(A, 'AIFollow', 'innnn|nnnnnnnnnnnn', desc='Follow someone: AIFollow player 0 0 0 0')
_f(A, 'AIFollowCell', 'icnnnn|nnnnnnnnnnnn', desc='Follow someone to a place: AIFollowCell player "Balmora" 0 0 0 0')
_f(A, 'AIEscort', 'innnn|nnnnnnnnnnnn', desc='Lead someone to a spot: AIEscort player duration x y z')
_f(A, 'AIEscortCell', 'icnnnn|nnnnnnnnnnnn', desc='Lead someone to a spot in a place.')
_f(A, 'AIActivate', 'i|n', desc='Go and use an object.')
_f(A, 'GetAIPackageDone', '', True, 'True when the current AI activity is finished.')
_f(A, 'GetCurrentAIPackage', '', True, 'Which AI activity is running (-1 none, 0 wander, 1 travel, 2 escort, 3 follow, 4 activate).')
_f(A, 'StartCombat', 'i', desc='This actor attacks someone: StartCombat player')
_f(A, 'StopCombat', '|i', desc='This actor stops fighting.')
_f(A, 'Face', 'nn|n', desc='Turn to face a spot: Face x y')
_f(A, 'GetTarget', 'i', True, 'True if this actor is fighting that one.')
_f(A, 'GetAttacked', '', True, 'True if this actor has been attacked.')
_f(A, 'GetDetected', 'i', True, 'True if this actor can see/hear that one.')
_f(A, 'GetLineOfSight', 'i', True, 'True if there is a clear line between them.')
_f(A, 'GetLOS', 'i', True, 'Same as GetLineOfSight.')
_f(A, 'GetDeadCount', 'i', True, 'How many of this NPC/creature have died: if ( GetDeadCount "fargoth" > 0 )', ref=False)
_f(A, 'Resurrect', '', desc='Bring this actor back to life.')
_f(A, 'GetRace', 'i', True, 'True if this actor is of that race: if ( player->GetRace "Dark Elf" == 1 )')
_f(A, 'GetLevel', '', True, 'This actor\'s level.')
_f(A, 'SetLevel', 'n', desc='Set this actor\'s level.')
_f(A, 'GetSpell', 'p', True, 'True if this actor knows the spell.')
_f(A, 'AddSpell', 'p', desc='Teach a spell (or give an ability/disease): player->AddSpell "fireball"')
_f(A, 'RemoveSpell', 'p', desc='Forget a spell / remove an ability or disease.')
_f(A, 'Cast', 'pi', desc='Cast a spell at someone: Cast "fireball" player')
_f(A, 'ExplodeSpell', 'p', desc='Cast a spell that hits everyone around.')
_f(A, 'GetEffect', 's', True, 'True if this actor is under a magic effect: GetEffect sEffectWaterWalking')
_f(A, 'GetSpellEffects', 'p', True, 'True if this actor is affected by that spell.')
_f(A, 'RemoveEffects', 'n', desc='Remove all magic effects of one kind (effect number).')
_f(A, 'RemoveSpellEffects', 'p', desc='Remove the effects of one spell.')
_f(A, 'GetSpellReadied', '', True, 'True if this actor has a spell ready.')
_f(A, 'GetWeaponDrawn', '', True, 'True if this actor has a weapon out.')
_f(A, 'GetStandingPC', '', True, 'True if the player stands on this object.')
_f(A, 'GetStandingActor', '', True, 'True if any actor stands on this object.')
_f(A, 'GetCollidingPC', '', True, 'True if the player bumps into this object.')
_f(A, 'GetCollidingActor', '', True, 'True if any actor bumps into this object.')
_f(A, 'HurtStandingActor', 'n', desc='Hurt whoever stands on this object (per second).')
_f(A, 'HurtCollidingActor', 'n', desc='Hurt whoever bumps into this object (per second).')
_f(A, 'Fall', '', desc='This actor falls.')
_f(A, 'PlayGroup', 's|n', desc='Play an animation: PlayGroup idle2')
_f(A, 'LoopGroup', 'sn|n', desc='Play an animation a number of times.')
_f(A, 'SkipAnim', '', desc='Skip the next animation frame.')
_f(A, 'ForceRun', '', desc='This actor runs.')
_f(A, 'ClearForceRun', '', desc='This actor stops being made to run.')
_f(A, 'ForceSneak', '', desc='This actor sneaks.')
_f(A, 'ClearForceSneak', '', desc='This actor stops being made to sneak.')
_f(A, 'ForceJump', '', desc='This actor jumps.')
_f(A, 'ClearForceJump', '', desc='')
_f(A, 'ForceMoveJump', '', desc='')
_f(A, 'ClearForceMoveJump', '', desc='')
_f(A, 'GetForceRun', '', True, '')
_f(A, 'GetForceSneak', '', True, '')
_f(A, 'GetForceJump', '', True, '')
_f(A, 'GetForceMoveJump', '', True, '')
_f(A, 'BecomeWerewolf', '', desc='Turn into a werewolf.')
_f(A, 'UndoWerewolf', '', desc='Turn back from a werewolf.')
_f(A, 'IsWerewolf', '', True, 'True while a werewolf.')
_f(A, 'GetWerewolfKills', '', True, 'How many people the werewolf player has killed.', ref=False)
_f(A, 'SetWerewolfAcrobatics', '', desc='')
_f(A, 'GetBlightDisease', '', True, 'True if this actor has a blight disease.')
_f(A, 'GetCommonDisease', '', True, 'True if this actor has a common disease.')
_f(A, 'GetHealthGetRatio', '', True, 'Health as a fraction of full health (0 to 1).')
_f(A, 'ModCurrentHealth', 'n', desc='Heal or hurt by an amount (without changing the maximum).')
_f(A, 'ModCurrentMagicka', 'n', desc='Restore or drain magicka by an amount.')
_f(A, 'ModCurrentFatigue', 'n', desc='Restore or drain fatigue by an amount.')
_f(A, 'SetDelete', 'n', desc='Remove this object for good (SetDelete 1). Use on things placed by scripts.')

ST = 'Stats'
for _s in ['Strength', 'Intelligence', 'Willpower', 'Agility', 'Speed', 'Endurance', 'Personality', 'Luck',
           'Block', 'Armorer', 'MediumArmor', 'HeavyArmor', 'BluntWeapon', 'LongBlade', 'Axe', 'Spear', 'Athletics',
           'Enchant', 'Destruction', 'Alteration', 'Illusion', 'Conjuration', 'Mysticism', 'Restoration', 'Alchemy',
           'Unarmored', 'Security', 'Sneak', 'Acrobatics', 'LightArmor', 'ShortBlade', 'Marksman', 'Mercantile',
           'Speechcraft', 'HandToHand', 'Health', 'Magicka', 'Fatigue', 'Fight', 'Flee', 'Alarm', 'Hello',
           'Reputation', 'Scale', 'AttackBonus', 'DefendBonus', 'MagicBonus',
           'ResistBlight', 'ResistCorprus', 'ResistDisease', 'ResistFire', 'ResistFrost', 'ResistMagicka',
           'ResistNormalWeapons', 'ResistParalysis', 'ResistPoison', 'ResistShock', 'WaterBreathing', 'WaterWalking',
           'SwimSpeed', 'Chameleon', 'Invisible', 'Paralysis', 'Silence', 'SuperJump', 'Blindness', 'Flying',
           'ArmorBonus', 'CastPenalty']:
    _f(ST, 'Get' + _s, '', True, 'This actor\'s %s.' % _s)
    _f(ST, 'Set' + _s, 'n', desc='Set this actor\'s %s.' % _s)
    _f(ST, 'Mod' + _s, 'n', desc='Change this actor\'s %s by an amount.' % _s)

M = 'Moving things'
_f(M, 'Enable', '|s', desc='Make this object appear (if it was disabled).')
_f(M, 'Disable', '|s', desc='Make this object disappear (it still exists; Enable brings it back).')
_f(M, 'GetDisabled', '', True, 'True if this object is disabled.')
_f(M, 'Activate', '', desc='Do this object\'s normal action (open the door, pick up the item…). Used with OnActivate.')
_f(M, 'Lock', '|n', desc='Lock this door or container (optionally with a lock level).')
_f(M, 'Unlock', '', desc='Unlock this door or container.')
_f(M, 'GetLocked', '', True, 'True if locked.')
_f(M, 'GetPos', 'x', True, 'Position along an axis: GetPos Z')
_f(M, 'SetPos', 'xn', desc='Move along an axis to a value: SetPos Z 1200')
_f(M, 'GetAngle', 'x', True, 'Turned angle around an axis (degrees).')
_f(M, 'SetAngle', 'xn', desc='Turn to an angle (degrees): SetAngle Z 90')
_f(M, 'GetStartingPos', 'x', True, 'Where this object started.')
_f(M, 'GetStartingAngle', 'x', True, 'How this object was turned at the start.')
_f(M, 'SetAtStart', '', desc='Put this object back where it started.')
_f(M, 'Move', 'xn', desc='Move along its own axis, per second: Move Z 50 (a rising platform)')
_f(M, 'MoveWorld', 'xn', desc='Move along a world axis, per second.')
_f(M, 'Rotate', 'xn', desc='Turn around its own axis, per second: Rotate Z 30')
_f(M, 'RotateWorld', 'xn', desc='Turn around a world axis, per second.')
_f(M, 'Position', 'nnnn', desc='Move to a spot outdoors: Position x y z angle')
_f(M, 'PositionCell', 'nnnnc', desc='Move to a spot in a place: PositionCell x y z angle "Balmora, Guild of Mages"')
_f(M, 'PlaceAtMe', 'innn', desc='Make a new object next to this one: PlaceAtMe "rat" 1 128 0   (count distance direction)')
_f(M, 'PlaceAtPC', 'innn', desc='Make a new object next to the player.', ref=False)
_f(M, 'PlaceItem', 'innnn', desc='Make a new object at a spot outdoors: PlaceItem "id" x y z angle', ref=False)
_f(M, 'PlaceItemCell', 'icnnnn', desc='Make a new object at a spot in a place.', ref=False)
_f(M, 'GetDistance', 'i', True, 'Distance to another object: if ( GetDistance player < 256 )')
_f(M, 'GetInterior', '', True, 'True if this object is indoors.')
_f(M, 'GetPCCell', 'c', True, 'True if the player is in a place (names starting with the text match): if ( GetPCCell "Balmora" )', ref=False)
_f(M, 'GetWaterLevel', '', True, 'Water height in this place.', ref=False)
_f(M, 'SetWaterLevel', 'n', desc='Set the water height in this place.', ref=False)
_f(M, 'ModWaterLevel', 'n', desc='Change the water height, per second.', ref=False)

P = 'Player & factions'
_f(P, 'PCJoinFaction', '|f', desc='Make the player join a faction.')
_f(P, 'PCRaiseRank', '|f', desc='Promote the player in a faction.')
_f(P, 'PCLowerRank', '|f', desc='Demote the player in a faction.')
_f(P, 'PCExpell', '|f', desc='Throw the player out of a faction.')
_f(P, 'PCClearExpelled', '|f', desc='Let the player back into a faction.')
_f(P, 'PCExpelled', '|f', True, 'True if the player was thrown out of the faction.')
_f(P, 'GetPCRank', '|f', True, 'The player\'s rank in a faction (-1 not a member).')
_f(P, 'GetPCFacRep', '|f', True, 'The player\'s reputation in a faction.')
_f(P, 'SetPCFacRep', 'n|f', desc='Set the player\'s reputation in a faction.')
_f(P, 'ModPCFacRep', 'n|f', desc='Change the player\'s reputation in a faction.')
_f(P, 'RaiseRank', '', desc='Promote this NPC in their faction.')
_f(P, 'LowerRank', '', desc='Demote this NPC in their faction.')
_f(P, 'GetPCCrimeLevel', '', True, 'The player\'s bounty.', ref=False)
_f(P, 'SetPCCrimeLevel', 'n', desc='Set the player\'s bounty.', ref=False)
_f(P, 'ModPCCrimeLevel', 'n', desc='Change the player\'s bounty.', ref=False)
_f(P, 'PayFine', '', desc='The player pays their bounty.', ref=False)
_f(P, 'PayFineThief', '', desc='The player pays their bounty (thieves guild).', ref=False)
_f(P, 'GoToJail', '', desc='Send the player to jail.', ref=False)
_f(P, 'GetPCInJail', '', True, '', ref=False)
_f(P, 'GetPCTraveling', '', True, 'True while the player is travelling (caravan, boat…).', ref=False)
_f(P, 'GetPCSleep', '', True, 'True while the player sleeps or waits.', ref=False)
_f(P, 'GetPCRunning', '', True, '', ref=False)
_f(P, 'GetPCSneaking', '', True, '', ref=False)
_f(P, 'GetPCJumping', '', True, '', ref=False)
_f(P, 'GetPCVisionBonus', '', True, '', ref=False)
_f(P, 'WakeUpPC', '', desc='Wake the player up.', ref=False)
_f(P, 'PCForce1stPerson', '', ref=False)
_f(P, 'PCForce3rdPerson', '', ref=False)
_f(P, 'PCGet3rdPerson', '', True, ref=False)

W = 'World, time & sound'
_f(W, 'PlaySound', 's', desc='Play a sound: PlaySound "Door Stone Open"', ref=False)
_f(W, 'PlaySoundVP', 'snn', desc='Play a sound with volume and pitch.', ref=False)
_f(W, 'PlaySound3D', 's', desc='Play a sound from this object.')
_f(W, 'PlaySound3DVP', 'snn', desc='')
_f(W, 'PlayLoopSound3D', 's', desc='Keep playing a sound from this object.')
_f(W, 'PlayLoopSound3DVP', 'snn', desc='')
_f(W, 'StopSound', 's', desc='Stop a sound.')
_f(W, 'GetSoundPlaying', 's', True, 'True while a sound plays.')
_f(W, 'StreamMusic', 's', desc='Play a music file: StreamMusic "Explore\\mx_explore_1.mp3"', ref=False)
_f(W, 'PlayBink', 'sn', desc='Play a video.', ref=False)
_f(W, 'ChangeWeather', 'sn', desc='Change the weather in a region: ChangeWeather "Bitter Coast Region" 4', ref=False)
_f(W, 'GetCurrentWeather', '', True, 'Current weather (0 clear … 9 blizzard).', ref=False)
_f(W, 'ModRegion', 's*', desc='Change weather chances of a region.', ref=False)
_f(W, 'GetMasserPhase', '', True, '', ref=False)
_f(W, 'GetSecundaPhase', '', True, '', ref=False)
_f(W, 'TurnMoonRed', '', ref=False)
_f(W, 'TurnMoonWhite', '', ref=False)
_f(W, 'FadeIn', 'n', desc='Fade the screen in over seconds.', ref=False)
_f(W, 'FadeOut', 'n', desc='Fade the screen to black over seconds.', ref=False)
_f(W, 'FadeTo', 'nn', desc='', ref=False)
_f(W, 'GetSecondsPassed', '', True, 'Seconds since the last frame; add it up to make a timer.', ref=False)
_f(W, 'Random', 'n', True, 'A random whole number from 0 up to (not including) the number: set x to Random 100', ref=False)
_f(W, 'GetSquareRoot', 'n', True, '', ref=False)
_f(W, 'FillMap', '', ref=False)
_f(W, 'ShowMap', 's', desc='Mark a place on the player\'s map.', ref=False)
_f(W, 'CenterOnCell', 'c', desc='(Console) jump to a place.', ref=False)
_f(W, 'COC', 'c', desc='(Console) jump to a place.', ref=False)

C = 'Control & menus'
for _n in ['DisablePlayerControls', 'EnablePlayerControls', 'DisablePlayerFighting', 'EnablePlayerFighting',
           'DisablePlayerJumping', 'EnablePlayerJumping', 'DisablePlayerLooking', 'EnablePlayerLooking',
           'DisablePlayerMagic', 'EnablePlayerMagic', 'DisablePlayerViewSwitch', 'EnablePlayerViewSwitch',
           'DisableTeleporting', 'EnableTeleporting', 'DisableVanityMode', 'EnableVanityMode', 'DisableLevitation',
           'EnableLevitation', 'EnableRest', 'DisableRest', 'EnableBirthMenu', 'EnableClassMenu', 'EnableNameMenu',
           'EnableRaceMenu', 'EnableStatReviewMenu', 'EnableInventoryMenu', 'EnableMagicMenu', 'EnableMapMenu',
           'EnableStatsMenu', 'EnableLevelupMenu', 'ShowRestMenu', 'MenuTest', 'XBox']:
    _f(C, _n, '|n' if _n == 'MenuTest' else '', _n.startswith('XBox'), ref=False)
for _n in ['GetPlayerControlsDisabled', 'GetPlayerFightingDisabled', 'GetPlayerJumpingDisabled',
           'GetPlayerLookingDisabled', 'GetPlayerMagicDisabled', 'GetPlayerViewSwitchDisabled']:
    _f(C, _n, '', True, ref=False)

SC = 'Scripts'
_f(SC, 'StartScript', 'S', desc='Start a global script: StartScript MyQuestScript', ref=False)
_f(SC, 'StopScript', 'S', desc='Stop a global script (a script can stop itself).', ref=False)
_f(SC, 'DontSaveObject', '', desc='', ref=False)
_f(SC, 'ToggleAI', '', ref=False)
_f(SC, 'ToggleCollision', '', ref=False)
_f(SC, 'ResetActors', '', ref=False)
_f(SC, 'RA', '', ref=False)
_f(SC, 'FixMe', '', ref=False)

KEYWORDS = {'begin', 'end', 'short', 'long', 'float', 'set', 'to', 'if', 'elseif', 'else', 'endif', 'while',
            'endwhile', 'return'}
DECL = ('short', 'long', 'float')
# IDs may contain - and ' (e.g. TR_m3-278_a_dwrvhelm); numbers come before words so ".5" stays a number
TOKEN = re.compile(r'[\s\x00\[\]]*(?:(?P<str>"[^"]*"?)|(?P<num>(?<![\w])(?:\d+\.\d*|\.\d+|\d+)(?![A-Za-z_]))|(?P<op>->|==|!=|<=|>=|[<>+\-*/(),.=])|(?P<word>[A-Za-z_0-9][\w\'#&:$!@~`]*(?:-(?=[A-Za-z_0-9])[\w\'#&:$!@~`]*)*))')


def _tokens(line):
    out, pos = [], 0
    while pos < len(line):
        m = TOKEN.match(line, pos)
        if not m or m.end() == pos:
            pos += 1              # stray characters: the game skips them too
            continue
        kind = m.lastgroup
        out.append((kind, m.group(kind), m.start(kind)))
        pos = m.end()
    return out


def _strip_comment(line):
    q = False
    for n, ch in enumerate(line):
        if ch == '"':
            q = not q
        elif ch == ';' and not q:
            return line[:n]
    return line


class _Ctx:
    def __init__(self, db, script_id):
        self.db = db
        self.script_id = script_id
        self.locals = {}          # lower -> (name, kind)
        self.order = []           # [(name, kind)] in declaration order
        self.msgs = []

    def msg(self, line, sev, text, col=None):
        self.msgs.append({'line': line, 'sev': sev, 'text': text, 'col': col})

    def is_global(self, name):
        return bool(self.db.by_key.get(('GLOB', name.lower())))

    def exists(self, rid):
        return self.db.resolve_id(rid) is not None or rid.lower() == 'player'

    def kind_of(self, rid):
        ri = self.db.resolve_id(rid)
        return self.db.recs[ri][0] if ri is not None else None


def _unq(tok):
    return tok[1].strip('"') if tok[0] == 'str' else tok[1]


def _check_arg(ctx, ln, code, tok):
    v = _unq(tok)
    if code == 'n':
        if tok[0] in ('num', 'expr'):
            return
        if tok[0] == 'word' and (v.lower() in ctx.locals or ctx.is_global(v) or (F.get(v.lower()) or {}).get('value')):
            return
        if tok[0] == 'word':
            ctx.msg(ln, 'error', '"%s" should be a number or a variable, but there is no variable called that.' % v, tok[2])
        return
    if code == 'x':
        if v.lower() not in ('x', 'y', 'z'):
            ctx.msg(ln, 'error', 'Expected an axis here: X, Y or Z (not "%s").' % v, tok[2])
        return
    if code in ('s', '*'):
        return
    db = ctx.db
    if code == 'q':
        if not db.by_key.get(('DIAL', v.lower())):
            ctx.msg(ln, 'warning', 'There is no quest or topic called "%s" in your load order.' % v, tok[2])
    elif code == 'S':
        if not db.by_key.get(('SCPT', v.lower())):
            ctx.msg(ln, 'warning', 'There is no script called "%s".' % v, tok[2])
    elif code == 'c':
        low = v.lower()
        if not any(k[0] == 'CELL' and k[1].startswith(low) for k in _cell_names(db)) and not _region_named(db, low):
            ctx.msg(ln, 'warning', 'No place is called "%s".' % v, tok[2])
    elif code == 'f':
        if not db.by_key.get(('FACT', v.lower())):
            ctx.msg(ln, 'warning', 'There is no faction called "%s".' % v, tok[2])
    elif code == 'p':
        if not ctx.exists(v):
            ctx.msg(ln, 'warning', 'There is no spell called "%s".' % v, tok[2])
    elif code == 'i':
        if not ctx.exists(v):
            ctx.msg(ln, 'warning', 'Nothing in your load order has the ID "%s".' % v, tok[2])


_cells_cache = None


def _cell_names(db):
    """Place names (lowercase) for "is there a place called…" checks."""
    global _cells_cache
    if _cells_cache is not None and _cells_cache[0] is db.recs and _cells_cache[1] == len(db.recs):
        return _cells_cache[2]
    names = set()
    for k, lst in db.by_key.items():
        if k[0] == 'CELL':
            for v in lst:
                r = db.recs[v]
                if r is not None:
                    if r[1]:
                        names.add(('CELL', r[1].lower()))
                    if r[2]:
                        names.add(('CELL', r[2].lower()))
    _cells_cache = (db.recs, len(db.recs), names)
    return names


def _region_named(db, low):
    return any(k[0] == 'REGN' and (db.recs[v][2] or '').lower().startswith(low)
               for k, lst in db.by_key.items() if k[0] == 'REGN' for v in lst[-1:])


def _call(ctx, ln, toks, i, in_expr):
    """Check a command (optionally "ref ->" first) starting at toks[i]. Returns the index after it."""
    if i < len(toks) and i + 1 < len(toks) and toks[i + 1][1] == '->':
        ref = _unq(toks[i])
        if not ctx.exists(ref):
            ctx.msg(ln, 'warning', 'Nothing in your load order has the ID "%s" (before ->).' % ref, toks[i][2])
        i += 2
        if i >= len(toks):
            ctx.msg(ln, 'error', 'Something is missing after "->": a command, e.g. %s->Disable.' % ref)
            return i
    t = toks[i]
    name = _unq(t)
    f = F.get(name.lower())
    if f is None:
        if t[0] == 'word' and (name.lower() in ctx.locals or ctx.is_global(name)) and in_expr:
            return i + 1
        if in_expr:
            if t[0] == 'word':
                ctx.msg(ln, 'error', '"%s" is not a variable or command I know. Declare it at the top (e.g. "short %s") if it\'s meant to be a variable.' % (name, name), t[2])
            return i + 1
        else:
            ctx.msg(ln, 'warning', '"%s" is not a command I know. Check the spelling (the reference on the right lists them).' % name, t[2])
        return len(toks)
    if in_expr and not f['value']:
        ctx.msg(ln, 'warning', '%s doesn\'t give back a value, so it can\'t be tested or used in a calculation.' % f['name'], t[2])
    req, _, opt = f['args'].partition('|')
    i += 1
    args = []
    stop = {')', '==', '!=', '<', '>', '<=', '>=', '+', '-', '*', '/', '='} if in_expr else set()
    while i < len(toks) and toks[i][1] not in stop:
        if toks[i][1] == ',':
            i += 1
            continue
        if toks[i][1] == '(':
            # a calculation in brackets as one value: GetSquareRoot ( x + 1 )
            depth, j = 0, i
            while j < len(toks):
                depth += {'(': 1, ')': -1}.get(toks[j][1], 0)
                if depth == 0:
                    break
                j += 1
            _expr(ctx, ln, toks[i + 1:j])
            args.append(('expr', '(…)', toks[i][2]))
            i = j + 1
            if in_expr and len(args) >= len(req) + len(opt):
                break
            continue
        if toks[i][1] == '-' and i + 1 < len(toks) and toks[i + 1][0] == 'num':
            args.append(('num', '-' + toks[i + 1][1], toks[i][2]))
            i += 2
            continue
        if in_expr and len(args) >= len(req) + len(opt) and '*' not in f['args']:
            break
        args.append(toks[i])
        i += 1
    if '*' in f['args']:
        if f['name'].lower() == 'messagebox' and (not args or args[0][0] != 'str'):
            ctx.msg(ln, 'error', 'MessageBox needs the text in quotes: MessageBox "Hello"', t[2])
        return i
    if len(args) < len(req):
        ctx.msg(ln, 'error', '%s needs %d more value%s. Example: %s' % (f['name'], len(req) - len(args), '' if len(req) - len(args) == 1 else 's',
                                                                 f['desc'].split(': ', 1)[-1] if ': ' in f['desc'] else f['name'] + ' ' + ' '.join('…' for _ in req)), t[2])
    elif len(args) > len(req) + len(opt):
        ctx.msg(ln, 'warning', '%s was given more values than it uses; the extra ones are ignored.' % f['name'], t[2])
    for code, a in zip(req + opt, args):
        _check_arg(ctx, ln, code, a)
    return i


def _expr(ctx, ln, toks, i=0):
    """Check an expression (in if/while/set). Returns the index after it."""
    depth, expect_value = 0, True
    while i < len(toks):
        t = toks[i]
        v = t[1]
        if v == '(':
            depth += 1
            i += 1
            continue
        if v == ')':
            depth -= 1
            if depth < 0:
                ctx.msg(ln, 'error', 'There is a ")" without a matching "(".', t[2])
                depth = 0
            i += 1
            continue
        if v in ('==', '!=', '<', '>', '<=', '>=', '+', '-', '*', '/'):
            i += 1
            expect_value = True
            continue
        if v == '=':
            ctx.msg(ln, 'warning', 'To compare, use two equals signs: == (the game may read one "=" differently).', t[2])
            i += 1
            continue
        if t[0] in ('word', 'str') and i + 2 < len(toks) and toks[i + 1][1] == '.':
            owner = _unq(t)     # someone.variable or script.variable
            if not ctx.exists(owner) and not ctx.db.by_key.get(('SCPT', owner.lower())):
                ctx.msg(ln, 'warning', 'Nothing called "%s" (before the dot) exists.' % owner, t[2])
            i += 3
            continue
        if t[0] == 'num' or t[0] == 'str':
            i += 1
            continue
        if t[0] == 'word':
            low = v.lower()
            if low in ctx.locals or (ctx.is_global(v) and low not in F):
                i += 1
                continue
            i = _call(ctx, ln, toks, i, True)
            continue
        i += 1
    if depth > 0:
        ctx.msg(ln, 'error', 'A "(" is never closed with ")".')
    return i


def _unwrap_ref_brackets(toks):
    """player->( GetItemCount "x" ) is accepted by the game: drop those brackets."""
    out, skip = [], []
    i = 0
    while i < len(toks):
        t = toks[i]
        if t[1] == '(' and out and out[-1][1] == '->':
            depth, j = 0, i
            while j < len(toks):
                depth += {'(': 1, ')': -1}.get(toks[j][1], 0)
                if depth == 0:
                    break
                j += 1
            skip.append(j)
            i += 1
            continue
        if i in skip:
            i += 1
            continue
        out.append(t)
        i += 1
    return out


def check(db, text, script_id=''):
    """Check a script. Returns {'messages': [{line, sev, text}], 'locals': [(name, kind)], 'name': begin name}."""
    ctx = _Ctx(db, script_id)
    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    begin_name, ended, stack = None, False, []
    first_stmt = True
    for n, raw in enumerate(lines, 1):
        line = _strip_comment(raw).strip()
        if not line:
            continue
        if raw.count('"') % 2:
            ctx.msg(n, 'error', 'A quote (") is opened but never closed on this line.')
            continue
        toks = _tokens(line)
        if not toks:
            continue
        for t in toks:
            if t[0] == 'bad':
                ctx.msg(n, 'warning', 'Unexpected character "%s".' % t[1], t[2])
        toks = _unwrap_ref_brackets([t for t in toks if t[0] != 'bad'])
        if not toks:
            continue
        if ended:
            ctx.msg(n, 'warning', 'This comes after "end", so the game ignores it.')
            continue
        kw = toks[0][1].lower()
        if first_stmt:
            first_stmt = False
            if kw != 'begin':
                ctx.msg(n, 'error', 'A script must start with "begin" and its name, e.g. "begin %s".' % (script_id or 'MyScript'))
            else:
                if len(toks) < 2:
                    ctx.msg(n, 'error', '"begin" needs the script\'s name after it.')
                else:
                    begin_name = _unq(toks[1])
                    if script_id and begin_name.lower() != script_id.lower():
                        ctx.msg(n, 'warning', 'The name after "begin" (%s) is different from the script\'s ID (%s). The ID is what counts; saving will use it.' % (begin_name, script_id))
                continue
        if kw == 'begin':
            ctx.msg(n, 'error', 'Only one "begin" is allowed in a script.')
            continue
        if kw == 'end':
            if stack:
                ctx.msg(n, 'error', 'The script ends but "%s" (line %d) is never closed with "%s".' % (stack[-1][0], stack[-1][1], 'endif' if stack[-1][0] == 'if' else 'endwhile'))
            ended = True
            continue
        if kw in DECL:
            if len(toks) < 2 or toks[1][0] not in ('word', 'str'):
                ctx.msg(n, 'error', '"%s" needs a variable name after it, e.g. "%s doOnce".' % (kw, kw))
                continue
            name = _unq(toks[1])
            low = name.lower()
            if low in ctx.locals:
                ctx.msg(n, 'warning', 'The variable "%s" is declared twice.' % name)
            elif low in ('begin', 'set', 'if', 'endif', 'else', 'elseif', 'while', 'endwhile', 'return', 'to'):
                ctx.msg(n, 'error', '"%s" is a keyword; pick another variable name.' % name)
            else:
                # (a variable may share a command's name, e.g. "short OnPCHitMe": the variable wins)
                if stack:
                    ctx.msg(n, 'warning', 'Declare variables at the top of the script, not inside if/while.')
                ctx.locals[low] = (name, kw)
                ctx.order.append((name, kw))
            if len(toks) > 2:
                ctx.msg(n, 'warning', 'Only one variable per line: put the rest on their own lines.')
            continue
        if kw == 'set':
            to = next((k for k, t in enumerate(toks) if t[1].lower() == 'to'), None)
            if to is None:
                ctx.msg(n, 'error', '"set" needs "to": set myVariable to 1')
                continue
            target = toks[1:to]
            if not target:
                ctx.msg(n, 'error', 'Which variable? set myVariable to 1')
            elif len(target) == 1:
                name = _unq(target[0])
                if name.lower() not in ctx.locals and not ctx.is_global(name):
                    ctx.msg(n, 'error', 'The variable "%s" isn\'t declared. Add "short %s" near the top (or make a global variable).' % (name, name), target[0][2])
            elif len(target) == 3 and target[1][1] in ('.', '->'):
                owner = _unq(target[0])
                if not ctx.exists(owner) and not db.by_key.get(('SCPT', owner.lower())):
                    ctx.msg(n, 'warning', 'Nothing called "%s" (before the dot) exists.' % owner, target[0][2])
            else:
                ctx.msg(n, 'error', 'I can\'t tell which variable to set here.')
            if to + 1 >= len(toks):
                ctx.msg(n, 'error', 'Set it to what? Put a value after "to".')
            else:
                _expr(ctx, n, toks, to + 1)
            continue
        if kw in ('if', 'while', 'elseif'):
            if kw == 'elseif':
                if not stack or stack[-1][0] != 'if':
                    ctx.msg(n, 'error', '"elseif" without an "if" before it.')
                elif stack[-1][2]:
                    ctx.msg(n, 'error', '"elseif" can\'t come after "else".')
            else:
                stack.append((kw, n, False))
            if len(toks) < 2:
                ctx.msg(n, 'error', '"%s" needs something to test, e.g. %s ( doOnce == 0 )' % (kw, kw))
            else:
                if toks[1][1] != '(':
                    ctx.msg(n, 'info', 'Tip: put the test in brackets, e.g. %s ( x == 1 ). The game is fussy without them.' % kw)
                _expr(ctx, n, toks, 1)
            continue
        if kw == 'else':
            if not stack or stack[-1][0] != 'if':
                ctx.msg(n, 'error', '"else" without an "if" before it.')
            else:
                stack[-1] = (stack[-1][0], stack[-1][1], True)
            continue
        if kw in ('endif', 'endwhile'):
            want = 'if' if kw == 'endif' else 'while'
            if not stack:
                ctx.msg(n, 'warning', 'This "%s" has no "%s" to close; the game skips it, but check your ifs and endifs match up.' % (kw, want))
            elif stack[-1][0] != want:
                ctx.msg(n, 'error', '"%s" here closes nothing: the "%s" on line %d needs "%s" first.' % (kw, stack[-1][0], stack[-1][1], 'endif' if stack[-1][0] == 'if' else 'endwhile'))
                stack.pop()
            else:
                stack.pop()
            continue
        if kw == 'return':
            continue
        if kw in ('to',):
            ctx.msg(n, 'error', 'Unexpected "to".')
            continue
        if kw == '(':
            ctx.msg(n, 'warning', 'A test on its own line does nothing. Did you mean "if" in front of it?')
            continue
        # a variable alone on a line does nothing
        if len(toks) == 1 and (kw in ctx.locals) and kw not in F:
            ctx.msg(n, 'warning', '"%s" alone on a line does nothing. Did you mean "set %s to …"?' % (toks[0][1], toks[0][1]))
            continue
        end = _call(ctx, n, toks, 0, False)
        if end < len(toks) and not any(m['line'] == n for m in ctx.msgs):
            ctx.msg(n, 'warning', 'I don\'t understand the end of this line ("%s").' % ' '.join(t[1] for t in toks[end:]))
    if first_stmt:
        ctx.msg(1, 'error', 'The script is empty. It needs "begin Name" … "end".')
    elif not ended:
        ctx.msg(len(lines), 'error', 'The script never ends: add "end" on the last line.')
        for s in stack:
            ctx.msg(s[1], 'error', 'This "%s" is never closed with "%s".' % (s[0], 'endif' if s[0] == 'if' else 'endwhile'))
    ctx.msgs.sort(key=lambda m: (m['line'], {'error': 0, 'warning': 1, 'info': 2}[m['sev']]))
    return {'messages': ctx.msgs, 'locals': ctx.order, 'name': begin_name,
            'errors': sum(1 for m in ctx.msgs if m['sev'] == 'error')}


# ------------------------------------------------------------------ reading and saving scripts
def _winner(db, sid):
    lst = [v for v in db.by_key.get(('SCPT', (sid or '').lower()), []) if v not in db.dead]
    return lst[-1] if lst else None


def read(db, sid):
    ri = _winner(db, sid)
    if ri is None:
        raise EditError('There is no script called "%s".' % sid)
    r = db.recs[ri]
    text = ''
    for t, d in iter_subrecords(db.files[r[3]].record_at(r[4])[2]):
        if t == 'SCTX':
            text = bytes(d).decode(ENC, 'replace').rstrip('\0')
    key = 'SCPT|' + r[7]
    return {'id': r[1], 'i': ri, 'text': text, 'src': db.plugins[r[3]]['name'],
            'mine': bool(db.project and key in db.project.records),
            'created': bool(db.project and db.project.records.get(key, {}).get('created')),
            'used_by': used_by(db, r[1]), 'check': check(db, text, r[1])}


_use_cache = None


def used_by(db, sid):
    """Who runs this script: objects and characters that carry it, start scripts, and dialogue that starts it."""
    global _use_cache
    stamp = (len(db.recs), len(db.dead), len(db.project.log) if db.project else 0)
    if _use_cache is None or _use_cache[0] is not db.recs or _use_cache[1] != stamp:
        idx = {}
        for k, lst in db.by_key.items():
            if k[0] in ('CELL', 'LAND', 'PGRD', 'DIAL', 'SCPT', 'GMST', 'GLOB', 'LTEX'):
                continue
            live = [v for v in lst if v not in db.dead]
            if not live:
                continue
            ri = live[-1]
            r = db.recs[ri]
            data = db.files[r[3]].record_at(r[4])[2]
            if k[0] == 'INFO':
                low = data.lower()
                p = low.find(b'startscript')
                while p >= 0:
                    m = re.match(rb'startscript[\s,"]+([\w\' ]+?)["\s]*(?:\r|\n|;|$)', low[p:p + 80])
                    if m:
                        idx.setdefault(m.group(1).decode(ENC, 'replace').strip(), []).append(('INFO', ri))
                    p = low.find(b'startscript', p + 11)
                continue
            if k[0] == 'SSCR':
                for t, d in iter_subrecords(data):
                    if t == 'NAME':
                        idx.setdefault(zstr(d).lower(), []).append(('SSCR', ri))
                continue
            p = data.find(b'SCRI')
            if p >= 0:
                for t, d in iter_subrecords(data):
                    if t == 'SCRI':
                        idx.setdefault(zstr(d).lower(), []).append((k[0], ri))
        _use_cache = (db.recs, stamp, idx)
    out = []
    for tag, ri in _use_cache[2].get(sid.lower(), [])[:40]:
        r = db.recs[ri]
        if tag == 'INFO':
            d = db.info_dial.get(ri)
            out.append({'kind': 'dialogue', 'i': ri, 'label': 'Started by a line in "%s"' % (db.recs[d][1] if d is not None else '?')})
        elif tag == 'SSCR':
            out.append({'kind': 'start', 'i': ri, 'label': 'Runs from the start of the game (start script)'})
        else:
            out.append({'kind': tag, 'i': ri, 'id': r[1], 'label': r[2] or r[1]})
    return out


def save(db, sid, text, create=False, save=True):
    """Keep a script in the mod. save=False leaves the commit to the caller (a script made as part of a
    bigger change: mechanism.py), and the result is then just the script's ID."""
    _require_project(db)
    sid = (sid or '').strip()
    if not sid:
        raise EditError('Give the script an ID, e.g. "MyMod_DoorScript".')
    if len(sid.encode(ENC, 'replace')) > 31:
        raise EditError('Script IDs can be at most 31 characters.')
    if not re.match(r'^[A-Za-z_][\w]*$', sid):
        raise EditError('Script IDs work best with letters, numbers and _ only (no spaces).')
    ri = _winner(db, sid)
    if create and ri is not None:
        raise EditError('A script called "%s" already exists.' % sid)
    if not create and ri is None:
        raise EditError('There is no script called "%s".' % sid)
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    # make "begin" use the script's ID (that's what the game goes by)
    text = re.sub(r'(?im)^(\s*begin\s+)("?)[^\s";]+("?)', lambda m: m.group(1) + m.group(2) + sid + m.group(3), text, count=1)
    res = check(db, text, sid)
    shorts = [n for n, k in res['locals'] if k == 'short']
    longs = [n for n, k in res['locals'] if k == 'long']
    floats = [n for n, k in res['locals'] if k == 'float']
    names = b''.join(n.encode(ENC, 'replace') + b'\0' for n in shorts + longs + floats)
    # Morrowind's own engine also wants compiled bytes; OpenMW compiles the text itself
    schd = sid.encode(ENC, 'replace')[:31].ljust(32, b'\0') + struct.pack('<5i', len(shorts), len(longs), len(floats), 0, len(names))
    subs = [('SCHD', schd)]
    if names:
        subs.append(('SCVR', names))
    subs += [('SCDT', b''), ('SCTX', text.replace('\n', '\r\n').encode(ENC, 'replace'))]
    key = sid.lower()
    flags = 0
    if ri is not None:
        flags = db.recs[ri][6] & ~0x20
    was_created = bool(db.project.records.get('SCPT|' + key, {}).get('created'))
    db.project.set_record('SCPT', key, flags, join_subs(subs), created=create or was_created)
    if not save:
        db.sync_project()
        return sid
    commit(db, ('Created script "%s"' if create else 'Edited script "%s"') % sid)
    return read(db, sid)


SCRIPTABLE = {'ACTI', 'DOOR', 'CONT', 'MISC', 'BOOK', 'WEAP', 'ARMO', 'CLOT', 'NPC_', 'CREA', 'LIGH', 'ALCH',
              'INGR', 'APPA', 'LOCK', 'PROB', 'REPA'}


def attach(db, sid, target, detach=False):
    """Put a script on an object/character (or take it off). target "*start*" = run from the start of the game."""
    _require_project(db)
    ri = _winner(db, sid)
    if ri is None:
        raise EditError('There is no script called "%s". Save it first.' % sid)
    sid = db.recs[ri][1]
    if target == '*start*':
        key = sid.lower()          # start scripts are known by their script's name
        if detach:
            for k, lst in list(db.by_key.items()):
                if k[0] == 'SSCR':
                    for v in lst:
                        if v in db.dead:
                            continue
                        for t, d in iter_subrecords(db.files[db.recs[v][3]].record_at(db.recs[v][4])[2]):
                            if t == 'NAME' and zstr(d).lower() == sid.lower():
                                if not db.project.records.get('SSCR|' + k[1], {}).get('created'):
                                    raise EditError('This start script comes from %s, so it can\'t be removed here.' % db.plugins[db.recs[v][3]]['name'])
                                db.project.remove_record('SSCR', k[1])
            commit(db, 'Script "%s" no longer starts with the game' % sid)
        else:
            db.project.set_record('SSCR', key, 0, join_subs([('DATA', zs(key)), ('NAME', zs(sid))]), created=True)
            commit(db, 'Script "%s" now runs from the start of the game' % sid)
        return read(db, sid)
    ti = db.resolve_id(target)
    if ti is None:
        raise EditError('Nothing has the ID "%s".' % target)
    r = db.recs[ti]
    if r[0] not in SCRIPTABLE:
        raise EditError('Scripts can\'t be put on that kind of thing (%s).' % r[0])
    _t, flags, data = db.files[r[3]].record_at(r[4])
    subs = [(t, bytes(d)) for t, d in iter_subrecords(data) if t != 'SCRI']
    if not detach:
        # SCRI goes after the name/model/stats, before inventory lists
        at = next((n for n, (t, _d) in enumerate(subs) if t in ('NPCO', 'NPCS', 'AIDT', 'AI_W', 'DODT', 'INDX', 'XSCL')), len(subs))
        subs.insert(at, ('SCRI', zs(sid)))
    db.project.set_record(r[0], r[7], flags & ~0x20, join_subs(subs),
                          created=bool(db.project.records.get(r[0] + '|' + r[7], {}).get('created')))
    commit(db, ('Took script "%s" off "%s"' if detach else 'Put script "%s" on "%s"') % (sid, r[2] or r[1]))
    return read(db, sid)


def reference():
    return {'cats': CATS, 'functions': {k: v for k, v in F.items()}}


TEMPLATES = [
    ('Empty object script', 'Attach it to an object or character. It runs while they are nearby.',
     'begin {id}\n\nshort doOnce\n\nif ( MenuMode == 1 )\n\treturn\nendif\n\nif ( doOnce == 0 )\n\tset doOnce to 1\n\t; things to do once\nendif\n\nend\n'),
    ('Do something when used', 'Attach to a door, lever or object. Runs when the player activates it.',
     'begin {id}\n\nif ( OnActivate == 1 )\n\tMessageBox "It doesn\'t budge."\n\t; Activate   ; uncomment to also do the normal thing (open, pick up…)\nendif\n\nend\n'),
    ('Picked up: advance a quest', 'Attach to an item. When the player picks it up, the quest moves on.',
     'begin {id}\n\nshort done\n\nif ( done == 0 )\n\tif ( OnPCAdd == 1 )\n\t\tJournal "MyQuest" 20\n\t\tset done to 1\n\tendif\nendif\n\nend\n'),
    ('Door locked until a quest stage', 'Attach to a door. It stays shut until the quest reaches a stage.',
     'begin {id}\n\nif ( OnActivate == 1 )\n\tif ( GetJournalIndex "MyQuest" >= 30 )\n\t\tActivate\n\telse\n\t\tMessageBox "The door is barred from the other side."\n\tendif\nendif\n\nend\n'),
    ('Timer (global script)', 'Start it with StartScript; it waits, does something, then stops itself.',
     'begin {id}\n\nfloat timer\n\nset timer to ( timer + GetSecondsPassed )\nif ( timer >= 10 )\n\tMessageBox "Ten seconds have passed."\n\tStopScript {id}\nendif\n\nend\n'),
    ('Character: greet the player once', 'Attach to an NPC. When the player comes close the first time, they walk up and talk.',
     'begin {id}\n\nshort greeted\n\nif ( MenuMode == 1 )\n\treturn\nendif\n\nif ( greeted == 0 )\n\tif ( GetDistance player < 300 )\n\t\tForceGreeting\n\t\tset greeted to 1\n\tendif\nendif\n\nend\n'),
]


def templates():
    return [{'name': n, 'desc': d, 'text': t} for n, d, t in TEMPLATES]


def my_scripts(db):
    if not db.project:
        return []
    out = []
    for k, rec in db.project.records.items():
        if k.startswith('SCPT|'):
            ri = _winner(db, rec['key'])
            out.append({'id': db.recs[ri][1] if ri is not None else rec['key'], 'created': rec.get('created', False)})
    return sorted(out, key=lambda x: x['id'].lower())
