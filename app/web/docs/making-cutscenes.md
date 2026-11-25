# Your first cutscene

*A scene step by step: somebody greets the player as they arrive. About five minutes. Home › **Your first cutscene**
walks you through the same steps on the real buttons.*

## What a scene is

A scene is a short piece of film played in the game: the camera cuts between shots, people stand where you put
them and play their animations, they say their lines (lips moving with a voice file), music plays, the screen
fades, and at the end the player gets the controls back. Something starts it: the player coming near a spot, a
line of dialogue, a quest stage, or another script. In the game, Space or Enter skips it; its end always runs.

Scenes play in an .omwaddon mod (the kind the Workshop starts).

## 1. Start where it happens

1. Open the **World map** and go to the place (*Go to a place…*: Seyda Neen, say). Switch to **3D**.
2. Right-click the person who'll greet the player › **🎬 Scene with…** › **The player arrives here**.

The **scene maker** opens along the bottom of the map, under the 3D view. The person is in it, with a close-up
ready, and a green ring in the 3D view marks where the scene starts. Drag the ring to move it.

Other ways in:
- **The ground:** right-click it › **🎬 New scene here…**.
- **A door:** right-click it › **🎬 Scene when the player comes through this door**.
- **The menus:** Scripts or Dialogue › **🎬 Scenes** › **+ New scene**.

## 2. Put everyone on their spots

Right-click the ground › **🎬 <name> stands here**, then right-click again › **🎬 The player stands here**.
- **Markers:** a gold marker shows each person and a blue one the player, with a cone for the way they face. They
  turn to face each other.
- **Moving them:** drag a marker in the 3D view.
- **Taking a spot away:** **✕ spot** lets someone stay where they already stand.

## 3. Shots

**+ Shot on someone** aims at a person:
- **Close-up:** their face.
- **Medium:** head and shoulders.
- **Wide:** the two of them and the place.
- **Over the player's shoulder:** behind the player, looking at the person.

Tick **push in** and the camera moves slowly closer during the shot.

**Your own framing:** move the 3D view until it looks right, then **+ Shot from the 3D view**. Or right-click the
ground › **🎥 Camera here, looking at…**. A purple cone marks each fixed camera. **👁** shows any shot in the 3D view.

## 4. What they say and do

- **+ Line** and type it.
  - **🔊 Voice…** picks a voice file from the game (search by a word, or a race and sex such as `d/m` for a Dark
    Elf man). The line then lasts exactly as long as the voice.
  - **⇣ One after another** spaces the lines so each starts when the one before ends.
- **+ Animation** picks what someone does, in words with the game's own name beside it: Standing, Fidgets,
  Walks forward, Casts a spell…. **▶** plays it so you can see it. **repeat** loops it until their next animation.

- **Coming and going**, under each person:
  - **comes in** at a time, with an effect if you like (a summoning flash);
  - **+ Walk** walks them to a new spot: drag its 🚶 marker in 3D, add more for a path. Or right-click the ground ›
    🚶 … walks here. They walk straight from spot to spot, so keep the way clear;
  - **leaves** at a time: **dies** or **vanishes**;
  - **back after** puts them where they stood once the scene ends.
- **Someone new:** type a person or creature and **+ Bring in**. The scene makes them at their spot when they come
  in, keeps them calm so guards leave them be, and takes them away at the end unless **stays after** is ticked.
- **Effects:** **+ Effect** picks fire, magic or one of your mod's own particle effects, **on** someone (their whole
  body, head or a hand) or **at a spot** (drag its ✨ marker). **for** how long, **repeats** for fire and smoke.
  Right-click the ground › ✨ An effect here.
- **In the world:** a door opens or closes, a lever is used, a light goes out, a thing is shown or hidden; the
  **weather** changes (and comes back after); the **time of day** moves on.

## 5. The timeline

Every shot, animation and line has a block on its row.
- **Drag a block** to move it in time.
- **Drag the end mark** to make the scene longer or shorter.
- **Click the timeline** to pick a time: new things start there, and the 3D view shows the shot at that moment.

## 6. Screen, sound and the end

