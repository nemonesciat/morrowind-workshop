# Morrowind Workshop

An easy, modern editor for making Morrowind mods with [OpenMW](https://openmw.org). It reads your own
OpenMW setup, so you work with your real game and the mods you play with, and it is linked to the
running game: what you change in the Workshop appears in OpenMW within a second.

**Download the installer from Nexus Mods** (Morrowind → Utilities → Morrowind Workshop). This
repository is the source code it is built from.

## What it does

### Build interiors from pieces
- **Room planner**: draw a floor plan (rooms by kind, any shape, doorways, the way out, cellars and
  upper floors), start from a ready-made layout, or read any of the game's kit-built places back as a
  plan. The Workshop builds the house from a style's own room pieces, sealed, with stairs and doors.
- **31 styles**: Hlaalu, Redoran, Telvanni, Common, Imperial, Vivec and Mournhold, and with Tamriel
  Data also Indoril, Dres, Necrom, the Gold Coast, Anvil, the Imperial chapel and the Legion fort.
  Each carries stars for how far the Workshop trusts itself in it.
- **Stairs**: placed where they fit and kept there while you change the rooms; drag, turn, keep or
  place them by hand. **One stairwell** through every floor, stacked (flights over each other, facing
  the same way, with the walk round each landing) or in a line. Two-storey halls in Redoran and
  Hlaalu manors.
- **Grow a built house**: add a room through an outer wall, **Extend by piece** from the pieces the
  game stands at each open edge, or **Remove this room**.
- **Fix here** and **Find gaps**: right-click any joint for what the game's own places of that style
  stand there; Find gaps looks round a place as a player does for void showing through, walls seen
  from behind, boxed-in stairwells, posts in walls and naked edges, with **Fix everything**.
- Outdoor buildings too, with the door where you choose.

### Auto-furnish
- One button furnishes a house: furniture, clutter, lights and wall hangings at the game's own rates
  for each kind of room, laid as the game's scenes (a bed with its chest, a table with its chairs and
  rug, the scribe's desk, the alchemist's bench).
- Bedrooms, studies, libraries, dining rooms, kitchens with whole hearth sets, shops, trade rooms
  (a smithy round its forge, alchemist, enchanter, bookseller, clothier), taverns, storerooms, baths,
  hallways, barracks, armouries and shrines; planters and garden beds with plants that fit them.
- Dressed shelves, tables, counters and racks with what the game puts on that model; hanging lights
  at the game's gap below the ceiling; nothing floating or through walls.
- **Furnish as** a wealth level, trade or faction; **Furnish like** a place you admire; a **taste
  set** of places you like; **Dress this**, **Add one thing** and **Furnish this room**.
- **Check this place**: furniture through walls, things floating, lights whose chain doesn't reach,
  fire things with no hearth, smith's tools with no forge, halls you can't walk through, and common
  interior-design guidelines, each with Show me and a one-Undo fix.

### The world map, in 2D and 3D
- Place, move, turn and scale with snapping, grid and wireframe; land things on surfaces; box select.
- **Windows over the view**: an object's record and placement side by side, with what you can do
  with that kind of thing; **Create here…** makes a container, item, note, person, spell, magic
  effect or new place at the spot you clicked.
- **Suggested for this place**, right-click menus (swap, replace all, retexture, add a sound, hide),
  **secret entrances** (rotating and sliding panels, with levers, sconces or books as switches and
  riders that slide along), landscape sculpting and painting, groundcover and scatter brushes, path
  grids, and **My changes** on the map with per-change undo.

### Magic of your own
- **New magic effect**: looks taken from a template effect, its own name, icon and cost, and steps
  that fire as it lands, each second or as it ends, filtered by target and with a chance: health,
  magicka or fatigue, push, pull, launch, dash, grow or shrink, calm, frenzy, aura, leech, swap
  places, cast a spell, change the weather, transmute, teleport, place an object, set a global,
  show a message, or your own Lua (checked, and the Assistant can write it).
