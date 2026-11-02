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

All eight open in one window with a tab for each kind.

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
