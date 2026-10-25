<img src="app/web/logo.svg" alt="Morrowind Workshop" width="200">

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
  grids (by hand, or **Redraw** by Project Tamriel's rules, measured on 100 of the game's places), and
  **My changes** on the map with per-change undo.

### Dungeons
- **Create > Dungeon**: a Dwemer ruin, a cave (grey stone, brown earth, pale rock or lava rock), a
  Velothi tomb or a Daedric ruin, grown from its front door the way the game's own of the kind are put
  together. Every piece joins where the game joins it, there are halls, chambers or rooms on the way and
  at the far end, door frames with their doors, and every passage ends in a dead end.
- Each piece is dressed the way a real piece of its kind was in the game: lights, rocks, urns, pipes,
  chests and creatures. Bare tables are set the way the game's own dungeons of the kind set theirs, more
  or fewer by the loot asked for. The last hall has the kind's best chest and a guardian (a Daedric
  ruin's is a shrine with its Prince's statue, offerings and cursed gems). Some have someone living in
  them (Populate's people, their camp laid as the game's own cave camps are: beds against the rock, goods
  by the walls, now and then a fire), and the walking paths are drawn.
- Then the place is checked and tidied: crates and chairs set level, nothing through anything else, no
  lamp hanging on nothing, nothing standing in the way from the front door.
- **A tool, not a form**: the plan of the layout is drawn as you choose, flat or as a 3D sketch you can
  turn, and Make builds exactly that plan. Options: size, levels (ramps up and down), layout (one winding way, branching, a maze), water
  (dry, pools, flooded caves), creatures, loot, lived in, and a door outside. 🎲 for another layout, ↶
  for the one before. On the World map it opens in a window over the 3D view.
- Learnt from the game's own places of each kind, once (15–20 s each).

### Magic of your own
- **New magic effect**: looks taken from a template effect, its own name, icon and cost, and steps
  that fire as it lands, each second or as it ends, filtered by target and with a chance: health,
  magicka or fatigue, push, pull, launch, dash, grow or shrink, calm, frenzy, aura, leech, swap
  places, cast a spell, change the weather, transmute, teleport, place an object, set a global,
  show a message, or your own Lua (checked, and the Assistant can write it).
- **How it looks, part by part**: the casting glow, bolt, hit, area burst, particles, colour, speed and
  the four sounds, each taken from any of the game's effects.
- **Icons from your own pictures** (PNG, JPG, DDS, TGA; from the Library or your PC) for effects and
  items: cropped, written at twice the game's size with the large `b_` spell icon, packed with the mod.
- **Tamriel Data's effects** usable in your spells, enchantments and potions.
- Both are written as an OpenMW Lua load script, so they need OpenMW 0.50+ and the mod as an
  `.omwaddon`.

### Populate
- **Populate this place** (right-click in the 3D view): people who would live or work there, as the
  game's own places of that kind have them, proposed first and placed only when you say. Each is a new
  person: race, sex, a name in the manner of their race (a household shares a family name; a home of
  two is a married couple as often as the game's own homes of two are), a face, a
  class, faction and rank, level, an outfit built slot by slot (armour of one make, by faction where the
  game has it), things they carry, a few spells, how they greet, fight and wander, what they sell. They
  stand where the game stands their kind (the trader behind the counter), and the household owns its
  beds and chests.
- Parameters: how busy, wealth, kind of place, faction, races, occupations; lock, re-roll, rename or
  change anyone; **Someone who'd live here** for one person at the spot clicked.
- **Words of their own**, written offline from templates: greetings for a first meeting and later, my
  trade, lines about each other (kin, the head of the house, servants, friends, rivals), a little secret
  and a rumour. The Assistant only writes when asked (✦).
- Learnt from the game's people: every place with people in it is read once (about 30 s), what kind of
  place it is, and who is there.

### Dialogue
- **Write a conversation**: one character's topic (or greeting) as a tree of versions (the first that
  fits is said), what each line does, and the player's answers, each leading on. Saved, it becomes the
  topic's own lines, with the answers numbered and ordered the way the game needs; the game's own
  conversations are read back as trees from their lines, and only lines you change go into your mod.
- **Conversation map**: everything a character says, laid out from their greeting, with the topics
  each line mentions or adds and the quest stages it needs and sets.