- **Tamriel Data's effects** usable in your spells, enchantments and potions.
- Both are written as an OpenMW Lua load script, so they need OpenMW 0.50+ and the mod as an
  `.omwaddon`.

### Everything else in a mod
- Browse every record in your load order; create and edit people, creatures, items, books, spells,
  enchantments, dialogue, quests and journal stages, Morrowind scripts and OpenMW Lua scripts (checked
  as you type), factions, classes, races, regions, weather, globals and game settings.
- **Open an existing `.esp` as your mod** and save straight back into it, or **Save as…** a new
  `.esp` or `.omwaddon`. **Your mods**: show folder, switch, delete to the Recycle Bin.
- Load order, **Merge mods**, and **Get ready to share** (verify, readme, zip).
- **Library**: bring in your own models (`.blend` read directly, `.obj`, `.fbx`, `.dae`, `.gltf`,
  `.glb`, `.nif`), pictures and sounds; prefabs and shareable packs.

### Live link and building together
- Start the game from the Workshop and edits appear in it straight away; **Play as** your own
  character from a save; test setups; build in game with Shift-key tools; quest testing.
- **Build together**: up to eight people on one mod, changes shared within a second, each person's
  own undo.

### Workspace
- Every tool is a panel you can float, dock and tab; saved layouts; Ctrl+K command palette; your own
  shortcuts; preset themes or **your own**; Recent messages.

### Optional AI assistant
Builds and changes things from a plain request, drafts dialogue and writes Lua for magic effects,
using Claude through the user's own Anthropic API key. Everything else works without it.

## How it learns to build and furnish

There are no hand-written rules for where a bed or a stairwell goes. On first use the Workshop
surveys the interiors in the installed game data and builds and furnishes from those statistics. The
surveys are counting and geometry, run locally, not machine learning; they take about five minutes
once, run in a separate process, and are cached.

- **Furnishing surveys** record which furniture and clutter each kind of room holds, how often and in
  what groups; where each model stands (wall, corner, column foot, open floor) and its clearances;
  how far each hanging light hangs below the ceiling; and what sits on each shelf, table, counter,
  planter and hearth.
- **Building surveys** read how each style's pieces join: which wall meets which corner, the posts,
  columns and door frames at each joint, how stairwells are enclosed and what closes an open edge.
  The builder and Fix here only lay a piece where that style puts one.
- **Checks** (Find gaps, Check this place) are measured against about a hundred existing interiors
  before they are used, so they flag real faults and not the game's deliberate choices.

## What it is made of

