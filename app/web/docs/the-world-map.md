# The World map

*Opening places, moving about in 2D and 3D, placing, selecting and changing things.*

## Opening a place

- Type in **Go to a place…** at the top of the Place panel: a name (*Balmora*, *Seyda Neen, Arrille's
  Tradehouse*), a cell's coordinates (*-4, -14*), or a spot in game units (*x y* or *x y z*, as the game's console
  gives it).
- Or **Ctrl+K** and type the place; or **🗺 Open on map** on any cell in Browse; or the **Places** panel, which
  remembers where you've been.
- Select a door and press **Enter** to go through it; **Alt+←** comes back.

**Map** and **3D** at the top left switch between the flat map and the 3D view.

## Moving about

**On the flat map:** drag to pan, the wheel to zoom, the arrows at the bottom left to step a cell, **◎** to fit
the place. **+ −** at the bottom right zoom.

**In 3D:**

| Do | To |
|---|---|
| Right-drag | Look around |
| W A S D | Fly (Q / E down and up, Shift faster; tap twice and hold to sprint, Esc stops) |
| Wheel | Forward and back |
| Middle-drag | Slide |
| Alt+drag | Circle round the selection |
| F | Look at what's selected |

**?** in the 3D toolbar (or the **⌨ 3D controls** panel) lists every control. Used to Blender? **Ctrl+/** has
**3D controls: Blender**: middle-drag circles, Shift+middle-drag slides, Ctrl+middle-drag moves in and out, and **G**
and **R** move and turn what's selected with the mouse (**X**, **Y**, **Z** keep it to one axis; click sets it down,
Esc puts it back). Without that choice, give those two a key of your own there.

Used to the old editor? **3D controls: Classic editor** there: drag what's selected to slide it over the ground,
**Z** + drag to raise or lower it, right-drag it to turn it (**X** or **Y** + right-drag to tilt it). A drag on
something not selected yet picks it up; a click still selects and a right-click still opens the menu.

## Selecting

- **Click** a thing to select it. **Shift+click** adds or takes one away.
- **Shift+right-click** keeps what is selected and adds that thing; the menu's **Add all the … here to the selection**
  then adds every one of its kind.
- **Drag a box** on an empty spot to select many (in 3D; **Shift+drag** on the flat map).
- **Esc** deselects. **Right-click** anything for what you can do with it.
- **☆** beside an action in that menu (shown when the mouse is over it) keeps it in your **Favourites**, at the top
  of the menu wherever it applies. **Shift+F** opens only them, for what's selected; **☰ The whole menu** shows the
  rest.
- **H** hides what's selected (to get at what's behind), **Shift+H** everything else, **Alt+H** shows it all
  again. Hiding only changes what you see, not the game.
- **🔒 Lock walls** (a button on the bar, lit when on) stops you moving walls and buildings by accident; pick them
  in the Objects list instead, or click it to turn the lock off.

## Moving, turning and changing

**In 3D**, drag the arrows to move what's selected and the rings to turn it: **G** move, **R** turn, **⤡ Tilt** to
lean it, **⤢ Scale** (**3**) to size it: drag any handle and it grows or shrinks evenly, ×0.5 to ×2 (several
selected: the Scale dialog). **⊙ Pivot** sets what several selected things turn, tilt and size about: **Median
point** (the group's middle, so they keep their places to each other), **Individual origins** (each where it stands)
or **Active element** (the one clicked last). The Selected panel has the same choice for the flat map. **✛ World axes** (lit: the world's directions; plain: the thing's own) sets which way the
handles point. **End** (or **⤓ Drop down**) sets it on what's below, **Del** removes it. **Esc** or a right-click while you
are still dragging puts it back, and Undo gets no step for it.

**On the flat map**, drag it. Outdoors its height follows the ground.

**⊞ Snap ▾** sets the steps for moving and turning, **Snap to pieces** lines up walls and floors with nearby
pieces as you move them (several selected snap as one), and **Land on surfaces** rests things on what's below after a move.

**The Selected panel** has everything about the thing selected:

| Control | What it does |
|---|---|
| X, Y, Height, Turn, Tilt, Scale | Exact numbers; **Apply** sets them. |
| Duplicate, ⧉ Copy | A copy in place; or copy it (Ctrl+C) to paste anywhere (Ctrl+V), in any place. |
| Swap for… | A replacement: keeps the spot, the turn, and where a door leads. **Ctrl+H** replaces every one of an object with another. |
| ↻ Other pieces | For a building piece: other pieces of its style that fit the same spot. |
| 🎨 Retexture | A new object like this one, with your own pictures. |
| 🌿 Add to brush | Puts it on one of your own scatter brushes. |
| 🔊 Add a sound | A sound from your Library, playing over and over where this stands. |
| 💬 Dialogue, 👤 Edit character | For people and creatures. |
| Undo | For something your mod changed: back to how the game has it. |

Double-click a thing (or right-click › **🗂 Its card**) for its card, under the view or **⧉** in a window you can move,
size or dock. Its tabs depend on what it is: **📋 Details** (its record and where it stands, owner, lock, key, trap; Save
is one Undo), **🚪 Leads to** for a door, **📦 Contents** for a container, **⚡ Does** (when it's used, opened or read; a
trap; a secret way), **🎨 Look** (model, textures, sound, swap), **🪄 Dress** and **🧱 Build** where they apply, and
**📅 Day** for a creature. With the card open, selecting something else moves the card on to it.

**Doors** have **Leads to**: search a place to make the door lead there (tick **Make the door at the other end
lead back here**). The arrival spot is chosen for you, just in front of the door there on the side with floor. To
set it yourself:

- **Type it**: **Arrive X**, **Y**, **Height** and **Facing °** (0 north, 90 east), then **Set**. Kept exactly.
- **📍 Pick…** opens the place it leads to. Click the floor there, or press and drag the way the player should face
  (a figure with an arrow shows it; the faint one is the arrival now). A plain click faces away from the nearest
  door, into the room. You stand on the floor under the spot, a step off any wall. On the map, a place with
  several storeys takes the storey the **Floors** slider shows.
- **📷 Where the camera is** (while picking in 3D): exactly where the camera stands, facing the way it looks.
- **Click a door** while picking: the two doors lead to each other, each arriving in front of the other.
- **🧍 Where I stand** (the game linked): the door leads to where your character stands in game, facing their way.

Setting one door's arrival never changes the door at the other end once that one leads back.

With several selected: **⧉ Copy**, **Duplicate**, **⟳ 90°**, **Delete all**, and **Save as a prefab** to drop the
group anywhere later.

## Placing new things

- **Search anything to place** (Place panel): type, then drag the result into the view (it lands where you drop
  it) or click it and then click where it goes.
- **Recently used** and **Prefabs** sit under the search, then things **Suggested for this place**, learnt from
  places like it.
- **🎨 Style palette…** has building pieces, furniture and decor sorted by style (Hlaalu, Redoran, Telvanni, Nord,
  Imperial…), the way the game's own places use them.
- **✚ Create new…** makes a new place, person, container, item, note, spell or list in a window over the map.
  In 3D, right-click a spot: **Create here**.
- **🧲 Physics** lets loose things fall and be pushed about; keep the result or put them back.

## The panels

| Panel | What's in it |
|---|---|
| Place | Go to a place, Play here, Create, Style palette, Second window; indoors **Auto-furnish**, **Find gaps**, **Check place**; placing. |
| Selected | The thing selected (above). **📌 Pin** keeps one in its own panel, to compare or tweak several. |
| Objects | Every object in the place in sections by kind, A to Z, with a filter (a name, an ID, a kind, or *your mod*). Click a section's name to fold it away. Open more Objects lists, each with its own filter. |
| ☑ Show | A window, opened by **☑ Show** on the bar (tick it in **▤ Panels** to have it as a tab instead): what's shown (buildings, doors, containers, lights, people, creatures, items), your changes, hidden things; indoors, **Floors** hides everything above a height to see lower storeys. |
| Sky | Region, weather and time of day outdoors; an interior's lighting. See *Sky, regions and weather*. |
| Land | Land shaping and height maps. See *Shaping the land*. |
| Paths | The walking paths people and creatures follow. |
| 📋 Object list | Everything that can go into a place, one kind at a time (Static, Door, Light, NPC, Creature, Weapon…, or All): ID, name, how often the game uses it, its mod. Click a column to sort, **Mine** for your mod's own. Drag a row onto the map or the 3D view, or double-click it to place it; right-click for its record or a list of its own. Open several, one kind each. |
| Library, Prefabs, Places, Recent changes, Find gaps, Check this place, 3D controls | Open them from **▤ Panels**. |

**Layout: Lists** (in **▤ Panels**) puts the Object list on the left, the place's Objects below and Selected on the
right. The small tabs at the view's edges (◂ ▸ ▾) fold a side away and back. **⛶** beside **▤ Panels** gives the map
or 3D the whole window: only its buttons and the windows you open stay, floating over it; **⛶** again brings
everything back.

**✚ Place** in an Object list: a click on a row picks it up, a see-through copy follows the mouse in 3D, and each
click puts one down (Esc, or the row again, stops). The wheel turns it (Shift: fine), **X** or **Y** + wheel tilts
it, **Alt** + wheel sizes it, **Backspace** sets it straight; the next keeps the last turn, tilt and size. Tick
**Lean with the ground** to stand it on the slope, **Random turn** to turn each its own way.

To fine-tune what's selected: the **arrow keys** nudge it over the ground along the grid, the way you look,
**Page Up**/**Page Down** raise and lower it, **,** and **.** turn it by the snap angle; **Shift** goes further. A run
of nudges is one Undo. All of these keys can be changed under **Ctrl+/**.

## Your changes

- On the map, your mod's changes are marked: **green** new, **gold** changed, a **red ✕** where you took something
  out (right-click it to bring it back). Turn the marks on in **☑ Show**.
- **Show only what your mod changed** hides the rest.
- **My changes** lists them all, each with **Open on map** and **Undo**, in sections by kind (Containers, Statics…),
  A to Z, with a filter (a name, an ID, a kind, or *new*, *changed*, *removed*). Click a section's name to fold it away.
- A character's **Stands in** (Characters), and **🔎 Find on the map** on a character's or creature's record in Browse,
  open the place with them picked and the view on them.

## The 3D view

| Button | What it does |
|---|---|
| 💡 Game light | Lit: the game's own lighting. Off: bright, even light to work by. |
| 👁 View ▾ | **Top** and the four isometric corners (◤ ◥ ◣ ◢; again turns round; **Free** or turning the camera lets go), **Flat** for no perspective (number pad 7, 1 and 5 as in Blender); grid (at the move step, or **At the selection**, **Turned to it**), cell borders, wireframe, field of view; outdoors the ground, water, sky, **Fog** and how far cells load. |
| ☑ Show | The Show window: what's shown, floors, your changes, hidden things. |
| 🔒 Lock walls | Lit: walls and buildings can't be picked or moved by accident. |
| ⛰ Ground | Outdoors: shape and paint the ground. See *Shaping the land*. |
| ⬚ Extend | Indoors: build out piece by piece from open edges. See *Building interiors*. |

## Walking paths

The **🚶 Paths** panel: **Make them for me** works out a whole set; **✎ Edit by hand** to touch them up. Click
to add a point joined to the selected one (Ctrl+click: not joined), drag to move, Shift+click another point to
join or unjoin, **Delete** removes one. **Esc** or **✓ Done** saves it all as one Undo; **Discard** leaves them as
they were. Outdoors, each cell keeps its own paths.

## A second window

**↗ Second window…** opens this place in another window, looking where you look now. Both are live: change
something in one and the other shows it. Handy on two screens: the map in one, 3D in the other.
