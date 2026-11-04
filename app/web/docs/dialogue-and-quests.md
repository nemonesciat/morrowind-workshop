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

## Testing in the running game

While the game runs from the Workshop (see *Playing and testing*), the Dialogue page has a **test panel**:

- set quest stages and global variables, give or take items, add topics;
- jump to the people a quest involves;
- see which conditions are true right now, as the game reports quest stages, variables and item counts back.

To start the game partway through a quest, use a **test setup** with the quest at a stage.

## Getting help writing

- **✦ Ask the assistant** (optional; your own API key): "Make a short quest for Fenas: she lost a ring in the cave
  nearby." It writes the quest and the lines, for you to change.
- **Populate** gives new people a greeting and a few lines of their own from templates, with no AI (see *People
  and creatures*).
