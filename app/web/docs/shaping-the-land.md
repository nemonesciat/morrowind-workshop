# Shaping the land

*How to change the ground outdoors: by hand with the Ground brush, or many cells at once with land shaping.*

## Which tool to use

| You want to… | Use |
|---|---|
| Nudge a hill, dig a hollow, level a spot for a house, paint a path | **The Ground brush** (in 3D) |
| Scatter grass, plants, rocks or trees | **The Ground brush**, Scatter |
| Rocks and cliffs over land that's there (an island you raised, ground you sculpted) | **🪨 Dress…** (the Land panel, on the marked cells) |
| Make an island, a mountain range, a river valley or cliffs over many cells | **Land shaping** (the Land panel) |
| Make smooth, plain land (a heightmap mod's, or your own) as rugged as hand-made land, over whole regions | **Region pass** (the Land panel) |
| Fill a region with towns, villages and dungeons, as many as the game has and where it puts them | **Places** (the Land panel) |
| Work on the land in World Machine, Gaea, GIMP or Krita | **Height maps** (the Land panel) |

Every change goes into your mod and comes back with one **Undo**. Changes to the ground show in the game
after you restart it.

## The Ground brush

Open a place outdoors on the World map, switch to **3D**, and press **⛰ Ground** in the toolbar. Then drag
on the ground. A plain click does nothing, so you can still select things.

| Tool | What it does |
|---|---|
| ▲ Raise / ▼ Lower | Raises or lowers the ground under the brush. Hold **Ctrl** for the opposite. |
| ≈ Smooth | Evens out bumps. |
| ▬ Flatten | Levels the ground to the height where the stroke started. |
| ◢ Ramp | A sloped path. Click its foot, then its top: the ground between becomes one even slope, level from side to side, with a level landing at each end. **Shift+click** first for bends; Backspace takes a point back; Esc gives it up. The ring shows how far it reaches either side (Size). The top bar says how steep it is, in red past 40°. One Undo. |
| 🖌 Paint | Paints a ground texture. Pick one from the list, or take the one on the ground: **💧 Pick**, then click it (or **Shift+click** it any time). **✨ Auto** paints each patch the way the region's own land is painted where the ground is like it (as steep, as high, on a crest or in a hollow, by the water or not), copying the game's layout so textures meet as they do in the game (roads and paving stay). **Like** takes another region's textures. |
| 🎨 Tint | Paints the ground's own colour (the shading the game multiplies into its textures). **Ctrl** paints back to plain; **💧 Pick** (or **Shift+click**) takes the colour there. |
| 🌿 Scatter | Scatters the region's own grass, plants, rocks or trees. **✕ Remove** (or **Ctrl**) clears away what the brush scattered, of the kinds ticked: never the game's own nor what you placed by hand. |

- **Size** is the brush's reach in game units (a cell is 8,192 across; the land has a point every 128, so 64 moves
  just the one under the brush). Type a size in the box, or press **[** and **]**. **Strength** is how much each pass
  changes (not used by Scatter).
- **Objects follow the ground**: things standing on it (rocks, plants, people, crates) move up and down with
  it. Buildings move too, so turn it off when you are fitting the ground to a building.
- Each stroke is saved when you let go, as one Undo step.
- The brush can't make a step steeper than the game's land can hold (about 83°).
- Drag the Ground window by its title to move it, or by its bottom-right corner to make it bigger. It keeps its
  place and size.

### Tint: shade automatically

Under Tint, three buttons shade the cell under the camera (or it and the eight around it) the way the
game shades its own land nearby: **Where textures meet** darkens the joins, **By texture** gives each texture
its usual tint, and **Hollows** darkens the hollows and lightens the crests. **Amount** sets how strongly.

### Scatter

- Pick a set (Grass, Flowers & plants, Rocks & stones, Trees, Logs & stumps). They are learnt from the region
  you're in, the commonest first; untick any you don't want. **＋ New brush** makes a set of your own, with
  any objects, from mods too.
- **Your own brush**: add things with the search. Each row shows its picture and its share of what the brush
  scatters. **Often** sets how often it comes up against the others; **Size** is the smallest and biggest it can be.
  **⤓ Share** saves the brush as a file, **⤒ From file** adds brushes from one, and 🗑 deletes it.
