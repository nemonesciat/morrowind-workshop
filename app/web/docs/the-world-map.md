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

**?** in the 3D toolbar (or the **⌨ 3D controls** panel) lists every control.

## Selecting

- **Click** a thing to select it. **Shift+click** adds or takes one away.
- **Drag a box** on an empty spot to select many (in 3D; **Shift+drag** on the flat map).
- **Esc** deselects. **Right-click** anything for what you can do with it.
- **H** hides what's selected (to get at what's behind), **Shift+H** everything else, **Alt+H** shows it all
  again. Hiding only changes what you see, not the game.
- **Lock walls & buildings** (View panel) stops you moving them by accident; pick them in the Objects list
  instead.

## Moving, turning and changing

**In 3D**, drag the arrows to move what's selected and the rings to turn it: **G** move, **R** turn, **⤡ Tilt** to
lean it. **✛ World axes / ⟀ Own axes** switches the handles between the world's directions and the thing's
own. **End** (or **⤓ Drop down**) sets it on what's below, **Del** removes it.

**On the flat map**, drag it. Outdoors its height follows the ground.

**⊞ Snap ▾** sets the steps for moving and turning, **Snap to pieces** lines up walls and floors with nearby
pieces as you move them, and **Land on surfaces** rests things on what's below after a move.

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

Double-click a thing in 3D for its window: its record and its placement together.

**Doors** have **Leads to**: search a place to make the door lead there (tick **Make the door at the other end
lead back here**). The arrival spot is chosen for you; **📍 Pick arrival spot…** sets it exactly.

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
| Objects | Every object in the place, with a filter. Open more Objects lists, each with its own filter. |
| View | What's shown (buildings, doors, containers, lights, people, creatures, items), lock walls, your changes, hidden things; indoors, **Floors** hides everything above a height to see lower storeys. |
| Sky | Region, weather and time of day outdoors; an interior's lighting. See *Sky, regions and weather*. |
| Land | Land shaping and height maps. See *Shaping the land*. |
| Paths | The walking paths people and creatures follow. |
| Library, Prefabs, Places, Recent changes, Find gaps, Check this place, 3D controls | Open them from **▤ Panels**. |

## Your changes

- On the map, your mod's changes are marked: **green** new, **gold** changed, a **red ✕** where you took something
  out (right-click it to bring it back). Turn the marks on in the View panel.
- **Show only what your mod changed** hides the rest.
- **My changes** lists them all, each with **Open on map** and **Undo**.

## The 3D view

| Button | What it does |
|---|---|
| 💡 Game light / ☀ Bright | The game's own lighting, or bright even light to work by. |
| 👁 View ▾ | Grid (at the move step, or **At the selection**, **Turned to it**), cell borders, wireframe, field of view; outdoors the ground, water, sky and how far cells load. |
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
