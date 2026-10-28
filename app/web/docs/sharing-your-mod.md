# Sharing your mod

*What's in your mod, checking it, packing it for Nexus or friends, your load order, and building a mod together
with other people.*

## My mod

The **My mod** page (or click the mod's name at the top) shows:

- **How many changes** it holds, whether it's **on in your normal OpenMW load order** (Play buttons load it for
  testing either way), and the files it **needs** (its masters).
- **Every change**, grouped by kind, with **Open on map** for places and ground (and **Undo** for a ground edit),
  and below it the history of what you did.

| Button | What it does |
|---|---|
| 📦 Get ready to share | Check, describe, test and pack the mod (below). |
| Add to my OpenMW load order | Switches it on for normal play. |
| 📁 Show folder | The folder with your mod file in it. |
| ＋ New mod…, 🗂 Your mods… | Start another mod; switch between them, or delete ones you no longer want. |
| 👥 Build together… | Work on it with others, live (below). |
| ⊕ Merge another mod into this one… | Adds everything another of your mods holds to this one, as one change. It clears this mod's Undo history; a backup is kept. |
| 📂 Open an .esp as your mod… | An existing .esp or .omwaddon becomes the mod you work on, saved straight back into that file, as the Construction Set's active file. Its placed objects keep their numbers, so saved games still work; a dated copy of the file as it was is kept beside it. |
| 💾 Save as… | Everything into a new .esp or .omwaddon, which is the active file from then on. |

A plain **.esp** can't hold OpenMW's Lua scripts. An **.omwaddon** can; tools that need Lua say so.

## Get ready to share

Four steps:

1. **Check**: the mod checked for what would trouble players, each finding marked **Needs fixing**, **Worth a look**
   or **Good to know**, with a safe fix where there is one. **↻ Check again** after fixing.
2. **Describe**: author, description (shown in the OpenMW Launcher), version and what's new, where to start (left
   empty, it lists the doors into your new places), credits and permissions. It writes the **Readme** and the **Nexus
   description** for you; **⧉ Copy** either.
3. **Try it on a clean setup**: **▶ Start a clean test** starts OpenMW with **only** the base game, your mod's masters
   and your mod, leaving out every other mod you have. If something's missing or broken there, players will see it
   too. Your normal setup and saves are untouched.
4. **Pack it**: **📦 Make the zip** with your mod, your own files (models, textures, sounds it uses) and the readme,
   laid out the way mod managers expect. Files your records don't use but should go in too (new music, say) go in the
   **extra files folder**.

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

The Workshop backs your mod up when you open it and regularly while you work (**Settings → Backups**: how often and
how many). **Restore** puts it back to a backup, after backing up how it is now.
