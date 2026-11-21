# Coding with AI

*Lua scripts, your own effects' Lua and dialogue lines written by an AI: Claude, or a model running on your own PC.*

## Which AI does what

| Where | What it writes | Which AI |
|---|---|---|
| Scripts › a Lua script › **✦ Write with AI**, **✦ Fix** | Whole OpenMW Lua scripts | Claude or your own model |
| Create › New magic effect › **✦ Write it for me** | The Lua of one step of your effect | Claude or your own model |
| Dialogue, quests, Populate, conversations › **✦** | Three versions of a line to pick from | Claude or your own model |
| The **✦ AI** panel (the chat assistant) | Builds and changes things in your mod: rooms, objects, records, quests | Always Claude |

Which one writes Lua and lines is set in **Settings › AI assistant › Lua and lines written by**. The chat assistant
needs Claude: it works through the Workshop's own tools step by step, which small models don't do reliably.

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
3. In **Settings › AI assistant**, pick **A model on this PC**, check the address, press **Find models** and pick
   the model.

The first request after the app starts takes a few minutes while the model loads into your graphics card; after that
a script takes seconds. An app may unload the model after a few idle minutes, and the next request is slow again.

"Nothing answered at …" means the app isn't running, or its server is off.

**Which model.** Bigger writes better. The Workshop keeps each request small (about 2,300 words' worth of the model's
room at most), so models that fit a 6–8 GB card can be used; a coding model of 30B fits a 12 GB card with the rest
in memory. A small model writes weaker scripts than Claude: see *Good to know*.

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

## Good to know

- **Try it in the game before sharing your mod.** The checks stop scripts that can't work, not ones that run and do
  the wrong thing.
- **A small model on a PC writes weaker scripts than Claude**: it makes up functions more often (the checks catch
  most) and gets the logic wrong more often (they don't). Fine for small jobs; for bigger ones, Claude.
- **What is sent.** With a model on your PC, nothing leaves your computer. With Claude, your request and the script go
  to Anthropic, billed to your API key (a script costs about a cent or two).
- On Linux, if OpenMW's list of its Lua isn't where the Workshop looks, the checks against it are skipped; the rest
  works.