- **Screen and sound:** fades, black bars, a music file, and videos (the game waits while a video plays).
  **+ Sound** plays one of the game's sounds by name (a door creaking, a spell) or a file, heard from someone or
  something. **+ Shake** shakes the camera.
- **Cuts:** each shot after the first can **dip to black** or **dip to white** instead of a straight cut.
- **Look:** **+ Colour** (lighter or darker, warmer or colder, less colour, dark edges), **+ Focus** (sharp on someone
  or at a distance, the rest soft) and **+ Motion blur**. Each blends in over its *over* seconds and holds until the
  next one changes it. Preview shows them roughly; the game shows them properly when the player has post-processing
  on in OpenMW (Options › Post Processing). Without it the scene plays the same, without the look.
- **At the end:** the player always gets the controls back. A quest can move to a stage, or a global variable be
  set to 1. **Talk with** opens the conversation with someone again: for a scene started from a line of dialogue
  (the line says Goodbye to let the scene play, and the talk picks up after it).

## 7. Preview, keep, try

- **▶ Preview:** the 3D view runs through the shots in time, with the lines as subtitles. People don't move in the
  preview; they do in the game.
- **Check:** finds anything that would stop it playing.
- **Save:** keeps the scene in your mod (Undo takes it back). **File › Save** writes the mod.
- **▶ Try it in the game:** starts OpenMW right there and plays the scene a few seconds after you arrive. After
  changing the scene, quit the game and press it again: the game reads scenes when it starts.

## What starts it

Under **Starts when**:
- **The player comes near a spot:** the green ring.
- **After a line of dialogue:** save the scene, then in Dialogue open the line › **Then do** › **🎬 Play a scene**.
- **A quest reaches a stage:** or in Dialogue, the quest's stage › **🎬**.
- **A global variable is set to 1:** from MWScript.
- **Only when a script asks:** another script sends `WsScene_Play`.

**once a game** is ticked to start with.

## Two scenes to make yourself

**Fargoth and the Dremora** (Seyda Neen; starts when the player walks up to Fargoth):
1. Right-click Fargoth in 3D › 🎬 Scene with Fargoth… › The player comes near. Right-click the ground beside him ›
   🎬 The player stands here.
2. Type `dremora` under People › Someone new, **+ Bring in**, and drag its marker a few steps in front of him.
   Tick **comes in** at 2.6 s with the summoning effect (**Soul Trap / Summon Start…** under Magic).
3. **+ Effect** at 6 s: **Fire Shield** on Fargoth, for 6 s, repeats. Right-click the ground at his feet › ✨ An
   effect here, and pick **Fire** under Fire.
4. Fargoth: **leaves** at 9 s, **dies**. The Dremora: **+ Walk** at 11 s, **leaves** at 14 s, **vanishes**.
5. Shots on each of them, one wide one; **dip to black** on the wide one. **+ Shake** at 2.6 s, **+ Sound**
   `conjuration hit` from the Dremora, **+ Weather** Thunderstorm, back after.

**News from Balmora** (the Census office; starts from a line of Sellus Gravius's dialogue):
1. A scene in the office with Sellus Gravius and Socucius Ergalla; the player on a spot in front of Sellus.
2. Socucius: **comes in** at 2.4 s on a spot by the door, **+ Walk** to beside the player, later **+ Walk** back,
   **leaves** (vanishes), **back after**: he is at his desk again once it ends.
3. **+ Sound** `Door Creaky Open` from the door, the lines, the shots.
4. At the end › **Talk with** Sellus Gravius. Save.
5. In Dialogue, a new topic for Sellus, a line › **Then do** › **🎬 Play a scene**. The line closes the
   conversation, the scene plays, and the conversation opens again after it.

## Good to know

- **Agents and connected programs:** a coding agent can make scenes when asked ("Fargoth welcomes the player,
  close-up, then the camera pulls back": see *Coding with AI*), and so can a modding program connected to the
  Workshop. Theirs open here like yours.
- **People:** a person in a scene is found by the very one standing in the place. If they die or are gone (not by
  the scene's own doing), the scene ends at once and its end runs.
- **Skipped:** who comes in, dies or goes still does, so the world is as the scene leaves it.
- **Walking** goes straight from spot to spot: put spots where the way is clear. Someone in the way stops them just
  short.
