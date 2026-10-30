# Shaping the land

*How to change the ground outdoors: by hand with the Ground brush, or many cells at once with land shaping.*

## Which tool to use

| You want to… | Use |
|---|---|
| Nudge a hill, dig a hollow, level a spot for a house, paint a path | **The Ground brush** (in 3D) |
| Scatter grass, plants, rocks or trees | **The Ground brush**, Scatter |
| Rocks and cliffs over land that's there (an island you raised, ground you sculpted) | **🪨 Dress…** (the Land panel, on the marked cells) |
| Make an island, a mountain range, a river valley or cliffs over many cells | **Land shaping** (the Land panel) |
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
| 🖌 Paint | Paints a ground texture. Pick one from the list, or take the one on the ground: **💧 Pick**, then click it (or **Shift+click** it any time). **✨ Auto** paints each patch with the texture the region's land has at its slope, height and shore instead (roads and paving stay). |
| 🎨 Tint | Paints the ground's own colour (the shading the game multiplies into its textures). **Ctrl** paints back to plain; **💧 Pick** (or **Shift+click**) takes the colour there. |
| 🌿 Scatter | Scatters the region's own grass, plants, rocks or trees. **Ctrl** clears them away. |

- **Size** is the brush's reach in game units (a cell is 8,192 across; the land has a point every 128, so 64 moves
  just the one under the brush). Type a size in the box, or press **[** and **]**. **Strength** is how much each pass
  changes (not used by Scatter).
- **Objects follow the ground**: things standing on it (rocks, plants, people, crates) move up and down with
  it. Buildings move too, so turn it off when you are fitting the ground to a building.
- Each stroke is saved when you let go, as one Undo step.
- The brush can't make a step steeper than the game's land can hold (about 83°).

### Tint: shade automatically

Under Tint, three buttons shade the cell under the camera (or it and the eight around it) the way the
game shades its own land nearby: **Where textures meet** darkens the joins, **By texture** gives each texture
its usual tint, and **Hollows** darkens the hollows and lightens the crests. **Amount** sets how strongly.

### Scatter

- Pick a set (Grass, Flowers & plants, Rocks & stones, Trees, Logs & stumps). They are learnt from the region
  you're in, the commonest first; untick any you don't want. **＋ New brush** makes a set of your own, with
  any objects, from mods too.
- **Thickness**: 5 is as thick as the game has that kind; 10 is about three times as thick, 1 under half.
- One stroke makes at most 1,500 things (15,000 grass tufts). Let go and paint again for more.
- **Grass as groundcover** goes into its own grass file next to your mod. OpenMW draws it fast, sways it,
  and lets you walk through it. **Grow it over this cell** (or **…and around**) grows it on the grassy
  ground of whole cells.

## Land shaping: how it works

Land shaping changes many cells at once from a **plan**: shapes you draw on the map (a coast, a ridge, a
river…), with settings for how natural it looks. It is on the World map's **Land** panel, on the flat map
(not in 3D).

It always goes in four steps:

1. **Draw shapes**. Each marks the cells it reaches as you draw, move or widen it (towns left out).
2. **Mark more cells** if you like: land with no shape on it is smoothed into the rest.
3. **Watch the preview** on the map, and change the sliders until it looks right.
4. **Press Shape them** (pinned at the top of the panel) to write it into your mod.

**Only marked cells ever change.** Everything else, including the edge a marked cell shares with an
unmarked one, stays exactly as it is. Marking is how you say both "work here" and "leave the rest alone".

## Step 1: mark the cells

Tick **Show the land map** to see what each cell is:

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

Press **⛰ Mark cells…**, then drag over cells to mark them. **Ctrl**+drag unmarks. Settled cells are left out
unless you hold **Shift**, so a town isn't reshaped by accident. **Done** (or Esc) stops marking.
**Clear marks** unmarks them all. Your shapes stay.

**↶ Undo my land** puts the land in the marked cells back as it was before your mod: heights, ground textures and
grass, in one step. Your objects stay, and Undo brings your land back. (In **My mod**, you can also pick ground
rows and undo just those.)

Cells with no land at all (the open sea) get a sea bed when you shape them. **Raise the marked cells into
land** is a quick way to make plain land there without drawing shapes (Height, Coast width, Roughness).