- **▦ / ☰** beside the search: pictures or a list. As pictures, the search shows a grid you click to add from
  (✓ marks what's on the brush), and clicking one of the brush's pictures opens its Often and Size.
- **Thickness**: 5 is as thick as the game has that kind; 10 is about three times as thick, 1 under half.
- One stroke makes at most 1,500 things (15,000 grass tufts). Let go and paint again for more.
- **Grass as groundcover** goes into its own grass file next to your mod. OpenMW draws it fast, sways it,
  and lets you walk through it. **Grow it over this cell** (or **…and around**) grows it on the grassy
  ground of whole cells.
- **Your own brush as grass:** tick **Paint as grass (groundcover)** on one of your brushes to paint it into the
  grass file instead of the mod. It suits small plants and tufts, since groundcover can't be touched or picked.

## Land shaping: how it works

Land shaping changes many cells at once. It's on the World map's **Land** panel, on the flat map (not in 3D), and
it goes in stages, in the order you'd build a place:

1. **🖌 Mark** the cells to work on.
2. **Land**: draw features (a coast, a ridge, a river…) and tick **Shape the rest automatically** to have the rest of
   the marked land made like a hand-made region round them. Press **Make land**. With it ticked, **Clear first** (shown
   when there's something to clear) takes other mods' objects out of the cells being made: Tamriel.esm's low-detail
   **stand-ins** (with the region's real trees and rocks where its trees and rocks stood), **trees, rocks, plants**, or
   **everything**. Your mod marks them removed, so turning it off brings them back; kept land is never cleared.
   **Trees** and **Plants** (0 to 2) set how thick it's dressed: at 1, a real tree for each of Tamriel.esm's stand-in
   trees, and plants as the region grows them.
   **♣ Cover** is an outline you draw, then pick what grows inside: **forest**, **swamp**, **grassland**, **rocky** or
   **bare**, and a **Density**. Each kind takes after the nearest hand-made region with the most of it (forest: the most
   trees a cell; swamp: the nearest marsh or the Bitter Coast); **Like** picks another. Make land lays it in place of the
   automatic dressing inside the outline.
3. **Places**: draw towns, castles, roads, farms and dungeons, or press **🎲 Suggest**. Press **Make places**. Towns
   go up from the outside only.
4. **Insides and people**: the towns' interiors, the dungeons, people and creatures, rumours and quests. Press
   **Make insides**.

After each Make, look it over on the map and in 3D, then:

- **✓ Keep**: it stays. Its shapes leave the map; the land kept is where the next Make starts, and the automatic
  shaping leaves it alone (a feature you draw over it later still shapes it).
- **↻ Try again**: it's taken back and made again, rolled anew.
- **✕ Drop**: it's taken back.

Each stage is one Undo step. **Only marked cells ever change**, and the edge a marked cell shares with an unmarked
one stays as it is. Each stage's ⚙ holds its settings.

## Step 1: mark the cells

Press **🖌 Mark** and drag over cells to mark them; **⌫ Unmark** and drag to unmark. **Shift**+drag marks or unmarks
a box. Right-drag moves the map while you mark. A game town's cells are left out unless you hold **Ctrl**. Press the
button again, **Done** or Esc to stop.

The **⋮** menu has **Clear marks**, **🪨 Dress…**, **↶ Undo my land** (the land in the marked cells back as it was
before your mod), **⤓ Set loose things down**, the **Land map** colours, **Where water runs**, and height maps.

**⤓ Set loose things down** lifts your mod's crates, barrels, sacks, baskets, clutter and furniture in the marked
cells out of the dirt, and lets down what hovers just over it. What stands on a thing follows it. Rocks, plants,
fences, posts, building pieces and anything hung stay as they are. On a slope a thing is let a little into the
ground on its uphill side. One Undo takes it back.

The land map's colours:

| Colour | Means |
|---|---|
| Sea bed | Under the sea. |
| Wild / Light | Land with little or some building on it. |
| Settled | A town or a place with many buildings. |
| Another mod's (hatched) | Land from another mod. Your mod overrides it. |
| Yours (dashed) | Land your mod has already changed. |
| Room to grow (dashed blue) | No land in any plugin yet, next to land. |

**Show where water runs** draws the way the rain would run over the marked cells, in blue: thicker where more
ground drains through. With shapes, it follows the plan's preview; without, the land as it is. Brighter lines are
where **Stream beds** (Dressing) would texture the ground.

**Shapes mark their own cells:** drawing a feature, moving its points or widening it marks every cell it reaches,
except towns. Dress areas mark nothing.

## Step 2: draw shapes

Press a shape's button, then draw on the map. **Backspace** takes the last point back; Esc cancels. With no
cells marked yet, your first shape marks the cells it reaches (towns left out).

Or **Start from** a ready plan, laid out over the marked cells (or the 4 × 4 cells round the view, which it then
marks), in place of the shapes there: **Island**, **Mountain range**, **River valley**, **Volcanic isle** or
**Lake in the hills**. Change any of its shapes and sliders from there; ↶ takes it back.

| Shape | How to draw | What it makes |
|---|---|---|
| 🏝 Coast | Click along the shore all the way round; click the first point to close. | Your outline becomes the waterline: inside rises out of the sea, a strip just outside goes under water. **Sea outside** sinks all other land in the marked cells too. |
| ⛰ Ridge | Click along the crest; double-click to finish. | A range: **Crest** height, **Width** to its foot, **Sharp** (rounded to knife-edge), **Spurs**, **Crags**. |
| 〰 River | Click from the source down to the sea; double-click. | A bed under the water, banks rising to the ground. The game has one water level, so rivers are dug down to it. **A canyon** makes steep walls. |
| ⇣ Spring | One click where a river rises. | The river finds its own way down to the water: a dry ravine up high, then a winding river below **Water from**. |
| ⌄ Valley | Click along the floor; double-click. | A dry trough: **Depth**, **Width**, **U or V**. |
| ▭ Plateau | Click round the top; click the first point to close. | A level **Top** with a **Cliff** round it, in **Terraces** if you like. |
| ◍ Lake | Click round the shore; click the first point to close. | A basin under the water line. |
| ◉ Stamp | One click. | A volcano, cone, caldera, crater, dome or mesa, or a piece of **the game's own land** (copy up to 6 × 6 cells). |

- The shapes are listed in the panel. Click one in the list, or its line on the map, to pick it and change its
  sliders. The tick turns a shape off without removing it; ⧉ duplicates it; ✕ removes it, **Clear shapes**
  removes all.
- **Editing a picked shape on the map:**

  | To | Do |
  |---|---|
  | Move a point | Drag it. |
  | Add a point | Click the shape's line where it goes (and drag it). |
  | Remove a point | **Ctrl**+click or double-click it. |
  | Join two points | Drag one onto the other (a ring shows the one it will join). |
  | Move the whole shape | Drag the cross in its middle, or **Shift**+drag its line. |
  | Resize it | Drag a corner of the box round it. |
  | Turn it | Drag the round knob over the box (**Shift**: 15° steps). |
  | Undo a shape edit | **Ctrl+Z** (Ctrl+Y redoes) while the Land panel is open and a shape edit was your last change. |

- **↶ ↷** (by Shapes) undo and redo changes to the shapes and their settings, Clear shapes included. They are
  the plan's own; the Undo at the top undoes changes to your mod, such as Make land.
- **Order matters**: each shape acts on what the ones above it made (↑ ↓ to reorder). Rivers, lakes and
  springs always go last, so they cut through what the others raised.
- **Only in** (on a shape) limits it to one region of the marked cells, fading out at the border. **Like**
  gives its ground another region's character, for example a ridge as craggy as the Druadach Highlands, while
  the textures stay the cell's own.

## Step 3: the preview and the settings

The map shows the plan's land over the marked cells, about half a second after you stop sliding. **Nothing
in your mod changes until you press Make land.** You don't have to touch any setting below: each starts at
the region's own figures.

A big plan (a long coast over a hundred cells) can take a minute or more to preview: the map counts the seconds,
and the top bar shows **⏳ Previewing the land**. Everything else goes on meanwhile. **✕** on it stops the preview;
it runs again when you change a shape.

### Protection

Each Make starts from your land as it is now: a stage tried again or dropped is taken back first, so nothing stacks.

**Hold the ground under buildings, ruins and doors** keeps the ground exactly as it is under them (outlined
on the map), fading back to the plan over the **Margin**. Rocks, plants, people and paths move with the
ground instead.

### Natural passes

| Setting | What it does |
|---|---|
| Match the region's roughness | Adds rolling detail (or smooths) until the new land is as rough as the region's own. |
| Valleys | Rain carves branching valleys: deep where much ground drains, faint on small slopes. |
| Rock layers | Bands of hard and soft rock: hard ones stand as cliffs with ledges on top, soft ones wear back to scree. **Layer height**, **Hard rock** (how many bands are hard), **Tilt** and **Tilt way** (tilted layers make one-sided ridges), **Only in**. |
| Rain gullies | Raindrops cut small gullies and leave fans at their feet. |
| Settle the steepest slopes | Ground slides down where it's steeper than the region's own steepest. |
| Round the corners | On by default. The corners of what you drew are rounded before shaping, and the creases and facets the shapes leave are eased afterwards, so a plateau or valley drawn with a few clicks has no straight edges or sharp bends. A made town rounds its own ground the same way, keeping its streets, plots, paths and wall. |
| Terraces | Steps up the slopes (the Ashlands look). |

### Dressing

| Setting | What it does |
|---|---|
| Like | The region whose land the plan takes after: textures, tints, roughness and slopes. Default: each cell's own. |
| Put the cells in this region | Its weather, sounds and creatures go with the land. |
| Textures | How many textures a cell: as many as the region's cells have, or fewer or more. |
| Shores | As the region lays them (West Gash's shores are rock, Nedothril's half sand), or **sandy** beaches or **rocky** shores whatever the region: at the water's edge and on the flat ground just over it, in the region's own sand or rock texture where it has one. Also in Texture only. |
| Tint, seams, hollows, Shading | The region's own colouring, laid on as the game does. |
| Rocks | The region's rocks on the new slopes and cliffs, as thickly as the game sets them on such ground, at the foot, on the face and at the crest, turned to the slope as the game turns them. |
| Rock the steep ground | On by default. The steep ground of a ridge, valley, river or plateau is clad the way the game's gorges and hilltops are: the region's big cliff pieces on the faces first and smaller rocks filling in, until the faces are as much under rock as the region's own; smaller rocks on the lip just above and boulders at the foot; rocks along the water's edge; and on a knoll (a hilltop of 300 or more) an outcrop packed into one mass, as the game's hills that read as mountains have. Every piece is sunk until no bottom edge shows: the open rim of its mesh is checked point by point against the ground and the rocks round it, and a piece that would need sinking more than most of its height is left out. Nothing goes on roads, under buildings or in the water. Off: the plain rock scatter alone. |
| Stream beds | Where much water runs, the region's water's-edge textures (mud, wet ground), so streams show. Off by default: the Bitter Coast's own land does this, most regions' don't. Also in Texture only. |

### Texture only

**🎨 Texture only** textures the marked cells without reshaping them: each 512-unit patch gets the texture the
region's own land has at that slope, height and distance from the water, with the region's tints and shading.
Each cell gets about as many textures as the region's own land cells have, in patches as broken up as theirs,
so no single texture covers the land in big repeating blocks. Make land and Raise texture new land the same way;
land textured before keeps its textures until you texture it again. It's
under Dressing when you have shapes, and in **Texture the land** when you don't.

- **Like** takes the textures of another region; **Textures** sets how many a cell.
- Heights never change, and no land is made. Roads, paths and paving keep their textures, and with **Keep the
  ground under buildings** (Protection) so does the ground under what's built.
- One Undo takes it back.

At the bottom: **Roughness**, **Edge fade** (how far in from the marked cells' edge the shapes fade in), **Only
in** (the whole plan in one region), **🎲 Re-roll** (the same shapes with other rolling ground and shores).

## Region pass

Some land is smooth from far off and plain up close: land made from a heightmap, or land you raised. The **Region
pass** makes the marked cells' land as it is as rough, as broken into ranges and as cut by valleys as land made by
hand, with no shapes drawn. Tick **Like hand-made land** (Land panel, under Shapes), watch the preview, then press
**Shape the ground**.

| Setting | What it does |
|---|---|
| Like | The hand-made region whose roughness and slopes the land takes on. **Nearest in relief** (the default) picks for each region the hand-made one closest to it in relief: plains take after gentle land, mountains after mountains. The panel says what each region takes after. |
| Ranges | Side crests and spurs between long, smooth ridges, about as far apart as the game's. Only on land standing over its valleys: plains stay plains. |
| Relief | Rolling ground and crags down to the smallest bumps, until the land is as rough as the region it takes after; craggier where the land already rises, gentle on the flats, fading out near the water. |
| Valleys | The rain carves valleys into the result, deep where much ground drains. |
| Cliffs | Hard rock stepped into cliffs and ledges where the game keeps its steep ground: on land high over its valleys, mid-slope, where the land round it is rough; not at the streams or on the plains. As much steep ground as the region it takes after has. The new cliffs get the rock texture of such ground (the region's own, else the one the cliff pieces come from), the steeper the more of it. |
| Rock the cliffs | Clads the steep ground in cliff pieces, as the game clads its own: faces, lips along the top, feet along the bottom and outcrops on the hilltops, each piece sunk so its bottom edge never shows. The land's own scattered rocks stay and follow the ground. |
| Rock | Whose cliff pieces. **Nearest in weather** (the default) takes the region's own where the game clad its cliffs, else those of the region nearest it in weather and on the map that did and whose ground looks like this land's (snowy land gets snowy rock, a province its neighbours', and no red sandstone on dark green land); land named for a hand-made region takes that region's. The panel says whose; pick another here if it doesn't fit. |
| Trees in groves | The land's own trees stood as the game stands its trees: ten times fewer on cliffs than on the flat, gathered into groves (a few more of the same kind grown round the trees in a grove, fewer in the open between). Trees you placed yourself, and trees by buildings, stay. Pressing again puts the same trees back first. |
| Plants | Plants where the land has none of its own: those of the nearest region in weather and on the map that has (Cyrodiil's or Skyrim's from their own lands), laid as that region's own land grows them, about as many as the game sets (some 20 a cell). The panel says whose. |
| Waterfalls | Where a stream that drains half a cell or more drops over the new cliffs, a waterfall as the game lays them in its mountains: the fall scaled to the drop and turned down the stream, a round plunge pool dug into the ground at its foot (with a rim, so no edge stands in the air), mist and the sound of falling water. About one fall for every three mountain cells, none on gentle land. Uses Tamriel_Data's water pieces; nothing is set if they're missing. |
| Texture it too | Textures the land again by its new slopes (with the Dressing settings), and blends them over the region borders as the game does: within a few hundred units of another region a patch often takes that region's texture, less and less to about two kilometres in. Off: the textures stay as they are, but for the cliffs'. |

- Only marked cells change, and Protection works as for shapes: by default it starts from the land under your mod,
  so pressing it again doesn't add more on top, and the ground under buildings, ruins and doors is held. At edges
  with land you haven't marked it fades back over a longer way than the Edge fade when the new land differs much
  from the old (up to a cell), so cliffs and valleys ease out instead of ending in a crease.
- **Cells side by side:** where the marked cells meet land your mod has already changed (an earlier press), the new
  land is joined to it with no step and no smooth strip between; the edges with other land fade back into it.
- **Big areas:** up to 2,048 cells at once. Past 400 it works in tiles of 16 × 16 cells, each joined to the ones
  before, and it is still one Undo. It takes about a second a cell with the cliffs rocked (a 20 × 20 block in about
  six minutes); the preview of a big area can take a minute.
- With shapes drawn too, the shapes go first and the region pass runs over all of it in place of **Match the
  region's roughness**.
- It plants no new kinds of tree and sets no rocks away from the cliffs: **🪨 Dress…** afterwards sets the region's
  trees and scattered rocks on the new ground if you want more.

## Places

**Town and Castle: draw the limits.** Press the button and draw round the place, in one stroke or point by point.
It is built inside the line you drew; drag its points to change it. Try again builds another in the same spot.

**Made** (under Make places) lists every town, castle, dungeon and interior the mod's Makes have built. 👁 goes there. ↻ Try again takes that one away and makes it anew with another layout. ✕ Drop only this takes away what it built and its interiors, whatever was made after it; what you added and the ground stay. Each is one Undo step. Places made by older versions are not listed.

Places is the second stage. **🎲 Suggest** puts towns, roads, dungeons, farms, small things and names on the map as
markers to move or drop; nothing is built. **Make places** lays the roads, builds the towns and castles (outsides
only) and lays the fields, docks, small things and names. The dungeons, the towns' interiors and the people come in
the third stage, **Insides and people**.

**🛤 Suggest roads only** (Places ⚙) is for after you move, add or remove towns: it joins them again.

**🎲 Suggest** (Places) lays towns, villages and dungeons over the marked cells as many
as the game has on as much land and on the ground it puts them: towns and cities by the sea and on big streams, on the
flat; villages on level ground; caves and tombs in hollows on steep slopes; Dwemer ruins high and steep. Each kind keeps
the game's spacing, and nothing is put by a place the land already has.

| Setting | What it does |
|---|---|
| Towns | Cities, towns and villages: 1 is the game's number for the land marked (about one village and one town for every forty cells, a city for every two hundred and fifty). |
| Dungeons | Caves, Velothi tombs, Dwemer and Daedric ruins, Imperial forts and Velothi towers: 1 is the game's number (about one cave for every five cells). |
| Small things | Camps, carts, graves, remains, wayside shrines, wrecks and fishing spots between the places: 1 is the game's number (about eleven for every hundred cells). |
| Culture | Whose towns they are planned like. **Nearest in weather** takes the game town nearest in its region's weather and on the map. Tombs and towers only stand on Dunmer land, as the game's do. |

- The places come as layers in the list, to move on the map, remove or keep. Proposing again replaces the proposed
  places you haven't built.
- **Towns** are ordinary town layers in the culture, sized like the game's (a village about 1,600 across its middle, a
  town 3,600, a city 8,900): **Make places** builds them as any town you draw.
- **Dungeons** are 🕳 markers where their door outside goes, each named in the culture's way. Pick one to change its
  kind, name or size, or **Build it**.
- **Make places** lays the fields, docks and small things; **Make insides** makes every dungeon and mine with the Dungeon tool (their doors facing down the slope), lays the
  fields, the harbours' docks and the small things, all as one Undo. A kind the Dungeon tool is still learning is left for later; build
  again once it has. Until then a dungeon's name on the map reads "not built yet"; a built one has a white ring.
- You can also add a 🕳 Dungeon marker by hand from the shapes' buttons.

### How the places grow

The places are laid in the order a land fills up, each kind placed by the ones before it as the game's own places
sit by each other:

1. **Cities and towns** first, on the best ground.
2. **Villages** in the gaps: the game's keep away from the towns rather than lie between them (half as often
   8,000–16,000 from a town as the land alone would give, a little more often past 16,000).
3. **Roads** joining them all and the game's towns near, as Propose roads makes them. They come with the places.
4. **Farmsteads** along those roads, about one for each settlement: a small town layer of two or three buildings
   living by farming (a plantation with its manor one time in three), a field beside it off the road. The game's farms
   stand on a road nine times as often as the land would give.
5. **Roadside inns**, as rare as the game's (about one for every five hundred cells), on a road away from the towns: a
   tavern and a building or two.
6. **Dungeons**: by the roads two to four times as often as elsewhere, but off the settlements (caves and tombs a
   quarter as often within 2,000–8,000 of one). Towers and forts stand near the towns. No door is put on a road.
   **Landmarks are put where the roads see them**, as the game's are: from points along the roads, the view is traced
   over the land to see which ground the road looks at. Daedric ruins stand where most of the road near them sees
   them, towers and wayside shrines lean that way, and caves and tombs keep out of sight in their hollows.
7. **Small things** last: what makes the way between places worth walking. Each is one of the game's own scenes as
   it stands, with what lies round it: a camp's bedroll, fire, stools and sacks; a cart left by the road with its load;
   an Ashlander cairn or burial banners; someone's bones and what they carried; a wayside shrine; a wreck on the beach;
   a fishing pole and a stool by the water. They stand where the game's do: carts beside the roads, camps on level
   ground away from the towns, remains in hollows, wrecks on the shore facing the sea, burial banners up high. Of a
   kind's scenes, the one whose ground falls most like the spot's is laid, one from the same region first. They are
   ✦ markers; **Make places** lays them on the ground as it is then, so make the land first.

Farmsteads and inns are town layers with fewer buildings and their kinds set (**How many**), built with **Shape, then
build** like the rest.

### Names of the land

Suggest also names a few of the land's features the way the game names its own, sparingly, each the name of
the one cell it stands in (the game's Mount Kand, Verulas Pass, Khartag Point, Lake Dolosamsi):

- **Peaks:** the most prominent tops, standing well over the land round them: "Mount …" ("… Peak" in Nordic lands).
- **Passes:** where a road crosses a ridge between higher ground either side: "… Pass".
- **Headlands:** land reaching out into the sea: "… Point". **Lakes** inland: "Lake …".
- **Crossings:** some of the bridges: "… Crossing".

About one name for every hundred cells, as the game has them, and at least the greatest peak or pass of a province.
An inn or a fort by a named pass or crossing takes its name ("Verulas Pass" for the inn, "Fort Verulas"). Names are
🏷 markers: pick one to change its name. **Make places** gives each its cell's name (on the map and as you walk
in); a cell with a name already keeps it.

### People and beasts

**🧍 People and beasts** (under the Places buttons) brings the marked cells to life as the game's land outside its
towns is, once the places are built:

- **Travellers** by the roads, as many as the game has (about six for every hundred cells): guards, traders,
  merchants, pilgrims and commoners, and barbarians and rogues too, alone or two or three of a kind together, just
  off the road.
- **Campers** at the camps you've built, two or three of one kind: outlaws, hunters, or Ashlanders on Dunmer land.
- **Creatures** over the land and in the water, about four a cell as the game has them, fewer near the towns, more on
  low ground and by the shore: the creatures and creature lists of the region's own wilds, or of the region nearest
  in weather. Swimmers go only in water deep enough.

Each person is made the way Populate makes one, in the region's own people (their race, faction, clothes and gear).
It's one Undo; each press adds more, so press it once.

### Rumours and quests

**📜 Rumours and quests** (under the Places buttons) gets your towns talking about the dungeons you've built near
them, as the game's towns talk of theirs. Press it once the towns (with their people) and the places are built:

- **A topic for each dungeon**, its name, with a line for the people of each of the two nearest of your towns within
  40,000: where it lies from the town ("a short walk north-east of Ida Vathi, under Mount Dreycrom") and who is there
  (bandits, smugglers, a necromancer, cultists, the dead, Daedra, Dwemer machines, beasts), read from what is inside.
- **A rumour** in "latest rumors" in the nearest town that teaches the topic.
- **A quest** where a band of people holds the dungeon, from the town's publican (else a guard), up to two a town:
  ask about the place, deal with the band's leader, go back for the gold. It's on the Quest Board like any quest, to
  change or add to.

It's one Undo.

### Yardstick

**📏 Measure** (Land panel, under Places) reads the marked cells as they stand now and sets each layer beside the
hand-made region they take after (the Region pass's **Like**, else the hand-made region nearest in roughness), read
from up to 160 of that region's own cells, none of them a town's:

- **The ground:** roughness close up, 512 apart and 2,048 apart (hills and hollows), and the share of ground over 30°
  and over 45°.
- **What stands on it:** trees, plants and rocks a cell, and the share of the ground in a road texture.
- **Who and what is there**, the towns' cells left out: places a cell (doors within 1,024 of each other count as one),
  small things, people and creatures.

Each layer gets a bar: green when the two figures are within a fifth of each other, red when one is twice the other
or more. The number at the top is their mean, out of 100. Hand-made land measured against its own region scores about
90; Tamriel.esm's coarse land about 40.

**Cells to look at** names the five cells furthest from the region's typical cell, none of them next to each other,
each with what is most off there (fewer plants, smoother, no rocks). **Look** opens the cell in 3D.

### What the towns live by

Each proposed town and village gets a livelihood from its land, at the game's own rates (its towns read for docks,
boats and nets, fields, crops and beasts, mine doors and who lives there): with the sea within a cell's eighth, seven
in ten live by the sea; a little further, half; inland, farming comes first, then mines and trade. A town only gets what
its site allows; the note under Suggest says what they live by.

- **By the sea:** a ⚓ Harbour marker on its shore: one of the game's own docks, its piers, boats and nets as they
  stand, laid where the shore falls to the water as it does under them, the size of the town.
- **By farming:** fields beside it on its flattest ground (one for a village, three for a city), laid as the Farm
  tool lays them, clearing the trees on them.
- **By a mine:** a mine on the steepest hillside near it, a 🕳 marker like the dungeons; an egg mine on Dunmer land.
- **By trade:** nothing more round it.

### Roads

Suggest brings its roads with it. **🛤 Suggest roads only** (Places ⚙) joins the towns again after you move, add or remove
some (drawn, proposed, and the game's own near the marked cells) as road networks join them: each pair with no third town nearer both, so roads go round a town instead of cutting through it. Each road
finds its way as the game's do: gently up the slopes (half its length under about 4°), round steep ground by zigzags,
never through water or a building, from the edge of one town to the edge of the next.

- The roads are 🛤 Road layers, to move, reshape or remove; you can draw your own too. Proposing again replaces the
  proposed ones and keeps the ones you drew.
- **Shape the ground** lays the roads in the marked cells: the ground under each made level across it and eased along
  it, never under a building, and painted with the road texture of the culture's nearest towns. Things standing on the
  ground follow it, and rocks, trees and plants keep off the road. Each press lays them again on the land it makes.
- **Bridges:** where going round the water would be much longer, a road crosses a river or a strait up to about
  two kilometres wide on a bridge, as the game's do: its deck level with the banks and high enough over the water,
  in the culture's own style (Hlaalu arches on Dunmer land, the Imperial highway's in Skyrim and the Reach, Anvil's
  on the Gold Coast, the Imperial stone bridge in Imperial towns), with piers under the long ones. The ground is
  raised to the deck under each end of the bridge, and the road climbs to it, gently and over a longer way where the
  deck stands high. A river running through a town gets no road bridge: the town's streets are its own. The
  bridges are drawn on the map, solid and wider than the road.

## Step 4: Make, then keep

**Make land** writes the features and the automatic shaping into the marked cells as one Undo step; things standing
on the ground follow it. While it works the button shows the step it's on. **◐** beside Mark shows the land as it was
before, for as long as you hold it. Then **✓ Keep**, **↻ Try again** or **✕ Drop** (see above).

## Height maps

- **Save marked as a height map**: the marked cells as a 16-bit greyscale PNG, a pixel a point of the land.
- **Bring in a height map…**: a PNG back onto the land. A map the Workshop saved comes back where it was, at
  the same heights. Otherwise, say where it goes and the heights of black and white.

## Recipes

### An island in the open sea

1. Mark the sea cells it will cover, and a cell more on each side for its shore.
2. Draw a **Coast** round it. Add a **Ridge** along its spine, and a **Spring** or two.
3. Turn on **Valleys** and **Rock layers**, then **Shape them**.

### A river valley through existing land

1. Draw the **River** (it marks its own cells).
2. Add a **Valley** along the same line for a broad trough round the river.
3. **Shape them**. The banks fade back into the game's land at the edge of the marked cells.

### Cliffs and mesas

Draw **Plateaus** with a short Cliff, or a Ridge, and turn on **Rock layers** with a Layer height of 512 or
more and some **Tilt**.

## Dressing land: rocks, trees and plants

**🪨 Dress…** (Land panel) dresses the marked cells' land as it is now, the way the game dresses its region's:

- **Rocks & cliffs:** as thickly as the game sets them on ground that steep, at the foot, on the face and at the
  crest, each turned to its own slope as the game turned that rock, so faces look out over the drop and crests hang
  over it. Steep faces are then covered as much as the region covers its own: most of a West Gash cliff hides
  behind rock, a coast's stays bare.
- **Steep faces:** on by default with Rocks & cliffs. The steep ground is clad first the way the game's gorges are
  (big faces, rocks on the lip and at the foot, banks, outcrops on knolls, no bottom edge showing: see *Rock the
  steep ground* under Dressing); the plain scatter then takes the gentle ground.
- **Trees & plants:** trees, plants, grass and logs from the region's own land. Its wild land is cut into squares
  (1024 across), each kept whole with what grows on it, and yours is filled with squares of the same kind of ground
  (as steep, as high, by the water or not), grown on the same texture where the region has them: grass tufts on the
  grass, bare scree on the rock. Groves, lone trees and undergrowth come out as the game lays them. Texture the land
  first, then Dress.
- **Like:** *The land nearest* (each cell's own region; for open sea, the nearest region with land), or one region's
  look for all. Where a region has no ground like yours, the nearest regions with land fill in.
- **Grow:** *The region's own*, or one of your **★ scatter brushes**: its things, as often and at the sizes the brush
  sets, in clusters at the brush's own spacing.
- **Amount:** 1 is the game's own thickness (or the brush's spacing).
- **Only part of the land:** draw a **▢ Dress area** with the shapes (it changes no ground), then Dress… and pick it
  under **Where**: only the land inside is dressed. No cells need marking for it. A region for each part: mark or draw it, Dress with that region, then the next.
- Not where something stands already, and not under water. One Undo takes it all back.

**🪨 Cliff** (a shape in the Land panel) makes a coast or a drop the way the game's are, without picking pieces one by one:
click along the edge, double-click to finish, then **🪨 Lay the cliff**. The rocks the region makes its cliffs of are
chained along the line, each in a pose the game set such a rock in, facing the lower side (or the water); boulders
lie at the foot and pieces on the crest. **Height** scales them within the sizes the game uses; **Drops** says which
side falls away when the lower side isn't the one you mean; **Like** borrows another region's rocks; with rocks
selected, **Use the selected rocks** chains those instead; **Raise the land behind it** lifts the ground to the
face's top; **Rock the slopes beside it** (on by default) clads the steep ground within about 1,000 of the line as
*Rock the steep ground* does, leaning its pieces on the chain. One Undo; lay it again for another arrangement.

To place rocks, cliffs, trees and plants by hand, open the **🎨 Style palette** and pick a region under **Regions**.

## Towns

Draw a **🏘 Town** shape round the ground it should take. The map shows its streets, plots and buildings.

- **Like:** whose towns it is planned after (streets, spacing, shops and taverns). The Imperial looks are kept apart:
  **Imperial** (the classic white towns and forts), **Anvil** and **Gold Coast**. **🎲 Another** gives another layout.
- **Look:** which of the culture's building families the town is built of, each named for the game town it is known
  by (a Hlaalu town of Balmora's houses, or of Narsis's). Shown when the culture has more than one. Blank: as the
  game mixes them.
- **Wall:** none, its culture's own, or one you pick. The wall is made of the game's pieces, each joined to the
  next as the game joins them, buttresses outwards, a tower at each corner, and gates where the streets go out, or
  where you put them with **⛩ Gate** (below).
  The wall stands on the outline you draw: each side you draw is one straight run of wall, its corner at your corner,
  and the town fills it. With the Imperial wall a side runs at whatever angle you drew it, and a round tower stands
  over every corner to close the joint, so a five-sided town, a slanted side or a town beside a castle that stands at
  another angle all come out as drawn; the town's wall ends at the castle's corners. A drawing that is square already
  keeps the wall's own square corner pieces. A corner sharper than about 65 degrees is cut off across, and a round
  shape of many short sides is given fewer, longer ones, so a gate fits. The other wall kinds have no round tower: with
  them a slanting side still becomes one to three big steps.
  Each side stands level, as the game's walls do: the ground under it is evened out a little first (fading back into
  the land round it), and the wall sunk deep enough that no foot shows; inside, the town's ground is brought level
  with the wall's foot for a way in, not left as a bank under the wall with the houses dug in below it. Where it must change height, Hlaalu and
  Velothi walls climb on their own step pieces; Imperial walls climb a stair for one step, stair, wall, stair for two or three, and a tower for more. Gates stand on the low side, where
  the town's streets go out, and the streets run on through them, never out onto the sea or over a cliff. Stairs inside lead up to the wall walk.
  The wall goes round at one level: where the ground lies lower it is brought up to the wall's foot, and the wall
  steps up only where a hill stands too high to cut. Castle walls the same.
  **Open to the water** leaves out the wall where it faces the sea or a lake, for a coastal town walled on its land side only.
  A Nord village gets a **palisade**: post sections following the land round it, with a gatehouse on the way in.
- **Dressed:** sets out what the culture's own towns set out. Before doors: benches, signs, lanterns, crates, a
  smith's forge and anvil. Along the streets: carts, stools, barrels. In the square: a well or a shrine. And the
  culture's own scenes, such as Telvanni slave pods or a gallows, as often as its towns have them. Its trade too:
  market stalls (the square first), crates and barrels stacked by side and back walls, shop signs and awnings,
  each as often a building as the culture's towns have them.
- **Density:** how many buildings, against the culture's own towns of that size (1). Raise it for a city on a big
  outline (the game's towns gather round their middle and leave open ground); lower it for a hamlet. A walled town
  fills its wall at 1 and over.
- **Streets:** as its towns' (wide), **narrower**, or **lanes**, one ground square (512) across.
- **Trade:** fishing, farming, mining or trading, as the game's towns that live by it, or **any** for the culture's
  own mix. A proposed town comes with the one its land gave it.
  - **Fishing:** fishers, sailors and dockworkers are a fifth of the townsfolk in the streets, and about one in twelve
    of the people in its houses. Some yards have a net on its frame and fish hung to dry.
  - **Farming:** farmers, herders and hunters are a third of the townsfolk and a quarter of the people in its houses.
    More yards are pens, and there are fewer shops, guard posts and guild halls.
  - **Mining:** about one townsperson in eight is a miner, and a few live in its houses. There are more shops, taverns
    and guild halls.
  - **Trading:** more shops and fewer taverns.
  - Its stalls and storage carry the trade's goods twice as often: fish and nets, crops, eggs and hay, or ore, picks
    and carts. Other trades' people turn up seldom: a fisher in a mining town is rare, as in the game.
- **On a hillside** (ground rising 400 or more across the outline) the streets run in **level bands** along the slope,
  a row of houses apart up it, the main street the middle band; the bands are joined by **ramps** found at a walkable
  grade, or by a straight **stair street** where a ramp would have to wander; each band's rows are a district of their
  own. Where the ground is a bowl or a crest of short contours and bands would halve the town, the plain plan stands.
- **The ground:** each street is one level plane across and runs smoothly along; each plot is levelled to its door;
  the ground from a door's front to its street is graded even. A door on a hillside whose straight way down would be
  steeper than a quarter rise a unit gets a **footpath** instead: a tread cut into the hill along the slope (never
  built up), level across and no steeper than a third, with a level landing at the door and a bank on the uphill side,
  the way you would shape one with Flatten. The few doors that get neither stand too far above or below any street.
- **Rocks on the hill:** a town on steep ground gets the rocks its culture's own towns stand, at their rate a building
  (a Mournhold town many, a Common one few, and fewer still where the land round the town is bare): behind the houses
  on their terraces' cut banks, under the downhill edge of a floor standing over the land so it rests on a rock top,
  along the footpaths' banks and the wall's, at the towers' feet, and a crown of big rocks packed into one mass where
  the town stands on a knoll. Each rock is sunk until the bottom edge of its mesh lies under the ground all round, as
  the game's are; one that would still show is left out. Never on a street, a plot, a tread or in a door's way.
- **Banks shored up:** steep ground the town leaves bare, the sides of a raised street first, is shored up with
  rocks laid along the bank and packed close, until about as much of it is covered as in the game's hill towns
  (nine tenths).
- **Open ground:** a pocket of level ground left between the houses gets a small fenced kitchen garden, and the
  open ground by the streets gets a few of the region's trees.
- **Draw 〰 Street / ▧ Zone / 🧱 Wall / ⛩ Gate:** shapes of the town's own, drawn inside it.
  - **Streets** you draw are its streets, in place of the ones it would plan.
  - A **zone** is a quarter: **Houses** keeps shops, taverns and halls out; **Business** draws shops, taverns and
    guild halls, every other house a shop; **Noble** draws manors and temples, its houses manors.
  - A **wall** you draw keeps to a grid of the wall's pieces from your first point, its corners square; the town fills it.
  - A **gate**: click on the wall where a way in goes, once for each gate. A walled town with gates of yours opens
    only at them, each where you put it (to the wall's piece step), with a street running in from the town's middle;
    drag one to move it, ✕ to take it away. One put on a short jog of the wall, too short to hold a gate, goes to
    the nearest side that can, clear of the corners. With none drawn, the gates are where the streets go out.
- **How many:** shops, taverns, temples, guild halls, manors and guard posts. Blank is as its towns have them.
- **Which buildings:** the game's buildings it picks from, with how often each is used. Untick one to leave it out.
- **Like ★ your style:** a style of your own (Style palette) builds the town of your prefabs, planned like the
  culture it names.
- **Name:** the town's name. Its interiors are called after it ("Varnhold, …"). Left blank, it takes the name shown,
  made from the culture's own town names.
- **Inside:** what goes behind every door. **Furnished:** an interior of the Workshop's own, planned from the
  building's footprint in its style (rooms, stairs and storeys that fit it, every door linked both ways; no game
  interior is copied), furnished by the Workshop room by room. **Empty shells:** the same rooms and doors, empty but
  lit, for you to furnish. **None:** outsides only. A home is named after the person who heads it ("Nala Niabhe's
  Lodge"), a shop after its keeper and trade ("Gilas Mundrethi: Clothier"); temples, guilds and towers keep what
  they are.
- **Yards:** the ground behind each house is its yard, fenced in the culture's own fence (Imperial rails, Nord and
  Breton farm fences, Dunmer wooden fences), with one kind of life in it: a kitchen yard (barrels, sacks, a chicken
  cage), a garden (a kitchen garden: rows of the region's own crop at the spacing the game's farms use), a workshop
  yard behind a shop (crates, a wheelbarrow), or a pen (hay and a trough).
- **What grows round the houses** is learnt from the game's towns, culture by culture, with the region's own
  species: a bed of two to six flowers or herbs of one kind at a side wall (the mushroom beds of a Telvanni town, the
  lilies and goldenrod of an Imperial one), a tree by the house where its towns have them, a planter at the door or
  along a wall with the game's own garden in it (a tenth of them by the door, as in the game; none in the cultures
  that stand none), and ivy on the walls where the culture grows it (two or three a house on the Gold Coast, none in
  Dunmer towns). Each at the game's rate a building. Nothing grows in a door's way, on the arrival spot in front of
  it, on a street or in a plot.
- **🌾 Farm and 🍐 Orchard** are shapes of their own on the Land panel, for fields away from a town: draw the outline
  (its longest side is the gate side) and **Make it**. A farm is fields of the region's own crop at the spacing of the
  game's farms, tiled over the outline with paths between, the culture's farm fence round them and the gate's way
  left open; an orchard is a loose grid of the region's fruit tree at the game's spacing (the nearest region's that
  grows one; fruit trees only, so none in a load order without them). **Like** picks whose crops and fence (blank:
  your own town beside it, else the nearest game town's), the seed lays the same outline another way. One Undo takes
  it back.
- **People:** outdoors, guards of the culture's own at the gates, the great doors and on the streets, sellers at their
  stalls (they barter; their wares and stock are theirs), and townsfolk about the streets and doors, as many a
  building as its towns have. With Furnished, a household in each too, owning its beds and chests. This takes a minute
  or two for a town.
- **The wall's keep and towers** (with Furnished or Empty shells): each has a door at the ground on the town side and an arched
  door on the wall walk where the wall runs into it, set only where the way out of it is clear. Behind them is a
  spiral-stair room joining the two, so you can climb from the street to the walk inside. The towers' rooms share one
  place ("Varnhold, Wall Towers"), each joined to the next round the wall, and the keep's room to the towers beside it.
  They are furnished by the Workshop, never with the original room's things.
- **🏘 Make it** builds it (the button at the top of the panel builds every town drawn). Each building is set on the ground, and the ground is raised where its foot or door
  would show a gap. The streets are paved with the road of the nearest towns of that culture. One Undo takes it all back.
- **Editing it afterwards:** right-click any piece of one of its buildings → **▣ Select the whole building**, then move
  or turn it as one. When a door moves, alone or with its building, the way out of its interior moves with it.
- **✕ Remove the town** takes away what Make it built there (buildings, wall, dressing, interiors and their people),
  even under later work; what you added since and the ground stay. Then Make it again.

## Keeps and castles

Draw a **🏰 Castle** shape round where it should stand. The map shows its walls, towers, gate, keep and doors before
anything is built.

- **Like:** whose forts it is built like.
  - **Imperial fort:** a curtain wall, closed all round, with its gate on the side the land falls away to. The gate
    is a Legion gatehouse: the wall arch, the gate passage with its door, and a guard tower either side. The corners
    are the wall's own corner pieces (a large fort has round towers at its back corners), the yard inside is one level.
    The keep stands square in the wall line at the back, rising over the wall, its door facing the gate; where the
    wall walk runs into a keep with an upper room, an arched door on the walk leads in. The game's forts stand
    halls in their walls besides the keep (Frostmoth's armoury, barracks and chapel; a prison), and a made fort
    stands them at the same rate to its ground: a medium fort one, beside the keep as its wing where the back wall
    is long enough, else in a side wall.
  - **Dunmer stronghold:** the old Chimer keep on its stepped platform, with its ways in to the upper and lower
    levels, the dome and the propylon chamber. **Small** is a keep without the platform.
  - **Redoran stronghold:** a house stronghold of manor, tower, services and a house, inside a Redoran wall and gate.
- **Rooms: Made anew** builds the keep's insides the Workshop's own way instead of copying a game keep's rooms: a set
  of linked interiors the way the game's big keeps are laid out (a great hall, chambers, a garrison, a prison, a tower
  or two, an undercroft under them; a large keep adds a household, a library, a chapel and a treasure chamber), in
  chains with a ring or two, every door paired both ways. The keep's ground door leads into the lowest of them, the
  arches where the walk runs in to those above, a roof door to a tower's hatch. Each run of wall towers is one
  interior of passages and spiral stairs with a door out at every arch on the walk and a hatch at each crown. The
  layouts turn as the game's do (corners as often as straights, junctions, ring corridors, stairs over several floor
  heights, big halls for a great hall or library, spiral towers with a room at each landing) and are dressed, lit and
  peopled by the Workshop; nothing inside is copied from a game interior.
- **The yard has jobs:** a smithy along the gate's wall (forge, anvil, bellows, grindstone), stables on the longest
  free wall (hay, a trough), stores on the next (crates, barrels, a wheelbarrow), a shrine by the keep, a drill ring
  with dummies and targets to one side of the way in, and a brazier in each corner — then the game's own bailey
  things in what is left.
- **Size:** small, medium or large, against the game's own forts of that kind. **As drawn** builds the outline you
  drew, any shape with square corners: an L, a T, a stepped side, a slanting side made a step. It is squared to the
  wall's pieces, so a short jog is merged away; its gate on the longest side facing the way in, its keep in the
  longest side at the back. A big outline is split into **wards** by cross walls, each with its gate and a round
  tower where it meets the side walls (two wards from about six lengths of yard before the keep's, three from
  sixteen): the keep's ward at the back holds the keep's **court**, a walled yard of its own with the keep in its
  back wall, its wings beside it, halls in its side walls and round towers at its corners; the lower wards are
  built as **quarters** of the castle's town, streets and houses of the fort's culture planned round the walls,
  towers and halls once they stand, with their own interiors and people. **Great** is a castle a cell across built
  the same way, square to where you drew. A large fort has a second hall beside the keep (a chapel or an armoury).
  A castle with wards or a court stands tall, as the game's great keeps do: its round towers rise storeys over the
  walk (the court's highest, then the junctions and corners). Its **keep is one mass** of the kit's keep pieces grown as the game's
  great keeps are composed: every join between keep pieces in the game's own keeps was read (a pyramid-roofed keep
  beside another so their roofs run into one, one keep on another, a keep beside a roofed one), and the castle's
  keep grows from its own doored block by those joins, each piece resting on the ground or on one under it, flush
  at the back wall. Round towers stand at the roofed keeps' corners and rise out of the top keep's deck; the keep's
  windows follow the game keeps' patterns; doors open from the upper walls onto the decks they meet. No two keeps are
  alike, and the mass stands for the castle's halls too: nothing else is built into the keep's ward's walls. A
  large fort's keep is a smaller mass. Its rooms are **made anew to its size** (Rooms: Furnished or Made anew), several storeys and halls
  linked door to door, the deck doors leading in above the ground door; Empty shells keeps the game keep's own.
- **Gate:** **By itself**, the gate goes on the low side that's dry land, never out onto the sea or over a cliff.
  Or pick **North**, **East**, **South** or **West**, or click an arrow inside a side of the castle on the map. The keep's
  door turns to face it. **🎲 Another** keeps it.
- **Name:** its rooms are called after it ("Fort Estmoth, Keep"). Left blank, it takes the name shown.
- **Rooms:** **None**; **Empty shells** (walls, stairs and doors only, for you to furnish); or **Furnished** (the same
  shells, furnished by the Workshop, each room as what it is: barracks, armoury, shrine, hall).
- **People:** cast as the game's own rooms of each kind have them (furnished rooms only).
- **🎲 Another** gives another keep and layout.

**Its rooms.** Behind every door is a room built like the one the game put there (the keep's halls, its prison, its
upper storey, a stronghold's levels), with its walls, stairs and doors but never the original's furniture or decor.
The doors between those rooms lead to each other as the game's did.
An Imperial fort's towers share one "Towers" place, as the game's forts keep theirs: a spiral-stair room for each
tower. Each room's doors lead out onto the wall walk on both sides and up to the roof. Its other doors join the next
tower and the keep, so you can walk from the keep into the towers without going outside.

**Doors face the world.** Each outside door sets you down just inside, in front of the door that leads back. Going
out, you stand a step outside it, facing away.

**Inside the wall** an Imperial fort has stairs up to the walk and a bailey set out the way the game's forts keep
theirs: stores of crates and barrels, training dummies, a cart, a well, benches, a smith's anvil. Each group stands in
the castle's own places, against a wall or in the yard, clear of the way from the gate to the keep.

**Beside a town.** Drawn beside a walled town or in its edge, the castle stands in the town's wall: the two are built
as one ring, the castle first, and its gate turns towards the town. They need not be lined up: the town's wall is
brought to the castle's corners and closed on it, and the map shows the wall as it will be built. If you drop or move
the castle later, make the town again to close its wall.

**🏰 Make it** evens the ground under the wall and the keep, clears trees and rocks inside, and builds it all.
One Undo takes it back. **✕ Remove** takes away what it built, rooms included; the ground stays.

## Good to know

- **The game shows changes to the ground after a restart.**
- If another plugin that loads after your mod has its own ground for a cell, it wins in the game. The Place
  panel warns you. **Play here** always loads your mod last.
- The game has one water level (0). Rivers and lakes are dug down to it.
- Large plans take a while at **Shape them**: about 10 seconds for 16 cells with every pass on.
- Some mods add sea floor without cells. Land shaped there gets its cell, in the land's region, when you first put
  something on it, paint its region or name it.
- **Naming a cell:** **name** beside an outdoor cell's place in the Place panel. The game shows it on the world map,
  as the map window's title while you're in the cell, and as your save's place. Leave it empty for no name, as most of the game's outdoor cells have.
