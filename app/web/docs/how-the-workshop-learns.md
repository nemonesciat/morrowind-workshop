# How the Workshop learns

*A plain account of where the Workshop's building and decorating knowledge comes from, what it reads, and
what it never does.*

## In short

When the Workshop furnishes a room, builds a house from pieces, makes a dungeon or fills the Style palette,
it does not ask an AI and it does not go online. It has studied the interiors already in your installed
game, measured how they're put together, and works from those measurements.

- That study runs on your own PC, in about seven minutes, once.
- It is **counting and geometry**: how often a bedroom has a chest, how far a lantern hangs below the
  ceiling, which wall piece the game puts next to which corner.
- No account, no API key, no internet connection and no AI model is involved. It works the same with your
  network cable unplugged.

## What "learning" means here

The Workshop reads every interior in your load order: the places the original game and the mods you play with
made. For each kind of question it needs answered, it runs a **survey** over them, a small program that counts
and measures. For example:

| Survey | What it measures | What uses it |
|---|---|---|
| Rooms | which furniture and clutter each kind of room has, and how often | Auto-furnish |
| Placement | where each piece stands: against a wall, in a corner, out in the room; its clearance | Auto-furnish |
| Arrangements and scenes | what goes together: a table with its chairs, the scribe's desk with its inkwell | Auto-furnish, the Style palette's sets |
| Shelves and tables | what the game puts on each particular shelf, table, counter or planter model | Dress this, Auto-furnish |
| Lights and walls | how far each hanging light hangs below the ceiling; where tapestries go | Auto-furnish |
| Hearths, trades, halls, gardens | a kitchen's whole hearth, a smithy around its forge, how halls are dressed | Auto-furnish |
| Joints and adjacency | which building piece the game joins to which, face by face, and what stands at each joint | building from pieces, Fix here, Extend by piece |
| Dungeons | how the game's ruins, caves and tombs join their tunnel pieces, and how they're dressed | Create › Dungeon |
| People | who lives and works in each kind of place, and how they're dressed and equipped | Populate |
| Styles | which pieces, furniture and decor each culture's places use, and how often | the Style palette |

There are 25 surveys in all. Each one ends up as a table of numbers, such as "in Hlaalu bedrooms, a chest
stands at the foot of the bed in 4 out of 10 cases". When the Workshop furnishes, it picks from those
numbers, with a little chance in the choice so that two rooms don't come out the same.

The checks work the same way. **Find gaps** and **Check this place** were each tried on about a hundred of
the game's own interiors before they were used. They warn only about what the game itself rarely does, not
about its deliberate choices.

## What it reads

- **Your installed plugins**, in the load order OpenMW uses: `Morrowind.esm` and the mods you play with. The
  Workshop finds them through your own `openmw.cfg`.
- **Places made by the game or by other mods only.** The mod you're making is left out, so the Workshop never
  learns its own habits back from its own work.
- **Your taste, if you give it.** Mark a place with **Use as an example** and the surveys count it five times
  over, so the results lean towards places you like.

It reads these files and never changes them. The only file the Workshop writes for the game is your own
mod's plugin.

## When it happens

- **The first time a feature needs it:** the first Auto-furnish after you install the Workshop, or after
  your load order changes. The Workshop shows a progress bar while it learns; the rest of the program keeps
  working meanwhile.
- **In the background:** up to three helper processes at low priority, so your PC stays usable. On a
  large load order with big landmass mods, it takes about seven minutes.
- **Once.** The results are kept. The Workshop learns again only when your load order or your example places
  change, or when a new version of the Workshop improves a survey.

## Where it's kept

In the `cache` folder inside the Workshop's own folder, as plain JSON files. On a large load order they come
to about 170 MB. They contain counts and measurements about your installed game's places, and nothing about
you. Delete the folder and the Workshop simply learns again next time.

## What the Workshop does connect to, and only when you ask

None of these are part of the learning, and each is off until you use it:

- **The Assistant** (optional), marked ✦ wherever it appears. It uses Anthropic's Claude, with an API key
  **you** paste in yourself, billed to your own Anthropic account. It does three things, each only when you
  ask:
  - answers you in the ✦ Assistant chat;
  - drafts a line of dialogue when you press its suggestion button in Dialogue;
  - writes the Lua for one of your own magic effects when you press "✦ Write it for me".

  Without a key it simply isn't available, and nothing else changes. Auto-furnish, building, dungeons,
  Populate (whose people and their words are written without AI) and the Style palette never use it.
- **Build together.** Working on a mod with friends connects your Workshops to each other, over your network
  or the internet, when you start or join a session.
- **Packs from a shared folder or link**, when you add one under Library › Pack sources.
- **Links you click**, such as the GitHub page or OpenMW's download page, which open in your web browser.

**Report a problem** makes a report file on your PC for you to read and send yourself. It sends nothing.

## Checking it for yourself

- **Unplug your network**, delete the `cache` folder, and Auto-furnish a room: the Workshop learns and
  furnishes exactly as usual.
- **Read the source** at <https://github.com/nemonesciat/morrowind-workshop>:
  - the surveys are the `*survey.py` files in `app/`, plus `joints.py`, `adjacency.py` and `catalogue.py`;
  - `background.py` and `surveyworker.py` run them;
  - the only code that talks to an AI service is `app/ai.py`, used by the Assistant alone.