- **`app/`**: the Workshop itself, a small web server written in Python (standard library, plus
  Anthropic's `anthropic` library for the optional AI assistant and `zstandard` for Blender files)
  and its page (`app/web`, plain HTML and JavaScript, with three.js and two fonts bundled in
  `app/web/vendor`).
  - `workshop.py` starts it and serves the page and its API. `database.py` and `esm.py` read
    OpenMW's settings, plugins and archives; `editing.py` and `project.py` keep your mod;
    `adopt.py` opens an existing `.esp` as the mod; `modfiles.py` lists, shows and deletes your mods.
  - **Building**: `builder.py` and `kits.py` build places from a style's room pieces; `plans.py` and
    `planfrom.py` are the planner's plans and reading a game place back as one; `extend.py` adds a
    room through a wall; `adjacency.py` is the piece-to-piece survey behind Extend by piece;
    `stairtemplate.py` reads how the game lays the pieces round a staircase; `styletrust.py` the stars.
  - **Gaps and joints**: `seethrough.py` casts rays against the models' real shapes to see what a
    player would see through; `fixit.py` finds and closes gaps; `joints.py` and `fixhere.py` are
    Fix here; `edges.py` reads open-shell meshes for naked edges.
  - **Furnishing**: `furnish.py` lays rooms out; `placecheck.py` is Check this place; `roomscore.py`
    scores a room against the game's; `roomrules.py` decides what each kind of room gets, from the room survey; `taste.py` the
    taste set; `hanggap.py` the hanging-light heights.
  - **Surveys**: the `*survey.py` files (rooms, furniture groups, scenes, shelves, counters, shrines,
    gardens, hearths, halls, trade rooms, stairs, walls, joints, wealth…) each read one thing from
    the game's interiors; `learning.py` and `surveyworker.py` run them in a separate process and
    cache the results.
  - **Magic**: `items.py` and `items_ed.py` are items, spells, enchantments and potions;
    `myeffects.py` makes your own magic effects and their Lua; `tdeffects.py` brings in Tamriel
    Data's effects; `lua_check.py` checks Lua before it is saved.
  - **Library**: `library.py` reads OBJ, glTF, COLLADA and FBX, `blendread.py` Blender files, and
    `nifwrite.py` writes Morrowind models; `pack.py` and `packshelf.py` make, open and share packs.
  - **World**: `landscape.py`, `grass.py` and `scatter.py` the land and its brushes; `pathgrid.py`
    walking paths; `mechanism.py` and `riders.py` secret entrances and what rides on sliding panels.
  - **Game and people**: `link.py` and `link_scripts/` are the live link (OpenMW Lua scripts);
    `saves.py` reads OpenMW's saves for Play as; `together.py` and `upnp.py` are building together;
    `uses.py` is the Use report; `verify.py` and `release.py` Get ready to share; `merge.py` Merge
    mods; `ai.py` the assistant.
  - In `app/web`: `panels.js` is the panel system, used by `worldpanels.js` (World map) and
    `pagepanels.js` (the other pages); `world3d.js` the 3D view; `planner.js` the room planner;
    `viewwin.js` and `objwin.js` the windows over the 3D view; `effects.js` the magic effect maker;
    `comfort.js` the status bar, right-click menus, Ctrl+K palette and shortcuts; `qol.js` the modder
    comforts; `setups.js` Play as and test setups; `pathedit.js` path grids by hand; `theme.js` the
    themes, including your own.
- **`packaging/`**: everything that turns `app/` into the Windows installer.
  - `build.py` makes `packaging/out/Morrowind Workshop Setup.exe` and the portable zip.
  - `launcher.cs`, `appwindow.cs`, `setup.cs` and `common.cs` are the small Windows programs in it
    (the launcher, and the installer); they are compiled with the C# compiler that comes with Windows.
  - `README.md` is the readme that goes into the installer.

## Requirements

Windows 10 or 11 (64-bit), [OpenMW](https://openmw.org/downloads/) 0.49 or newer set up with its
Launcher (0.50 or newer for custom and Tamriel Data magic effects; built and tested with 0.51), and
Morrowind. It works only with OpenMW, not the original engine.

## Running it from the source

1. Install OpenMW and set it up with its Launcher, so it knows where Morrowind is.
2. Install [Python 3.13](https://www.python.org/downloads/) (64-bit).
3. Double-click **`Start Morrowind Workshop.bat`**. It installs the `anthropic` and `zstandard`
   libraries the first time and opens the Workshop in your browser.

## Building the installer

See [BUILDING.md](BUILDING.md).

## AI disclosure

The code in this repository was written with the help of Claude, an AI by Anthropic, under the
author's direction and testing. The Workshop contains no AI-generated game assets. Its optional
assistant uses Claude through the user's own Anthropic API key.

## Licence

The Workshop's own code is © 2026 Nemo and licensed under
[Creative Commons Attribution-NonCommercial 4.0](LICENSE.cc-by-nc-4.0.txt): you may share and
change it, with credit, but not for commercial purposes. See [LICENSE](LICENSE).

The bundled third-party files keep their own licences: three.js (MIT) and the Cinzel and Inter fonts
(SIL Open Font License 1.1), in `app/web/vendor` with their licence texts in
`app/web/vendor/licenses`. The installer also includes Python (PSF License), the `anthropic`
library and its dependencies (MIT, BSD, Apache 2.0) and `zstandard` (BSD); the built installer lists them all in
`THIRD_PARTY_NOTICES.txt`.

Not made by or affiliated with Bethesda Softworks or the OpenMW project. Contains no Morrowind files.
