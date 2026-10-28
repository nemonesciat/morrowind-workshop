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

A quest has two views: **📜 Stages** (the journal), and **🗺 Flow: who moves it on**, which shows which characters'
lines set each stage, so you can follow the quest from start to end.

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
