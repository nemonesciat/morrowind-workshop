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
- **✋ Fit to the hand** (your own weapon model): turned, placed and sized so the hand holds it as the game's own of
  that kind, shown over a faint game weapon. **⇅ Flip**, **⟳ Turn**, **Grip** and **Length** fix it; **Use it**
  makes a fitted copy in the Library.
- **✋** beside a worn part of yours (a helmet, pauldron, greave, bracer or shield) lays it over the game's own piece
  for that part. Parts that bend with the body (a cuirass, gauntlets) show **⚠**: they need weighting in Blender.
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
- **With OpenMW 0.52**, cast on Target, its "as it lands" steps happen **where the bolt strikes**, even on a corpse, a
  wall or the ground: **Raise the dead** stands up the corpse you hit (with the game's own Resurrect), a **quake**
  shakes there, a **summon** or **placed** thing appears there, and **Blink** takes you there. **Knock down** floors
  them. On 0.51 these work as before: on whoever it lands on (Blink beside them; Knock down by fatigue).
- **Also with OpenMW 0.52:** **Run a script** starts an MWScript (the game's or yours) on whoever it lands on; any step
  can happen **only at full moon**, **at new moon** or **with a moon up**; and **Change the weather** offers your own
  weathers too.
- **More with OpenMW 0.52:**
  - **Stagger** makes them reel, every time or by the game's own odds of a fall. **Strike them** lands a blow as the
    game's weapons do (armour, difficulty, blood, stagger), or one that goes through armour.
  - **Push away**, **Pull in** and **Launch up** can end with them **reeling** or **knocked down**. A quake makes
    people reel, and a hard one floors some.
  - **Glow** makes them glow in your colour. A bolt striking a door or chest makes that glow.
  - **Burst** sets off a spell's area effects where it lands or where the bolt strikes, like a fireball's blast.
    **Cast a spell on them** now follows the game's own rules, with its look and sound.
  - **Every one near** finds every copy of a thing (an ID, or a word such as "lantern") within so many feet, or in the
    whole place. It then hides them, shows them again, makes them glow, or casts a spell on each.
- **School:** with your own schools of magic (below), an effect can belong to one, and its spells train that skill.

Effects from **Tamriel Data** are offered too when it's in your load order.

## Your own skills, attributes and weathers

**Create → New skill, New attribute, New weather** (OpenMW 0.52 or newer; your mod must be an .omwaddon). They're
made as the game loads, with no Construction Set or Lua.

- **A skill** has a name, description, icon, a kind (combat, magic or stealth), the attribute that governs it (the
  game's or yours) and its skill gains. **How it rises:** using or activating the things you name raises it by the
  gain you give.
- **A skill can be a school of magic**: sounding like one of the game's six (or with your own sounds); your magic effects
  can be of it, and casting their spells trains it.
- **Where it counts:** a skill can be a major or minor skill of a class, a faction's skill or a race's bonus; an
  attribute a class's or faction's favoured one, or a race's base value; either one more or in place of one of the
  game's. The game's classes, factions and races, and your mod's.
- **An attribute** sits beside Strength and the rest, to govern your skills.
- **A weather** starts from one of the game's ten. Tick a colour row (sky, fog, ambient light, sunlight) to give it
  your own colours at sunrise, day, sunset and night; the rows start from the game's. Wind, clouds, glare,
  particles, sound, storm, torches and ripples are yours to change too. **Where it comes:** its share of each region's
  weathers you pick, as the game's ash storms have theirs; the region's other weathers get smaller shares.

## Adding to the game's lists (OpenMW 0.52)

**Create → New skill → Lists**: things added to one of the game's random loot or creature lists as the game loads.
The list itself is left as it is, so what other mods add to it stays; a list your mod changes in **Lists** replaces
it whole. Tick **The Forge adds to the game's lists this way too** to have the Forge's "into the game's loot lists"
do the same. Players of your mod need OpenMW 0.52 for these additions.

## Loot rules, ingredients, looking at things and traps (OpenMW 0.52)

In the same place (**Create → New skill**), four more tabs:

- **Loot rules:** loot picked in play from everything the player's load order has, other mods' too, by a rule: what
  kinds (weapons, armour, potions...), words in the name ("daedric", "glass"), a value range, how many, a chance, and
  matched to the player's level if you like. It fills the containers you name the first time each is opened, and
  gives to the people you name the first time each is met. Tick **Glow** and those containers glow until opened.
- **Ingredients:** give an ingredient any four effects, the game's, Tamriel Data's or your own, so alchemy brews them.
  **A new ingredient** is made in the same form: a name, the look of one you pick, your own model and icon if you
  like, its weight and value.
- **Look at:** a line shown at the bottom of the screen while the player looks at a thing, every copy of it or only
  in one place. A scratched name on a skull, a note on a door: the story told by what lies about.
- **Traps:** a spell strikes whoever opens, takes or uses a thing (a cursed chest, a door that burns, a book that drains
  the reader), once for each one or every time, with a line for the player. With 0.52 the game's own rules apply, and
  the spell's area goes off where the thing is. Traps work on 0.51 too, more simply.
