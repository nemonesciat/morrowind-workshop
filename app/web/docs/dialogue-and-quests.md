# Dialogue and quests

*What characters say (greetings and topics), quests and their journal, how the game picks a line, and testing it
all, in the Workshop and in the running game.*

## How Morrowind picks a line

Every topic ("latest rumors", "little secret", "Fargoth"…) and every greeting is a list of lines. **The game says
the first line, from the top, whose conditions all fit.** So a line for one character goes above the general ones.
Drag lines to reorder them.

## The Dialogue page

On the left: **Characters** (open anyone, e.g. Caius Cosades; yours are listed), and **Topics, greetings & quests**
with a search and filters (My mod, Quests, Topics, Greetings, All). **+ New quest** and **+ New topic** at the top.

**📋 All quests** (the Quests filter, or *Browse quests* on the page's first screen) lists every quest in the loaded
data as a table: ID, title, the plugin it comes from, how many stages, how many finish it, and what the Board finds
(⚠ stages nothing leads to, ⛔ stages nothing leads on from). Click a column to sort (by plugin groups each mod's
quests), pick a plugin, or tick **Faulty only**. The Board's check fills in behind the table, twenty quests at a
time, and is kept for the session. A quest opens on its Board.

## A character's dialogue

Open a character and choose a tab:

| Tab | What it's for |
|---|---|
| 💬 Their own lines | Every line they can say, topic by topic: add, change, reorder. |
| 🌳 Write a conversation | One topic as a tree: what they say (the first version that fits is said), the answers the player can give, and what each answer leads to. Saved, it becomes the topic's own lines. |
| 🗺 Conversation map | Every topic and line they can reach, as boxes joined by what leads to what. Drag a box by its title to move it. |
| 🎭 What would they say? | A tester: be any race, sex, faction, rank and level, set quest stages and the rest, and see which line they'd say. It keeps one state across characters, the way a playthrough does. |

## A line

Each line has its text, and:

- **Conditions** (all must fit): a quest's stage, the player having an item, how many of someone are dead, a
  global variable, the answer to a choice, other tests (disposition, skills, reputation…), the speaker's script
  variables, and "the speaker is not…" (a person, faction, class, race or place).
- **Who says it**: everyone, or only a character, a race, a class, a faction (and rank), in a place.
- **What it does** (in the conversation builder): set a quest stage, give the player an item or take one, add a
  topic, change disposition, end the conversation. Lines can also carry a result script.

On the map, a line marked as always beaten by a line above it is one they'll never say.

## Quests

**+ New quest**: an ID, a title, and numbered **journal stages** (10, 20 … 100), each with the journal text; one is
the finishing stage. Characters' lines move it on by setting stages.

A quest has three views: **📜 Stages** (the journal), **🧩 Board**, and **🗺 Flow: who moves it on**, which shows
which characters' lines set each stage, so you can follow the quest from start to end.

### The Board

The Board draws the quest as a **rail**: its stages on one line, in order, each a numbered dot with its journal entry
under it (a filled dot finishes the quest). What brings the player to a stage is written in the gap before it, with no
line to follow: *Talk to Fargoth about "lost ring"*, *Bring the ring to Fargoth + 100 gold*, a kill, a book read, a
door opened, a place entered, days passed. Lines and scripts both count: the Board reads every script in the loaded
data that sets a stage of the quest, and names the move by the test round it (OnDeath, OnActivate, OnPCAdd,
GetPCCell, a day count…). Under each stage, in small print, what has moved by then: what the player carries, who is
dead, who holds the quest's things; and 💬 how many lines are said from that stage on without moving it.

- **A move that skips stages** is an arc over the rail, its words at the top of the arc. A move back to an earlier
  stage is an amber arc below.
- **Another way through.** Where a stage can lead to two next stages, the second runs on a rail below, and comes
  back up where it meets the main line again. *The same way as above* in its last gap means the move written on the
  main line still works from there.
- **At any time**, under the rails: moves that need no stage at all (a kill script, a book), each with the stage it
  sets. When nothing else leads to a stage, such a move is written in its gap instead, marked *any time*.
- **Other quests.** A move that waits on another quest's stage, or sets one, carries a green chip naming it; click the
  chip to open that quest's Board.

Above the rail is the **cast**: the people, creatures, items, books, doors and places the quest touches, with where
they stand (point to one). Point at a move, a stage or a cast member and what it touches lights up while the rest dims;
click a cast member to keep it lit; double-click a person to open their dialogue. Click a move to open its line, or
its script.

Two faults the journal hides are flagged on the stage: **⚠ nothing leads here** (no line or script sets it; the rail
into it is dashed red) and **⛔ nothing leads on** (an unfinished stage no move leaves).

**Map** (beside the zoom) is the other view: every move as a card under the stage it sets, with an arrow from the
stage it starts at, cards you can drag about. The Board remembers which view you last used.

**Making a quest on the Board.** **+ Stage** adds a journal entry. **+ Cast** finds people and things to pin to the
quest before any move uses them. The **+** on a frame adds a move into that stage: pick what the player does, from
which stage, with whom; the Board writes it the way the game does. *Talk*, *Meet*, *Bring* and *Show* become a line of
that person's (at the top of its topic, or their greeting) that needs the stage it starts from and whose result sets the
next, takes the item, hands over the reward and teaches the next topic. *Read*, *Open*, *Use* and *Take* become a short
script on the thing (it still opens or reads as before). *Kill*, *Enter*, *Wait* and *Come near* go into the quest's
own watcher script, started with the game, which looks while the quest stands at that stage. A thing that already runs
a script is left alone: add the stage to that script in Scripts instead. Every move is one change in My mod, so Undo
takes the whole of it back.

### Quests on the map

Make and grow a quest where it happens, in the 3D view.

- **Opening it:** the **🧩** button on the 3D view's bar (it shows the quest you are working on), **🧩 Work on
  it on the map** on a quest's page in Dialogue, or Ctrl+K › *Quest maker on the map*.
- **Any quest:** the quest's name at the top of the quest maker opens a picker:
  - ☆ pinned quests first, then the recent ones and your mod's;
  - type to search every quest: the game's and other mods' too;
  - ☆ pins one, and pins are kept with your mod.

  Continuing the game's or another mod's quest puts what you add into your mod. A note says so, and for another
  mod's quest it reminds you to load your mod after that one.

- **Start one by right-clicking:**
  - a person › 🧩 **Quest given by…**;
  - a thing › 🧩 **Quest that begins when the player finds it / reads it…**;
  - the ground › 🧩 **Quest that begins here…**.

  The **quest maker** opens under the 3D view. Give the quest a title and the first journal line, then **Begin
  the quest**.
- **Add what happens next**, by right-clicking again:
  - a person › 🧩 **Next: talk to / bring something to / kill…**;
  - a thing › 🧩 **Next: take / read / open / use it**;
  - a door › 🧩 **Next: go into…**;
  - the ground › 🧩 **Next: reach this spot**, which draws a ring the player has to walk into;
  - the ground › 🧩 **Put a quest item here…**, which places a copy of the item of the quest's own, so only that
    one counts.

  The **Next:** entries add to the quest you are working on, its name shown beside them, whether the quest maker is
  open or not. **🧩 Next step of another quest…** asks which quest first, from the same picker. A right-click
  guesses the kind of step; the form's first box changes it.
- **Linking quests:** 🔗 **After another quest**: this quest begins, or moves on, when another reaches a stage.
  Pick the quest and the stage from its own journal lines.
  The buttons under **What happens next?** do the same, with search fields for people, items and places, and the
  people of the place as chips to pick.
- **Each step adds its stage**, with the journal line you write, as **one Undo**.
- **The route:** each stage is a row with its journal line (edit it in place) and the steps that reach it. 📍 takes
  the 3D view there.
  - In 3D the steps are numbered pins, joined in the order of their stages.
  - A stage nothing leads to is marked ⚠, and one nothing leads on from is marked ⛔.
- **Changing it:**
  - ✕ beside a step takes it out; its stage stays, marked ⚠, until another step reaches it or you take the stage out.
  - A ring's number box sets how near the player must come. Drag the ring's middle in 3D to move it.
  - Point at a stage for **＋ way here** (another way to reach it) and **＋ from here** (a fork: a step that starts
    there, as for two endings).
  - Each of these is one Undo. A step that can't be written (a thing that already runs a script of its own) is
    refused with the reason and leaves nothing behind.
- **Topics:** a talk, bring or show step teaches the player its topic when the quest reaches the stage it starts
  from, so the player can ask about it.
- **Quest items:** **Put a quest item here** places a copy of the item of the quest's own, so taking any other copy
  doesn't count. If the original runs a script of its own, the copy leaves it off.
- **Where it goes:** under the title, the places its steps happen in, in the order of the stages, each with 📍.
  **Next place ›** takes the map to the next one.
- **🧩 Board** opens the whole quest on its Board.

## A person's card

Right-click a person in the 3D view for **💬 Say something…**, **👤 About…**, **🎒 Gear and wares**, **🪙 Trade
and services** and **🧭 Travel**. Each one opens the person's card under the 3D view, at its own tab.
**Dialogue page** and **Character page** at the top open the full pages.

- **💬 Talk:** what they say now, then your own lines by kind. **Say something** adds one:
  - 👋 a greeting, 💬 a topic (made if it's new, and taught to the player), or 👥 a rumour;
  - **When:** always, once, at a quest's stage, if the player carries something, or between two hours;
  - **Two answers:** the player picks one, and they reply to each, then nothing, goodbye, or give an item.

  ✕ beside a line takes it out.
- **🎒 Gear:** what they wear, by slot, and what they carry, as the game's icons. Click one for its count, ✕ and
  ↻ restocks (it comes back after it is sold). **+ Add an item** searches every item.
- **🪙 Trade:** what they buy and sell, their services (training, spells, repairs…), and their barter gold. The
  game picks these from the class; **Choose them myself** sets them by hand.
- **🧭 Travel:** where they take travellers. Right-click the ground › **🧭 Travel from … to here** adds a place.
- **🧩 Quests:** their quests, and a quick job: 📦 fetch, 📜 deliver, 🔍 find, 🗡 hunt or 👥 meet. Right-clicking
  a person or the ground while the form is open fills it in (**🧩 Job: deliver to…**, **Job: it lies here**).
  **Write the quest** makes it whole, and the quest maker opens on it.
- **📦 Contents:** right-click a container for the same grid of what it holds.

Each change is one Undo. **⚠ in N places**: the person (or container) stands in more than one place, and a change reaches every one.

## Testing in the running game

While the game runs from the Workshop (see *Playing and testing*), the Dialogue page has a **test panel**:

- set quest stages and global variables, give or take items, add topics;
- jump to the people a quest involves;
- see which conditions are true right now, as the game reports quest stages, variables and item counts back.

To start the game partway through a quest, use a **test setup** with the quest at a stage.

## Getting help writing

- **✦ beside a line or a stage** (optional; a model on this PC, Settings › AI) suggests three versions to pick from.
- **A coding agent** of your own (Claude Code, Codex…; *Coding with AI*): "Make a short quest for Fenas: she lost a
  ring in the cave nearby." It writes the quest and the lines, for you to change.
- **Populate** gives new people a greeting and a few lines of their own from templates, with no AI (see *People
  and creatures*).
