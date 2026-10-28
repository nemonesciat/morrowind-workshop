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

## Effects in the game

Your own magic effects can shake the ground, change the weather, summon, teleport and more, with no scripting of
your own. See *Items, spells and the Forge*.