**Shapes mark their own cells:** drawing a shape, moving its points or widening it marks every cell it reaches,
except towns. A shape that reaches a town says so; **Shift**+click **⛰ Mark its cells** to shape the town too. Marks
are never taken away by themselves: a moved shape's old cells stay marked, so its old land goes when you shape
again. Dress areas mark nothing.

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
  the plan's own; the Undo at the top undoes changes to your mod, such as Shape them.
- **Order matters**: each shape acts on what the ones above it made (↑ ↓ to reorder). Rivers, lakes and
  springs always go last, so they cut through what the others raised.
- **Only in** (on a shape) limits it to one region of the marked cells, fading out at the border. **Like**
  gives its ground another region's character, for example a ridge as craggy as the Druadach Highlands, while
  the textures stay the cell's own.

## Step 3: the preview and the settings

The map shows the plan's land over the marked cells, about half a second after you stop sliding. **Nothing
in your mod changes until you press Shape them.** You don't have to touch any setting below: each starts at
the region's own figures.

### Protection

**Start from the land under my mod** (on by default): each Shape starts from the marked cells' land as it is
without your mod (the game's land, or the sea bed), so a moved or removed shape leaves nothing behind. Off, it
starts from your land as it is now, keeping what you sculpted there by hand (shapes you took out then stay in it).

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
| Terraces | Steps up the slopes (the Ashlands look). |

### Dressing

| Setting | What it does |
|---|---|
| Like | The region whose land the plan takes after: textures, tints, roughness and slopes. Default: each cell's own. |
| Put the cells in this region | Its weather, sounds and creatures go with the land. |
| Textures | How many textures a cell: as many as the region's cells have, or fewer or more. |
| Tint, seams, hollows, Shading | The region's own colouring, laid on as the game does. |
| Rocks | The region's rocks on the new slopes and cliffs, as thickly as the game sets them on such ground, at the foot, on the face and at the crest, turned to the slope as the game turns them. |
| Stream beds | Where much water runs, the region's water's-edge textures (mud, wet ground), so streams show. Off by default: the Bitter Coast's own land does this, most regions' don't. Also in Texture only. |

### Texture only

**🎨 Texture only** textures the marked cells without reshaping them: each 512-unit patch gets the texture the
region's own land has at that slope, height and distance from the water, with the region's tints and shading.
Each cell gets about as many textures as the region's own land cells have, in patches as broken up as theirs,
so no single texture covers the land in big repeating blocks. Shape them and Raise texture new land the same way;
land textured before keeps its textures until you texture it again. It's
under Dressing when you have shapes, and in **Texture the land** when you don't.

- **Like** takes the textures of another region; **Textures** sets how many a cell.
- Heights never change, and no land is made. Roads, paths and paving keep their textures, and with **Keep the
  ground under buildings** (Protection) so does the ground under what's built.
- One Undo takes it back.

At the bottom: **Roughness**, **Edge fade** (how far in from the marked cells' edge the shapes fade in), **Only
in** (the whole plan in one region), **🎲 Re-roll** (the same shapes with other rolling ground and shores).

## Step 4: Shape them

**Shape them** (pinned at the top of the panel, and at the bottom) writes the plan into the marked cells, as
one Undo step. Things standing on the ground follow it, and the note after it compares the new land's
slopes and roughness with the region's own.

The shapes stay after shaping, so you can change them and shape again: with **Start from the land under my
mod** on, the land is made afresh from your shapes each time. While it works, the button shows the step it's on
and fills like a bar. **◐ Before** (under Show where water
runs) shows the land as it was before the last Shape them or Texture only for as long as you hold it.

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
  over it.
- **Trees & plants:** trees, plants, grass and logs from the region's own land. Its wild land is cut into squares
  (1024 across), each kept whole with what grows on it, and yours is filled with squares of the same kind of ground
  (as steep, as high, by the water or not). Groves, lone trees and undergrowth come out as the game lays them.
- **Like:** *The land nearest* (each cell's own region; for open sea, the nearest region with land), or one region's
  look for all. Where a region has no ground like yours, the nearest regions with land fill in.
- **Amount:** 1 is the game's own thickness.
- **Only part of a cell:** draw a **▢ Dress area** with the shapes (it changes no ground), then Dress… and pick it
  under **Where**: only the land inside is dressed. A region for each part: mark or draw it, Dress with that region, then the next.
- Not where something stands already, and not under water. One Undo takes it all back.

To place rocks, cliffs, trees and plants by hand, open the **🎨 Style palette** and pick a region under **Regions**.

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
