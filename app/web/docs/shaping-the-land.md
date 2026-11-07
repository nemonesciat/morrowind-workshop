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

Land shaping changes many cells at once from a **plan**: shapes you draw on the map (a coast, a ridge, a
river…), with settings for how natural it looks. It is on the World map's **Land** panel, on the flat map
(not in 3D).

It always goes in four steps:

1. **Draw shapes**. Each marks the cells it reaches as you draw, move or widen it (towns left out).
2. **Mark more cells** if you like: land with no shape on it is smoothed into the rest.
3. **Watch the preview** on the map, and change the sliders until it looks right.
4. **Press the button pinned at the top of the panel** to write it into your mod. It does everything you drew, in
   order: **Shape the ground**, **Build the town**, or **Shape, then build** when there are both.

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

A big plan (a long coast over a hundred cells) can take a minute or more to preview: the map counts the seconds,
and the top bar shows **⏳ Previewing the land**. Everything else goes on meanwhile. **✕** on it stops the preview;
it runs again when you change a shape.

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
| Shores | As the region lays them (West Gash's shores are rock, Nedothril's half sand), or **sandy** beaches or **rocky** shores whatever the region: at the water's edge and on the flat ground just over it, in the region's own sand or rock texture where it has one. Also in Texture only. |
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

The button pinned at the top of the panel (**Shape the ground**, or **Shape, then build** with towns drawn too; and
**Shape the marked cells** at the bottom) writes the plan into the marked cells, as one Undo step, then builds each
town drawn. You don't need to select a town first. Town, street, zone and wall shapes change no ground. Things standing on the ground follow it, and the note after it compares the new land's
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
  over it. Steep faces are then covered as much as the region covers its own: most of a West Gash cliff hides
  behind rock, a coast's stays bare.
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
face's top. One Undo; lay it again for another arrangement.

To place rocks, cliffs, trees and plants by hand, open the **🎨 Style palette** and pick a region under **Regions**.

## Towns

Draw a **🏘 Town** shape round the ground it should take. The map shows its streets, plots and buildings.

- **Like:** whose towns it is planned after (streets, spacing, shops and taverns). The Imperial looks are kept apart:
  **Imperial** (the classic white towns and forts), **Anvil** and **Gold Coast**. **🎲 Another** gives another layout.
- **Wall:** none, its culture's own, or one you pick. The wall is made of the game's pieces, each joined to the
  next as the game joins them, buttresses outwards, a tower at each corner, and gates where the streets go out.
  Each side stands level, as the game's walls do: the ground under it is evened out a little first (fading back into
  the land round it), and the wall sunk deep enough that no foot shows. Where it must change height, Hlaalu and
  Velothi walls climb on their own step pieces; Imperial walls step at a tower. Gates stand on the low side, where
  the town's streets go out, and the streets run on through them, never out onto the sea or over a cliff. Stairs inside lead up to the wall walk.
  The wall goes round at one level: where the ground lies lower it is brought up to the wall's foot, and the wall
  steps up only where a hill stands too high to cut. Castle walls the same.
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
- **Draw 〰 Street / ▧ Zone / 🧱 Wall:** shapes of the town's own, drawn inside it.
  - **Streets** you draw are its streets, in place of the ones it would plan.
  - A **zone** is a quarter: **Houses** keeps shops, taverns and halls out; **Business** draws shops, taverns and
    guild halls, every other house a shop; **Noble** draws manors and temples, its houses manors.
  - A **wall** you draw keeps to a grid of the wall's pieces from your first point, its corners square; the town fills it.
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
  left open; an orchard is a loose grid of the region's fruit tree at the game's spacing. **Like** picks whose fence
  and orchards (blank: the nearest game town's), the seed lays the same outline another way. One Undo takes it back.
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

**Beside a town.** Drawn against a walled town, the castle's gate turns towards the town, and where the two walls
meet only one is built: the wall already standing serves both. A town walled round a castle does the same.

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
