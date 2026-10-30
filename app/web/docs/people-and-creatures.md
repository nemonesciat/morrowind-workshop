# People and creatures

*Making new people, changing anyone in the game, filling a place with the people who'd live there, and random
creature spawns.*

## Making someone new

**Create → New NPC** (or **Characters → + New character**). Pick a **role** and the Workshop sets them up,
dressed the way the game's own people of their race and class are:

| Role | What they do |
|---|---|
| Townsperson | Wanders about and talks using the normal topics for their race and class. |
| Quest character | Stays near where you put them and is **essential** (can't be killed), ready for your quest dialogue. |
| Merchant | Stays put and trades; pick what they sell. |
| Guard | Wears the guard kit for their race and reacts to crimes. |

Give them a name, race, sex, class, level and faction, and say where to place them (the World map's view, the
spot you right-clicked, or where your character stands in game), or place them later. One Undo takes them back.

## The Characters page

Open anyone (your own characters, or anyone in the game, Fargoth included) from **Open a character** on the left.
**In my mod** lists the ones you've made or changed. The game's own stay safe: your version goes into your mod.

| Tab | What's on it |
|---|---|
| 👤 Who | Name, race, sex, class, faction and rank, level, size, script; **Essential** and **Respawns**; their looks (head, hair). |
| 📊 Stats | Attributes, health, magicka, fatigue, skills, disposition, reputation, gold. **Work out stats automatically** sets them from race, class and level as the game does. |
| 🧭 Behaviour | **Temper**: Fight (ordinary people about 30, bandits and wild animals 80 to 100, which attack on sight), Flee, Alarm (how likely they report crimes; guards 100), Hello (how far away they greet you). **What they do**: wander (how far, for how long, how often they fidget), walk to a spot, follow or escort someone, use an object. |
| 🪙 Services & travel | What they buy and sell, what they offer (repairs, spells, training…), and the places they can take the player, like caravaners and boatmen. |
| 🎒 Carries & knows | What they carry (they wear the best and use the best; for merchants, **restocks** things come back after they're sold) and the spells they know. |

At the top: **💬 Dialogue** (their greetings and topics), **🎞 Animations** (how they move), **⧉ Make a copy** (a new
character based on this one), **↺ Undo edits** (forget what you haven't saved) and **Save**.

Creatures have their own page: kind, level, size, their **model**, the sounds they make, attributes, attacks, soul
value and gold.

On the World map, select a person and press **👤 Edit character** (or **💬 Dialogue**) in the Selected panel.

## Populate a place

Right-click inside a place → **👥 Populate this place…**: the Workshop proposes a cast, the people who'd live or work
there as the game's own places of its kind have them (a house, a tavern, a guildhall, a cave, a camp…).

- **How busy**, **Wealth**, **Kind of place**, **Faction**, **Races** and **Occupations** change the cast.
- Each person has a name, race, class, level, where they'll stand ("by the bed", "by the counter"), and what they
  carry. **Change them** edits one; **🎲** gives someone else instead; **🔒** locks them so **🎲 New cast** keeps them;
  **✕** leaves them out; **+ One more** adds one.
- **The household owns the beds and chests**, and **words of their own**: a greeting, their trade, someone in
  particular, a little secret and a rumour each, written from templates (no AI). Change them here or later in
  Dialogue; **✦** asks the Assistant to write a line better.
- **Band** (dungeons): the people are one band, as the game's dungeons have them: bandits, smugglers, Daedra
  worshippers, Sixth House cultists, necromancers or rogue mages, led by the strongest of them, all fighting on sight,
  with their kind's **Loot** (crates, chests, sacks) against the walls. **No band** gives the place's usual people.
- **Creatures**: caves, mines, tombs, ruins and other dungeons also get the creatures and creature lists the game's
  own places of that kind hold, as many as theirs. A list (⟳) picks its creature by the player's level. Fish and other
  swimmers go only where the floor is under the water. Click one to leave it out; **🎲** beside them gives others.
- **Daily routines** (OpenMW): each sleeps by their own bed, eats at a table, works where they stand here and
  spends the evening at the table or the fire, by the hours, each a little earlier or later than the rest. When you
  come in they're where the hour puts them; while you watch they walk to the next spot. Anyone hurt, dead or with a
  weapon out is left to the game. Guards and tavern patrons stay put. A script in your mod (**wsroutines**, on the
  Scripts page) keeps the days; plain Morrowind ignores it.
- Nothing is placed until you press **Place them**. One Undo takes them all back.

**🧍 Someone who'd live here** (right-click a spot) does the same for one person.

## Random creatures and loot: leveled lists

**Create → Random loot or spawn list** opens the list editor: a list the game rolls on, different each time and
matched to the player's level (what a chest holds, what a bandit carries, which creature appears). Start empty or
copy an existing list, then add items (or creatures, or other lists) with the player level from which each can
appear. Two switches: whether lower-level entries keep appearing as the player levels up, and whether several of
the list (say 5 ×) are rolled one by one. Use it wherever the game takes an item or a creature: a container, a
character's inventory, a region's sleep encounters.

## Teaching spells to many people

**Create → Give spells to people** teaches spells to everyone who fits (by race, class, faction, a spell they
already know or a skill) in the regions or towns you pick: in their records, or by a script that leaves their
records untouched.

## Groups and backgrounds

Factions, classes, races and birthsigns are on the **Rules** page (also linked from the Characters page). See
*Scripts and game rules*.
