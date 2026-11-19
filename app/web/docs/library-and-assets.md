# Library and assets

*Your own models, pictures and sounds; changing what the game's objects look like; animations; and sharing packs.*

## The Library

The **Library** page holds your own models, pictures and sounds, ready for every mod you make. **Drop files on
it**, or **Choose files…** / **Choose a folder…**:

| Kind | What it takes |
|---|---|
| 📦 Models | From Blender and the like (.blend, .obj, .fbx, .dae, .gltf, .glb), turned into game models; .nif as they are. Drop a model together with its pictures, or the folder they're in. A .blend's particle effects come along (see below). |
| 🎨 Pictures | .png, .jpg, .tga, .dds, .bmp: on your models, or to retexture anything. |
| 🔊 Sounds | .wav, .mp3, .ogg, .flac. |

Everything goes into the folder your mods live in, so the game can use it at once, and a mod that uses it takes it
along when shared.

- As things come in they're **sorted** into a category and a kind (Weapons › Long blade, Armour › Helmet,
  Furniture › Chair…), guessed from the file name. Change it on the card; the Forge offers an Armour › Helmet
  model first for a helmet.
- **Place** a model like anything else: from the Library panel on the World map, or search it in the Place panel.
- A sound can be **put in the world** (it plays over and over where it stands, unseen) or made **a sound your
  scripts can play**.
- Taking something off the list leaves its file, since mods may use it.

### Particle effects from Blender

Flames, smoke, sparks or a fountain made in Blender come in as the game's own kind of particle effect, ready to put
on a light, a static or anything placed.

- **Blender's own particles** (Properties › Particles): the emitter's size and turn, the count over its frames, the
  lifetime, the push and its randomness, the size, gravity and winds, and the material's picture. A **Color Ramp**
  driven by the particle's age gives the colours over its life; an **Emission** shader makes it glow.
- **UnitParticles** (a free add-on that copies Unity's particle system): the cone or other shape, rate, lifetime,
  speed, size, gravity and force, colour and size over lifetime, and an additive or alpha material. Velocity over
  Lifetime's pull to the middle (Radial) and its Speed Modifier become the game's pull toward a point. The Workshop
  reads these through Blender, with the add-on installed there, so opening the file takes a little while.
- **Add a model** shows **✦ With its particles**: untick it to leave them out. A model and its particles become one
  model; particles alone become an effect of their own (**✦ Particles** on the card).
- What the game has no place for (noise, trails, collisions, sub-emitters, spin…) is left behind, and the window
  says which.
- Effects of their own are kept in the **Particles** group on the Library page (Fire, Smoke, Sparks, Water, Magic,
  Dust and ash, guessed from the name). In the 3D view, click an effect at the spot it comes from.

The effects are drawn in the 3D view and in the Library's 3D look, as the game draws them.

## Packs

**Packs** share prefabs, scatter brushes and your models as one file. **🗂 Browse packs…** shows the ones you have,
**⤓ Make a pack…** makes one, **⤒ Open a pack…** opens one someone shared.

## What an object is drawn with

Right-click an object → **🧩 Model & textures…** (or from its window, or from its page in **Browse**) shows its model (where its file comes from,
its shapes, triangles and size, whether it has collision, animation, particles, a light…), what else uses it, and its
textures with pictures.

| Button | What it does |
|---|---|
| ✎ Change everywhere | A copy of the game's texture goes into your mod's own folder under the same name, so the game draws your copy wherever that texture is used, on other objects too. |
| ✎ For this one only… | A copy under a new name, and a new record of the object drawn with it. Opened from something placed, that one changes and nothing else does. |
| ↺ The game's own again | Takes your copy back out. |
| ⬡ Open in Blender | The model out to Blender; when you save it there, it comes back. Its particle effects go too, as Blender particle systems, and whatever you leave alone in them comes back exactly as the game had it. |

The texture opens in your picture editor, and while the window is open the 3D view draws it again each time you
save.

**✨ Particles** (in the same window, for a model with particle effects): **Amount**, **Life**, **Speed**, **Size**
and **Pull** sliders, and a **Colour**, for all of its effects or one, seen at once in a preview of its own. A colour
keeps each effect as bright as it was, in the colour picked: an orange flame can turn blue. Save it **everywhere**
(every object drawn with that model) or **for this one only** (only the one you opened it from). The same goes for
a model brought back from Blender.

To start from one of the game's effects: **Browse** → **✦ Particle effects** (under World) lists everything drawn with
particles, the game's and your mods'. Pick one, press **🧩 Model & textures…**, and save it **for this one only**: a
new object of your own, ready to place. (The first time, every model is looked through, which can take a while.)

**🎨 Retexture** (Selected panel, or right-click) makes a new object like the one selected, with your own pictures.

## Animations

**🎞 Animations and text keys…** (right-click a moving thing, or **🎞 Animations** on a character):

- The model is played as the game plays it. Pick a **group** (Idle, WalkForward, Attack1…) and play it.
- **Text keys** name the groups and time the sounds: change, add or take them out. Save **everywhere** (your mod's
  copy of the game's file) or as **a new copy** of the creature with its own files.
- People move in **layers**, as the game puts them together: everyone's animation, then the women's or beast
  folk's, then their own model's. **For this person only** puts a group into their own animation file.
- A group's motion can go to **Blender** and come back as keyframes.

## Icons

**🖼 From a picture…** beside an Icon box (items, your own magic effects) makes the icons the game wants from any
picture: a magic effect's small icon and its large twin, an item's inventory icon. A Library model can make its
own inventory icon again from the model.