- **What would they say?**: a tester that picks their lines the way the game does for a state you set
  (quest stages, items, race, faction, disposition, globals…), follows what each line does, explains
  each pick condition by condition, and names your lines that can never be said.
- **A quest's flow**: its stages left to right, who says what in rows, and arrows to the stage each
  line moves it on to.

### Everything else in a mod
- Browse every record in your load order; create and edit people, creatures, items, books, spells,
  enchantments, dialogue, quests and journal stages, Morrowind scripts and OpenMW Lua scripts (checked
  as you type), factions, classes, races, regions, weather, globals and game settings.
- **Open an existing `.esp` as your mod** and save straight back into it, or **Save as…** a new
  `.esp` or `.omwaddon`. **Your mods**: show folder, switch, delete to the Recycle Bin.
- Load order, **Merge mods**, and **Get ready to share** (verify, readme, zip).
- **Library**: bring in your own models (`.blend` read directly, `.obj`, `.fbx`, `.dae`, `.gltf`,
  `.glb`, `.nif`), pictures and sounds; prefabs and shareable packs.

### Models, textures and animations
- **Model & textures** for anything (right-click it):
  - what it is drawn with, and where each file comes from;
  - its textures, with pictures, and what uses them.
- **Change a texture** in your picture editor, everywhere or for one object. The 3D view redraws it each
  time you save. Missing textures can be found and fixed.
- **To Blender and back**: the model with its textures opens in Blender, and each Ctrl+S brings it back
  exactly, everywhere or as its own object.
- **Animation & text keys**: creatures, people and moving objects played as the game animates them.
  - Edit the text keys that name the groups and time the sounds.
  - Trim a group, or change its speed.
  - Give a creature another one's animation, when their skeletons truly match.

### Live link and building together
- Start the game from the Workshop and edits appear in it straight away; **Play as** your own
  character from a save; test setups; build in game with Shift-key tools; quest testing.
- **Build together**: up to eight people on one mod, changes shared within a second, each person's
  own undo.

### Workspace
- Every tool is a panel you can float, dock and tab; saved layouts; Ctrl+K command palette; your own
  shortcuts; preset themes or **your own**; Recent messages.
- In the 3D view, a preview of the weather (rain, snow, ash and blight falling) and of the time of day:
  the sky, sun and light through the day in the game's own colours for each weather, from openmw.cfg.
- In the 3D view, a measuring grid that stays where you put it: level on a floor, upright along a wall,
  or set at and turned to the selected object.

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
  - **Assets**: `assets.py` is the Model & textures window (texture copies, thumbnails, the `.glb`
    round trip to Blender, missing textures); `nifanim.py` reads skeletons, skins, keyframes and text
    keys, and retimes, trims and swaps animations.
  - **World**: `landscape.py`, `grass.py` and `scatter.py` the land and its brushes; `pathgrid.py`
    walking paths; `mechanism.py` and `riders.py` secret entrances and what rides on sliding panels;
    `dwemer.py` the dungeons (Dwemer ruins, caves, tombs, Daedric ruins).
  - **Dialogue**: `dialogue.py` reads and writes topics, lines and quests in the game's order;
    `convo.py` works out what a character can say and which line wins for a given state (the map,
    the tester and a quest's flow); `convbuild.py` turns a character's lines into a conversation tree
    and back.
  - **Populate**: `castsurvey.py` reads who the game's people are, place by place; `peoplesurvey.py`
    where they stand; `populate.py` proposes a cast and places it; `poplines.py` writes their lines.
  - **Game and people**: `link.py` and `link_scripts/` are the live link (OpenMW Lua scripts);
    `saves.py` reads OpenMW's saves for Play as; `together.py` and `upnp.py` are building together;
    `uses.py` is the Use report; `verify.py` and `release.py` Get ready to share; `merge.py` Merge
    mods; `ai.py` the assistant.
  - In `app/web`: `panels.js` is the panel system, used by `worldpanels.js` (World map) and
    `pagepanels.js` (the other pages); `world3d.js` the 3D view; `planner.js` the room planner;
    `viewwin.js` and `objwin.js` the windows over the 3D view; `effects.js` the magic effect maker; `dialogue.js`, `convo.js` and `convbuild.js` the Dialogue
    page, its map, tester and conversation builder; `populate.js` the cast window; `ruins.js` the
    Dungeon card;
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
