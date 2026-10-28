# Items, spells and the Forge

*New items, books, spells and magic effects, weapons and armour from the Forge with the game's own numbers, and
getting them into the world.*

## New items

**Create → New item**: clothing, a potion, a tool or any other item, **started from one you pick** (its look and
type come from it). Name it, set its stats, **enchant it** if it can be, and give it to someone or place it.
Weapons and armour open in the Forge instead.

**Create → Note, letter or book**: something to read in game, in your own words, placed somewhere or given to
someone.

**Create → Container with contents**: a chest, crate, barrel or sack, filled with what you choose (or a random loot
list), locked and owned if you like.

## Changing any item or spell

**Create → Edit an existing item or spell** (or **✎ Item editor** on any item in Browse) changes anything already
in the game: stats, effects, enchantments, looks, script. Your version goes into your mod.

- Enchantments: **Cast once**, **Cast when strikes**, **Cast when used**, **Constant effect**.
- Spells: **Spell**, **Ability**, **Blight disease**, **Disease**, **Curse**, **Power**.
- **🖼 From a picture…** beside an Icon box makes an inventory icon from any picture, at the sizes the game wants.
  **📦 From the Library…** beside a Model box uses one of your Library's models.

## The Forge: weapons and armour

**Create → Forge a weapon or armour** (or right-click a weapon or armour piece → **⚒ Forge a new piece like this…**).
Three tabs: **A piece**, **A whole set**, then **Into the world**.

**A piece:**

- Pick **what it is** (a longsword, a cuirass…) and its **material** (iron, steel, glass, ebony, Daedric, and
  mods' own), or **a new material between two** of the game's.
- The Workshop fills in **the game's typical numbers** for that kind and material, shows the game's own range beside
  each, and warns when yours go beyond anything the game does. Armour shows its weight class by the game's rule.
- **The look** is taken from one of the game's pieces of that kind (any in your load order, mods' too), or your own
  model from the Library. **Skins** swap its pictures: swap one and every piece that uses it changes. The originals
  stay as they are; new copies are made.
- The Forge remembers each piece's material.

**A whole set** makes every piece of a set at once, with the same choices.

**⚒ Forge it** makes the records. One Undo takes them back.

## Into the world

After forging (or for any weapon or armour), **Into the world** says where the game should have it:

| Section | What it does |
|---|---|
| Loot lists | The game's random lists where its like are (widest-used first), at the level its material has in each. More lists for a people, faction or place fold out below. |
| Carried by, instead of theirs | People who carry one like it, by class. Tick someone and theirs is swapped for yours (for a set: they wear the whole set). |
| Merchants with one like it | Tick them and they sell it. |
| Extras | Give it to someone by name, sell it at a merchant, or a list of your own. |

Each change copies that list or person into your mod; one Undo takes it all back. If another mod changes the same
list or person, the one loaded last wins.

## Spells

**Create → New spell**: a spell, ability, power, disease or curse with your own effects (each with its range,
area, magnitude and duration). Give it to someone, or to the player.

**Create → Give spells to people** teaches spells to everyone who fits (by race, class, faction, a spell they know
or a skill) in the regions or towns you pick: in their records, or by a script that leaves them untouched.

## Your own magic effects

**Create → New magic effect** (OpenMW 0.50 or newer; your mod must be an .omwaddon, since a plain .esp can't carry
Lua):

- It **looks like** one of the game's effects (school, icon, colours, sounds, spell pictures), with its own name,
  icon, base cost and description. **How it looks** can mix the look part by part: casting, the bolt, hitting, the
  area, sparkles, colour and bolt speed.
- **What it does** is what you pick, one step or several: change health, magicka or fatigue; leech them; an aura;
  launch, dash or pull; grow or shrink; calm, frenzy or swap places; teleport; summon or spawn creatures;
  resurrect; shake the ground (a quake); change the weather; transmute items; cast another spell; set a global
  variable; show a message; or a line of Lua. Each runs **as it lands**, **each second** or **as it ends**, on
  anyone or only on people, creatures, the undead, Daedra or the player.
- The spell, enchantment and potion editors then offer it with the game's effects.

Effects from **Tamriel Data** are offered too when it's in your load order.
