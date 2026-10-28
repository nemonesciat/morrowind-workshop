# Library and assets

*Your own models, pictures and sounds; changing what the game's objects look like; animations; and sharing packs.*

## The Library

The **Library** page holds your own models, pictures and sounds, ready for every mod you make. **Drop files on
it**, or **Choose files…** / **Choose a folder…**:

| Kind | What it takes |
|---|---|
| 📦 Models | From Blender and the like (.blend, .obj, .fbx, .dae, .gltf, .glb), turned into game models; .nif as they are. Drop a model together with its pictures, or the folder they're in. |
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

## Packs

**Packs** share prefabs, scatter brushes and your models as one file. **🗂 Browse packs…** shows the ones you have,
**⤓ Make a pack…** makes one, **⤒ Open a pack…** opens one someone shared.

## What an object is drawn with

Right-click an object → **🧩 Model & textures…** (or from its window) shows its model (where its file comes from,
its shapes, triangles and size, whether it has collision, animation, particles, a light…), what else uses it, and its
textures with pictures.

| Button | What it does |
|---|---|
| ✎ Change everywhere | A copy of the game's texture goes into your mod's own folder under the same name, so the game draws your copy wherever that texture is used, on other objects too. |
| ✎ For this one only… | A copy under a new name, and a new record of the object drawn with it. |
| ↺ The game's own again | Takes your copy back out. |
| ⬡ Open in Blender | The model out to Blender; when you save it there, it comes back. |

The texture opens in your picture editor, and while the window is open the 3D view draws it again each time you
save.

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
