# Sharing your mod

*What's in your mod, checking it, packing it for Nexus or friends, your load order, and building a mod together
with other people.*

## My mod

The **My mod** page (or click the mod's name at the top) shows:

- **How many changes** it holds, whether it's **on in your normal OpenMW load order** (Play buttons load it for
  testing either way), and the files it **needs** (its masters).
- **Every change**, grouped by kind, with **Open on map** for places and ground (and **Undo** for a ground edit),
  and below it the history of what you did. Click ground rows to pick several (**Shift**+click a run, **Ctrl**+click
  one more or one less), then **↶ Undo** puts the ground in all of them back at once.

**Keeping Undo for the big changes.** Undo keeps about a hundred steps. So that a long run of small edits doesn't push
a town or a big shape out of reach:
- **Undo always takes back one change**: one stroke, one move, one turn. When the history is full, runs of the same
  change at its far end become one step, so nothing older is pushed out by them. Undo and Redo leave what they
  changed selected.
- **⧉ Group** (beside Undo and Redo, or **Group changes into one step** on this page): click it, work, click it
  again, and what you did in between becomes one step. Until you close it, Undo takes back one change at a time.
  Name the group on this page if you like. Undo and switching mods wait while a town is being made, and so does Group.

| Button | What it does |
|---|---|
| 📦 Get ready to share | Check, describe, test and pack the mod (below). |
| Add to my OpenMW load order | Switches it on for normal play. |
| 👥 Build together… | Work on it with others, live (below). |

## The File menu

**📁 File** at the top holds what a program's File menu holds.

| Entry | What it does |
|---|---|
| New mod… | Start another mod; this one stays as it is. |
| Open… (Ctrl+O) | Your computer's file picker. One of your mods switches to it. Any other .esp or .omwaddon becomes the mod you work on, saved back into that file, as the Construction Set's active file. Its placed objects keep their numbers, so saved games still work; a dated copy of the file as it was is kept beside it. With changes unsaved it asks first. |
| Open recent | Your other mods, newest first: one click switches. |
| Save (Ctrl+S) | Writes your changes into the mod and its .esp or .omwaddon. Until then nothing changes your mod's files. |
| Save as… | Everything, unsaved changes too, into a new mod under a new name, and you carry on in the copy. The original stays as you last saved it. Models and pictures are shared, not copied. The copy takes the original's place in your load order. |
| Save a version | Keeps the mod as saved, to come back to (see Backups). |
| Earlier versions… | The versions you saved and the Workshop's own backups, each with Restore. |
| Merge a mod into this one… | Adds everything another of your mods holds to this one, as one change. It clears this mod's Undo history; a backup is kept. |
| Merge a plugin file… | The same for any .esp or .omwaddon, picked with your computer's file picker: that file is only read. Its places, objects, records and dialogue come over; where both changed the same thing, you choose. Switch it off in the load order when merging (the window offers it): saved games made with it forget what happened to its things. An .omwaddon's Lua scripts don't come over. |
| Show in folder | The folder with your mod file in it. |
| Manage mods… | Every mod you made or opened: switch, show its folder, or delete the ones you no longer want. |
| Get ready to share… | The same as the button on My mod. |

A plain **.esp** can't hold OpenMW's Lua scripts. An **.omwaddon** can; tools that need Lua say so.

## Get ready to share

Four steps:

1. **Check**: the mod checked for what would trouble players, each finding marked **Needs fixing**, **Worth a look**
   or **Good to know**, with a safe fix where there is one. **↻ Check again** after fixing. **Leftovers** is what a
   place taken out leaves behind: people placed nowhere (with their lines and daily routines) and mod-made places no
   door leads to; **Sweep them out** removes them in one change. **Cloth awnings hanging in the air** are long
   sheets of cloth with no pole and no wall at the far end of their span (a town made before 2.6.14 copied them over
   doors from a game building whose market stall stood under them); **Take them down** removes them in one change.
2. **Describe**: author, description (shown in the OpenMW Launcher), version and what's new, where to start (left
   empty, it lists the doors into your new places), credits and permissions. It writes the **Readme** and the **Nexus
   description** for you; **⧉ Copy** either.
3. **Try it on a clean setup**: **▶ Start a clean test** starts OpenMW with **only** the base game, your mod's masters
   and your mod, leaving out every other mod you have. If something's missing or broken there, players will see it
   too. Your normal setup and saves are untouched.
4. **Pack it**: **📦 Make the zip** with your mod, your own files (models, textures, sounds it uses) and the readme,
   laid out the way mod managers expect. Files your records don't use but should go in too (new music, say) go in the
   **extra files folder**. With **Pictures as DDS** ticked, your .png, .jpg, .bmp and .tga textures go into the zip
   as DDS with mipmaps; your own files stay as they are.

## Health check

The **Health check** page reports what could go wrong with your setup, grouped by plugin and explained in plain
language: **Needs fixing** (missing masters or plugins), **Worth a look** (missing models or icons), **Good to know**
(dirty edits and the like). It changes nothing. **Check my mod** checks every record of your mod the way the game's
editor checks them.

## Load order

The **Load order** page lists the mods OpenMW loads, top to bottom: when two change the same thing, the lower one
wins.

- Tick to switch one on or off; drag (or ↑ ↓) to reorder; **Save load order** writes OpenMW's openmw.cfg, after a
  backup. **Undo my changes** before saving puts it back.
- **Fix master order** moves plugins only as far as needed so every file loads after the ones it needs.
- A plugin's **⋯** menu opens it as your mod, among other things.

## Build together

**👥 Build together…** (My mod, or the 👥 button at the top) works on one mod with other people at the same time,
from wherever they are. Everyone sees every change within a second or so, in the Workshop and in their own game.

- **Host**: share the mod you have open, under your name. Your copy is the one that counts. You get an **invite code**
  to send.
- **Join someone**: paste their invite code. You get a copy of their mod as a mod of its own; your own mods stay as
  they are.
- The 👥 button shows who's in. **Leave** (or **Stop hosting**) ends it; a copy you left can **Rejoin** later (the
  host's version then replaces it).

## Backups

**File → Save a version** keeps a version of your mod as you last saved it, until you remove it. **File →
Earlier versions** lists them with the Workshop's own backups, each with **Restore**. The Workshop also keeps
one by itself before each Make on the Land panel ("before making Uda"), the newest ten.

The Workshop backs your mod up when you open it and regularly while you work (**Settings → Backups**: how often, how
many, how much space they may take and whether they are stored compressed, about a tenth of the size). **Restore** puts it back to a backup, after backing up how it is now.
