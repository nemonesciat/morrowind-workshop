# Scripts and game rules

*Morrowind scripts and OpenMW Lua scripts, and the game's own rules: factions, classes, races, birthsigns, skills,
regions, sounds, magic effects, global variables and game settings.*

## Morrowind scripts (MWScript)

The **Scripts** page: **+ New script**, **Open a script** (search any, e.g. LocalState), and **In my mod** for yours.

- The editor colours the script and numbers its lines.
- **A checker explains mistakes in plain words as you type**: a missing `endif`, a command spelt wrong, an ID that
  isn't in your load order.
- **A searchable list of every command**, with examples, sits beside it.
- OpenMW compiles scripts itself when the game starts, so what you save takes effect directly.

Attach a script to an object, a person or a creature from its editor (the **Script** box), or run it from dialogue
(a line's result script).

## OpenMW Lua scripts

**Lua scripts (OpenMW)** on the Scripts page, with **+ New Lua script**. Lua can do what MWScript can't: new menus,
keys, timers, changing the world as you play. Pick what the script is for (attached to objects, the player, or the
whole game); the editor checks it as you type.

**✦ Write with AI** in the editor: say what the script should do, and the AI writes it (or changes the one you have),
for you to read over and Save. It uses **a model on this PC**: in Settings → AI, give the address of the app that
runs it and press **Find models**. Ollama,
LM Studio (its server on), llama.cpp's llama-server, KoboldCpp and most others work; their addresses are in the
box's tip.

- The AI is given OpenMW's own list of its Lua, read from your OpenMW install, so it picks functions that exist.
- Put names of places and things in quotes ("Balmora, Guild of Mages", "Caius Cosades"): the Workshop looks them up in
  your game and gives the AI their real IDs, and for a place a spot to arrive at. An ID your game doesn't have is
  pointed out.
- What it writes is checked: its shape, OpenMW's rules for that kind of script, and every function and field against
  that same list (a name OpenMW doesn't have, or one only a whole-game script may use). Anything found goes back to
  the AI to put right, twice at most; what is left shows under the editor.
- A script on objects that needs the whole game to do something (moving the player, giving items) asks for it; the
  AI writes that part too, and offers to add it as its own script.
- Each script it writes starts with a line saying which model wrote it. Try it in the game before sharing the mod:
  the checks catch scripts that can't work, not ones that run but do the wrong thing, and a small model on a PC
  writes weaker scripts than a big one.

The editor itself also marks names that aren't in OpenMW's list, as warnings (the list now and then trails the game),
and shows the Lua errors the game wrote about the script in its log (openmw.log) the last time it ran. **✦ Fix** sends
both to the AI to put right, the script unsaved after, as with Write.

Lua only works in an **OpenMW .omwaddon**. If your mod is a plain .esp, Lua scripts you write are kept in the
project but not saved into the mod.

Some Workshop tools write small Lua scripts for you: your own magic effects, sliding panels, Tamriel Data's effects.

## Global variables and game settings

- **🌐 Global variables**: numbers every script and dialogue line can read and change: quest flags, counters, choices
  the player made.
- **⚙ Game settings**: the game's own rules: prices, jump height, bounties, how fast skills rise… Change them
  carefully, since they affect the whole game.

Both are on the Scripts page (Shared numbers and rules) and the Rules page.

## The Rules page

| Tab | What's in it |
|---|---|
| 🏛 Factions | Guilds, Great Houses and other groups: ranks with what it takes to be promoted, the skills they care about, how they feel about other factions. |
| 🎓 Classes | What characters are good at. Classes ending in "Service" sell things when their characters use automatic stats. |
| 🧝 Races | Starting attributes, skill bonuses, size and built-in powers. |
| ✨ Birthsigns | The sign chosen at the start and the spells or abilities it gives. |
| 📚 Skills | The 27 skills: which attribute governs each, combat, magic or stealth, and how much each use raises it. None can be added. |
| 🌦 Regions & weather | See *Sky, regions and weather*. |
| 🔊 Sounds | Every sound the game can play: its file, how loud it is and how far it carries. Make a new one from any sound file in your game or your Library. |
| 🪄 Magic effects | Their school, base cost, colour, pictures and sounds. Your own (made with Lua) are listed first; see *Items, spells and the Forge*. |
| 🌐 Global variables, ⚙ Game settings | As above. |

**＋ New** makes a new one where the game allows it (not for skills, magic effects or game settings, which are
fixed sets, as in the Construction Set).

## Things that move: hidden doors and panels

Right-click a placed object for **🚪 Make this a door to…**, **↪ Rotating panel…** and **⇆ Sliding panel…** (a
panel that slides aside, used directly or pulled by another object, such as a lever or a book). The Workshop
writes the scripts in the game's own way. See *Building interiors*.

## Scenes

A scene is a cutscene: camera shots, actors playing their animations, spoken lines, music, fades, and what happens
at the end. Scenes are made in a modding program connected to the Workshop (**Settings › Connected programs**;
such a program asks once and you press **Allow**). What it sends joins your unsaved work, marked ⇄ in My changes,
each with Undo.

On the Scripts page, **Scenes** lists them. Pick one to choose what starts it in the game: only when asked by
another script, the player coming near a spot, a quest reaching a stage, or a global variable set to 1 (from a
dialogue result, for example). **Only once a game** is ticked to start with. In the game, Space or Enter skips a
scene; its end always runs. Scenes play in an .omwaddon mod.

## Effects in the game

Your own magic effects can shake the ground, change the weather, summon, teleport and more, with no scripting of
your own. See *Items, spells and the Forge*.
