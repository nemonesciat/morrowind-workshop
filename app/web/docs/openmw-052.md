# What OpenMW 0.52 adds

*Everything the Workshop does with OpenMW 0.52's new powers, and where to find it. Your mod must be an
**.omwaddon** (My mod → Save as…), since these are made by OpenMW Lua scripts. On OpenMW 0.51 the rest of the
Workshop works as before; About shows which OpenMW you have.*

## Where to start

**Create → New with OpenMW 0.52** has a card for each:

| Card | What you get |
|---|---|
| New skill | A skill of your own, its icon made from any picture (🖼 From a picture): governed by any attribute, rising as the player uses things you name, taught by books, held by people, in classes, factions and races. It can be a **school of magic**. |
| New attribute | An attribute beside Strength and the rest, to govern your skills. |
| New weather | A weather from one of the game's, with your own sky, fog and light; clouds and particles picked from the game's weathers or your Library, its sound searched by name; and **its share of each region's weathers** you pick. |
| Add to the game's lists | Your items or creatures into the game's random lists, keeping what other mods add. The Forge can do this too. |
| Loot rules | Loot picked in play from everything installed, by kind, words, worth and level, into the containers and people you name. The containers can **glow** until opened. |
| Trap | A spell that strikes whoever opens, takes or uses a thing. Its area goes off where the thing is. |
| Ingredient effects | Any four effects on an ingredient, your own included. Or **a new ingredient**: its name, the look of one you pick, your own model (📦 From the Library) and icon (🖼 From a picture), weight, value and effects, in one form. |
| Look-at lines | A line shown while the player looks at a thing. |

All of them open in one window with a tab for each kind.

## When… then…

A rule in three parts, with no scripting:

1. **When** the player uses an item, activates a thing (a shrine, a plant, a chest, a person) or reads a book.
2. **Only if** (any of these, or none): standing by water; once a day for each thing; once ever; a chance, which
   can grow with each point of a skill or attribute. **If it misses**, a line says so ("Nothing bites.").
3. **Then**, in order:
   - **Raise a skill.** This happens on every try, even when the chance misses, as practice does.
   - **Give items.** `*` gives one more of what the thing activated holds, such as a plant's own ingredient.
   - **Bless:** a bonus to a skill or attribute for some hours, bigger with a stat.
   - **Patron:** a lasting bonus, one of a group at a time.
   - **Cast a spell**, or **show a line**.

Right-click a chest, a book or an item → **What it does** starts one for that thing.

## Examples

**Start from an example** (in the same window) makes one whole, ready to play and yours to change. Open its parts
to see how it's done:

| Example | What it makes |
|---|---|
| 🎣 Fishing | A skill; use a fishing pole by water, and with skill a fish bites. |
| 🙏 Piety | An attribute with two skills: pray at shrines (a blessing), read holy books, take a patron Divine. |
| 🪕 Performance | A skill; play a lute or drum once a day, and passers-by toss coins. |
| 🌿 Foraging | A skill; pick from a plant, and with skill you find one more of what it holds. |
| 🌌 Aurora, 🌀 Arcane storm, 🌫 Mourning mist | Weathers of your own, with the Workshop's own sky art. |
| ⚠ Cursed chest, ✨ Glowing treasure | A trap, and loot rules with a glow. |

**▶** beside an example you've made tries it in the game:
- it switches on a test setup with what the example needs (the fishing pole, a holy book, a chest beside you);
- then it asks where to start, with a hint ("by water").

My mod → **Undo it all** takes an example back.

**📜 See the script** shows the scripts the Workshop wrote, each with a line on what it does.

## Magic effects

**Create → New magic effect**. The steps are grouped (Body, Move, Fight, Magic, World), and the ones new with
0.52 are marked **0.52**:

- Cast on Target, steps act **where the bolt strikes**, even on a corpse, a wall or the ground. **Raise the dead**
  uses the game's own Resurrect. **Blink** takes you there.
- **Stagger**, **Strike them** (a weapon-like blow, or one that goes through armour) and **Knock down**.
- **Push, Pull, Launch** can end with them reeling or knocked down. A quake makes people reel.
- **Glow**, **Burst** (a spell's area goes off there), **Every one near** (every copy of a thing near, or in the
  whole place: hide, show, glow, or cast on each) and **Run a script**.
- Any step can wait for a **moon**: full, new, or a moon up. **Change the weather** offers your own weathers.

## Settings

**Load order → OpenMW settings** marks the settings new in 0.52.

## Good to know

- Players of your mod need OpenMW 0.52 for these. Anything refused shows in openmw.log with "[Workshop]".
- Traps also work on 0.51, without the game's own spell rules.
