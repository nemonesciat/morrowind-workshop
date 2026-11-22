# Coding with AI

*Lua scripts, your own effects' Lua and dialogue lines written by a model running on your own PC, and coding agents
such as Claude Code working on your mod with the Workshop's own tools.*

## Which AI does what

| Where | What it writes | Which AI |
|---|---|---|
| Scripts › a Lua script › **✦ Write with AI**, **✦ Fix** | Whole OpenMW Lua scripts | Your model on this PC |
| Create › New magic effect › **✦ Write it for me** | The Lua of one step of your effect | Your model on this PC |
| Dialogue, quests, Populate, conversations › **✦** | Three versions of a line to pick from | Your model on this PC |
| A **coding agent** of your own (Claude Code, Codex, Cursor…) | Anything the Workshop's tools do: rooms, objects, records, quests, Lua, spells | The agent's own model |

All of it is set up in **Settings › AI**. To build and change things by asking in plain words, use a coding agent:
it works through the Workshop's own tools step by step.

## Setting up a model on your PC

A model on your PC is free and nothing leaves your computer. You need an app that runs models and offers the usual
chat address; most do:

| App | Address to give |
|---|---|
| Ollama | http://127.0.0.1:11434/v1 (filled in for you) |
| LM Studio | http://127.0.0.1:1234/v1 (switch its server on, in the Developer tab) |
| llama.cpp's llama-server | http://127.0.0.1:8080/v1 |
| KoboldCpp | http://127.0.0.1:5001/v1 |

1. Install the app and get a model in it (a coding model does Lua best).
2. Start the app. Ollama runs from the tray by the clock; its icon may be among the hidden ones (the **^**).
3. In **Settings › AI › Lua and dialogue writer**, check the address, press **Find
   models** and pick the model.

The first request after the app starts takes a few minutes while the model loads into your graphics card; after that
a script takes seconds. An app may unload the model after a few idle minutes, and the next request is slow again.

"Nothing answered at …" means the app isn't running, or its server is off. "Stopped partway" means the app running
the model broke down while writing: its own log says why. Try again, or another model. "Used all its room thinking"
means a model that thinks before it answers ran out of room first; the Workshop has already asked once more with its
thinking off. Give it more room (context length) in the app running it, or try a model that answers straight away.

**Which model.** Bigger writes better. The Workshop keeps each request small (about 2,300 words' worth of the model's
room at most), so models that fit a 6–8 GB card can be used; a coding model of 30B fits a 12 GB card with the rest
in memory. A small model writes weaker scripts than a big one: see *Good to know*.

## Writing a Lua script

1. **Scripts** › your Lua scripts › **+ New Lua script**. Lua works in an .omwaddon mod (a plain .esp can't hold it:
   **File › Save as…** makes one).
2. Under **Runs**, pick where it runs: the whole game, the player, every NPC, every creature, or only the objects you
   choose (then add them under *On these*).
3. Press **✦ Write with AI** and say what it should do.
4. It is written and shown unsaved, its first line saying which model wrote it. If it needs a part that runs for the
   whole game, you are asked whether to add that as its own script too.
5. Read it over, press **Save**, and try it in the game. In a running game, `reloadlua` in the console (the ~ key)
   loads your changes without restarting.

With a script already written, **✦ Write with AI** changes it as you ask and keeps the rest; **↺ Undo edits** takes
the AI's version back before you save.

## Telling it what you want

- **Put names in quotes**: "Balmora, Guild of Mages", "Caius Cosades", "restore health potion". The Workshop looks
  them up in your game and tells the AI their real IDs, and for a place a spot to arrive at. An ID that your game
  doesn't have is pointed out to it.
- **Pick the right Runs first.** "When the player uses this stone…" is a script on chosen objects; "when a new game
  starts…" runs for the whole game; "when this NPC dies…" runs on every NPC (or on the ones you choose).
- **Spells are magic effects, not scripts.** "When I cast this spell, take me to Seyda Neen" is made with **Create ›
  New magic effect**: steps such as Teleport, Summon, Push or *Lua of your own* run as the effect lands. Then make a
  spell with it. A script can't easily tell when a spell is cast.
- **One job a script.** Several small scripts are easier to get right, and to fix, than one big one.
- **Say what you mean by time.** "Every 10 seconds" is taken as real seconds; say "game hours" or "game time" for the
  game's clock, which runs 30 times faster.
- **Say what should happen, not how.** "When the player reaches stage 20 of "a1_2_antabolisinformant", show "Caius
  will want to hear this."" is enough.

## What the Workshop does with it

Before you see a script:

- **The rules of OpenMW's Lua** for that kind of script go with your request: which modules and handlers it may use,
  what only a whole-game script may do (moving the player, giving items).
- **OpenMW's own list of its Lua**, read from your OpenMW install, goes too, so the AI picks functions that exist.
- **It is checked**: its shape, the rules for its kind, and every function and field against that list. Anything
  found goes back to the AI with the real descriptions, twice at most. What is left shows under the editor.
