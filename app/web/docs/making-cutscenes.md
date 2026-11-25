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

## 5. The timeline

Every shot, animation and line has a block on its row.
- **Drag a block** to move it in time.
- **Drag the end mark** to make the scene longer or shorter.
- **Click the timeline** to pick a time: new things start there, and the 3D view shows the shot at that moment.

## 6. Screen, sound and the end

- **Screen and sound:** fades, black bars, a music file, and videos (the game waits while a video plays).
- **At the end:** the player always gets the controls back. A quest can move to a stage, or a global variable be
  set to 1.

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

## Good to know

- **Agents and connected programs:** a coding agent can make scenes when asked ("Fargoth welcomes the player,
  close-up, then the camera pulls back": see *Coding with AI*), and so can a modding program connected to the
  Workshop. Theirs open here like yours.
- **People:** a person in a scene is found by the very one standing in the place. If they die or are gone, the
  scene ends at once and its end runs.
