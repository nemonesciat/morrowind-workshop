# Playing and testing

*Starting the game right where you're building, as a new character or one of your own, with what you need to test,
and the live link that shows your changes in the game as you make them.*

## Play here

On the World map, **▶ Play here** (Place panel) starts OpenMW in the place you have open, with your whole load
order and your mod. Your mod always loads last.

- **Pick a spot** first to start (or, while the game runs, teleport) exactly where you click.
- Outdoors without a spot you start in the middle of the cell; indoors, just inside the place's door.
- **Your normal saves are untouched.**

## Who you play as

The **👤** button beside Play here says who you start as:

- **A new character**: a fresh start with nothing but your test setup.
- **One of your own characters**: they start from their latest save and are moved to the spot, with their own
  gear, spells and quests. The Workshop loads a copy of the save; saving in the game makes a new save, as always.
  A character whose save needs mods missing from your load order is marked, and the game asks before loading it.

## Test setups

**🧪 Test setup…** is what you get on top when Play here starts the game, so you can try something without
playing up to it.

- **Items to carry**, **Spells to know**: search and add (gold, a potion, Mark, Levitate…), with how many.
- **Quests, at a stage**: to test a quest from the middle; pick the stage from its journal lines.
- **Variables**: global variables your scripts or quests check.
- **Invincible (god mode)**, **Level**, and **Other console commands**, one per line.

Make as many setups as you like (**+ New setup**), and pick the one Play here uses with its round button
(**Nothing extra** for none). There are ready-made ones too; **Make a copy to change** one of them.
**▶ Give it now in game** hands a setup's items (and quest stages) to the game that's already running.

## The live link

While the game runs from the Workshop, the top shows **● Game linked**. Then:

- Edits you make in the Workshop appear in the game within a second. Brand-new places and records, and changes
  to the ground, need the game restarted.
- **Play here** becomes **Go here**: it teleports you there.
- **Me** (the map pin at the top) shows where your character is; **Follow my character** (Place panel) keeps the
  map with you.
- While you work in the Workshop the game pauses; your edits appear as soon as you switch back to it.
- On the Dialogue page you can set quest stages, give items and change variables in the running game, and see
  which conditions are true right now.
- Nothing you do in the game changes your mod, so you can play normally while it's linked.

A game started from OpenMW's own Launcher isn't linked (the top says **○ Game not linked**). Start it from the
Workshop instead.

## The OpenMW menu

**▶ OpenMW** at the top:

| Entry | What it does |
|---|---|
| ▶ Start the game | To the main menu, with your load order and your mod. The live link connects too. |
| Start in a place… | Pick a spot on the World map (Play here). |
| OpenMW Launcher | OpenMW's own settings, mods and data files. |
| Load order… | Switch plugins on or off and change their order. |
| Game start options… | Extra options for OpenMW each time the Workshop starts it (and settings, one per line). |
| OpenMW settings… | Graphics, shadows, the game's options: every setting, with what it does. |
| Open settings.cfg | OpenMW's settings file, in your text editor. |

## Testing as others will see it

**My mod → Get ready to share → ▶ Start a clean test** starts the game with only the base game and the mods your
mod needs, to see it as someone downloading it will. See *Sharing your mod*.

## Good to know

- If another plugin that loads after your mod changes the same ground or record, it wins when the game is started
  from OpenMW's own Launcher. The Place panel warns you where that happens; Play here always loads your mod last.
- Quitting the game is noticed by itself, and the top goes back to **○ Game not linked**.