- **Missing `require` lines** are put in by the Workshop.
- **The whole-game part.** A script on an object or NPC may not move the player or give items itself; it asks the
  whole-game script to. When none of your scripts does that yet, the AI writes it too.

The editor checks scripts you write yourself the same way; names OpenMW's list doesn't have are marked as warnings
(the list now and then trails the game).

## When it doesn't work

- Open the script after trying it in the game: the **Lua errors the game wrote about it** (in openmw.log) show under
  the editor.
- **✦ Fix** sends those and anything the checker finds to the AI, with the script, to put right.
- If it runs but does the wrong thing, say so with **✦ Write with AI** ("it shows the message for corpses already
  lying there; only when the NPC dies"), or change the description and write it again.
- Read what it wrote: a short script is quick to follow, and the comments say what each part is for.

## Your own effects and dialogue

- **Create › New magic effect**: add a *Lua of your own* step, say what it should do in the line beside it, and press
  **✦ Write it for me**. The step's Lua is checked the same way, with the effect's helpers (ctx.change, ctx.push…).
- **Dialogue**: the **✦** beside a line, a greeting, a journal entry or a quest title gives three versions to pick
  from, in Morrowind's voice; %PCName and the like are kept as the game wants them.

## Coding agents

If you already use a coding agent (Claude Code, Codex, Cursor, VS Code's Copilot, opencode and the like), it can work
on your open mod with the Workshop's own tools. The Workshop is an **MCP server** (the Model Context Protocol most
agents speak). With Claude Code no API key is needed: it uses your own Claude account.

**Claude Code**, in two clicks and no terminal:

1. In **Settings › AI › Coding agents**, tick **Let coding agents connect**.
2. Press **Connect Claude Code**. When it shows **✓ Connected**, Claude Code has the Workshop for every folder.
3. Start a **new** Claude Code session (one already open doesn't see it), keep the Workshop open with your mod, and
   ask about your mod ("make a Gate Stone that takes the player to "Balmora, Guild of Mages""). It sees the
   Workshop's tools and the rules of the place, and uses them.

If the Workshop says *Claude Code isn't on this PC*, install the Claude app (**Get the Claude app** beside it), open
its Code tab once, and press **Connect Claude Code** again. After **New key**, the line says *old address*: press
Connect Claude Code again.

**Other agents**: pick yours under **Set up**. The settings to give it are shown, with a **Copy** button, and where
they go.

What an agent can do: everything the Workshop's own buttons do. It has tools for the everyday work (look around a
place, place, move and remove things, records, characters, dialogue and quests, interiors and furnishing, MWScript,
Lua with OpenMW's own list of its Lua, magic effects and spells, recent changes, undoing its own last change), and it
can find and run any other action of the Workshop's: towns, castles, dungeons, land, populating, grass, regions,
sounds, items, the release zip and the rest. Agents that offer them also get ready-made requests: *write a Lua
script*, *fix a Lua script*, *make a spell*.

Some things stay yours: opening, switching or deleting mods, backups and files, starting the game, your settings and
load order, windows opening on your screen, and undoing your own changes.

**You see what it does.** While an agent works, a line under the Workshop's header says what it is doing and what it
did, and the window goes to the place it opens or changes, with what it placed or moved selected. It can also show
you something on purpose: a place, the map or 3D view, the camera on a spot. It never needs to control your screen;
tell it so if it offers. To keep your window where it is, untick **Show me what agents do** under Coding agents.

How its work is kept in check:
- Every change goes through the same steps as the Workshop's buttons, shows in **My changes** marked with 🤖 and the
  agent's name, and **Undo** takes it back. An agent can undo only its own last change.
- A Lua script it writes is checked before it is saved: its shape, the rules for its kind, every function and field
  against OpenMW's own list, and a function only a whole-game script may use. One with errors, or with a name OpenMW
  doesn't have, is refused with the reason, for the agent to fix. Forgotten `require` lines are put in. Events that
  nothing sends, or that nothing handles, come back as warnings.
- Each script starts with a line saying which agent wrote it.
- Only programs on this PC can reach the Workshop, with the key in the address. **New key** stops agents set up with
  the old one; unticking **Let coding agents connect** stops them all.

Agents should never edit the mod's files in the data folder directly: the Workshop writes those from your mod and
would write over the changes. The tools are the way in. A good agent with a strong model writes and fixes scripts
well; a small model on a PC driving an agent gets more wrong, and the checks catch only part of it.

## Good to know

- **Try it in the game before sharing your mod.** The checks stop scripts that can't work, not ones that run and do
  the wrong thing.
- **A small model on a PC writes weaker scripts than a big one**: it makes up functions more often (the checks
  catch most) and gets the logic wrong more often (they don't). Fine for small jobs; for bigger ones, a bigger model
  or a coding agent.
- **What is sent.** With a model on your PC, nothing leaves your computer. A coding agent sends what it works on to
  wherever its own model runs.
- On Linux, if OpenMW's list of its Lua isn't where the Workshop looks, the checks against it are skipped; the rest
  works.
