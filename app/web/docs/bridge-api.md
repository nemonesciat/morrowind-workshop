# Morrowind Workshop bridge: for programs that work with the Workshop's open mod

*For the authors of modding programs (first the OpenMW Suite for Blender and Maya) and their coding agents. Bridge
API 1, Workshop 2.9.8 and later (records, land and object details: 2.9.9). Nothing here is for the Workshop's own users.*

## How it works

The mod open in the Workshop is the main copy. Your program sends its work into that open mod:

- Each change goes in as one change with its own **Undo**. It shows in the user's *My changes* marked
  `⇄ <your program's name>: ...`.
- Your changes **join the user's unsaved work**, the same way a second Workshop window's would. Nothing is written
  to the mod's files until the user saves (Ctrl+S). Coding agents and scripts are refused while anything is
  unsaved; a program the user allowed is not.
- The Workshop's window follows what you do: it goes to the place you change, and a line at its foot says what was
  done.
- Files (models, animations, pictures, sounds) are the exception: they go into the mod's folder at once, as the
  Workshop's own Library does.

Everything is plain HTTP and JSON on `127.0.0.1`. Python's standard library is enough (`urllib.request`). Turn
off proxies: `urllib.request.build_opener(urllib.request.ProxyHandler({}))`.

## 1. Finding a running Workshop

A running Workshop writes `running.json`:

| System | Where |
|---|---|
| Windows | `%LOCALAPPDATA%\Morrowind Workshop\running.json` |
| Linux | `$XDG_DATA_HOME/morrowind-workshop/running.json`, else `~/.local/share/morrowind-workshop/running.json` |

```json
{"pid": 4120, "port": 57243, "url": "http://127.0.0.1:57243/", "bridge": "http://127.0.0.1:57243/bridge/",
 "bridge_api": 1, "version": "2.9.8", "home": "C:\\...\\Morrowind Workshop"}
```

The file is removed when the Workshop closes. A file left behind by a crash points at a dead port: if a call fails,
treat the Workshop as closed. Before relying on it, check that `bridge_api` is a version you know.

## 2. Connecting (once)

```
POST /bridge/hello      {"program": "OpenMW Suite (Blender)", "version": "4.1.0"}
  -> {"id": "1cff0a97...", "state": "waiting"}
```

The Workshop's window asks the user: *"OpenMW Suite (Blender) wants to connect"*, **Allow** / **Not now**.
Poll every second or two:

```
GET /bridge/hello?id=1cff0a97...
  -> {"state": "waiting"}
  -> {"state": "allowed", "key": "…", "block": [14000000, 15999999]}     (given once: keep it)
  -> {"state": "refused"}  or  {"state": "unknown"}                     (unknown: expired after 10 minutes, or already taken)
```

- **Keep the key** in your own settings. Send it with every other call as `Authorization: Bearer <key>`.
- A **401** means the user removed your program (Settings › Connected programs). Ask again with `/bridge/hello`.
- Use the same `program` name every time. Asking again under the same name replaces the old key and keeps the same
  block of numbers.
- Calls that carry an `Origin` header (from web pages) are refused.

## 3. Calls

Every answer is JSON. A refusal is a 400 with `{"error": "a sentence for the user"}`: show it as it is.

### Reading

| Call | Answer |
|---|---|
| `GET /bridge/status` | `bridge_api`; `workshop` (version); `scene_format` (`"openmw-scene/1"`); `scene_player` (the scene player's version, `"1"`); `lua_slug` (the mod's name in its Lua paths and events); `lua_ok` (false for a plain .esp, which can't hold Lua); `program`; `block`; `ready`; `mod` (`name`, `plugin` file name, `folder` where its files are, `unsaved`, `unsaved_since`, `masters`); `changes` (the change counter) |
| `GET /bridge/changes?since=n` | `n` (the counter now); `changes` (`[{n, by, cells, records}]` since n: `by` is who made each one, `bridge:<your name>` for yours; `cells` lists the cells it touched); `all: true` when n is too old to say, so read everything again; `mod`; `unsaved` |
| `POST /bridge/snapshot` `{}` | The open mod on disk as it is now: `{"unsaved", "plugin", "folder", "changes"}` |
| `GET /bridge/scenes` | `{"scenes": [{"scene", "name", "length"}]}` |
| `GET /bridge/scene?scene=<id>` | The scene file as it was sent |
| `GET /bridge/actions?search=furnish` | The Workshop's own actions matching the words |

**Staying in step.** Load the mod once from `snapshot`. Then ask for `changes?since=<n>` every second or so, and
reload only the cells listed. When `all` is true, the mod was switched, or `mod` changed, take a new snapshot.

**What `snapshot` gives:**
- With nothing unsaved, `plugin` is the mod's own file.
- With unsaved work, it is a **test copy** in a folder of the Workshop's own, the same copy Play here writes. The
  next snapshot or Play here writes it again, so read it straight away and don't keep the path.
- `folder` is where the copy's plugin sits. The mod's models and pictures stay in `status.mod.folder`.

### Objects

Positions are game units. Turns are degrees about x, y, z, as the game stores them; send `"degrees": false` for
radians. `cell` is `[x, y]` outdoors, or an interior's name. An object is `{"file": "<plugin>", "index": n}`,
the same plugin + index your program already uses.

```
POST /bridge/place   {"cell": [-2, -9], "id": "barrel_01", "pos": [-11100, -70000, null, 0, 0, 90], "index": 14000017, "scale": 1.0}
  -> {"ref": {"file": "my mod.omwaddon", "index": 14000017}, "cell": "#-2,-9"}
POST /bridge/move    {"cell": [-2, -9], "ref": {"file": "my mod.omwaddon", "index": 14000017}, "pos": [x, y, z, rx, ry, rz], "scale": 1.0}
POST /bridge/delete  {"cell": [-2, -9], "ref": {"file": "morrowind.esm", "index": 12345}}
```

- **Your block of numbers.** A new object may carry the `index` you gave it in your own draft. It must be inside
  your `block`, and not already used in the mod. The Workshop never renumbers objects, and Save As keeps every
  number.
- Leave `index` out and the Workshop gives the mod's next number; the answer says which.
- `pos` may be `[x, y, z]`. A new object's `z` may be `null`: it is set down on what is under it.
- Moving or deleting an object of the game or of another mod works the same way. The game's original stays as it
  is, and the mod records the change.

### Records, land and path grids (Workshop 2.9.9)

```
POST /bridge/record         {"type": "NPC_", "id": "mi_flima", "flags": 0, "subs": [["NAME", "<base64>"], ["FNAM", "<base64>"], ...]}
  -> {"type": "NPC_", "key": "mi_flima", "made": true}
POST /bridge/record/delete  {"type": "NPC_", "id": "mi_flima"}
```

- **Any record, sent as your program writes it.** `subs` is the record's subrecords in order, each as its
  four-letter tag and its bytes in base64 (no record header). The Workshop keeps it as the mod's version:
  - one the mod didn't have is **made**;
  - one the game or a master has is **overridden**.
  Each send is one change with Undo.
- **Types taken:** `ACTI ALCH APPA ARMO BODY BOOK BSGN CLAS CLOT CONT CREA DOOR ENCH FACT GLOB INGR LAND LEVC LEVI LIGH
  LOCK LTEX MISC NPC_ PGRD PROB RACE REGN REPA SCPT SNDG SOUN SPEL STAT WEAP`.
- **The record's key:**
  - Most records go by their `NAME`. `id` must match it.
  - **LAND** (terrain): the record's own `INTV` says which cell, so leave `id` out. Send it whole, with `VHGT`
    heights, `VTEX` texture paint, `VCLR` vertex colours, `VNML` and `WNAM`, as the game writes it.
  - **PGRD** (path grid): `id` is the cell (`[x, y]` or an interior's name).
- **New things together:** send a new record **before** placing it (an NPC Maker character, an Object Creation
  item, Build's doors and lights). Then `/bridge/place` can use its id at once.
- **`record/delete`** takes back the mod's version. A record it made is removed; one it changed goes back to the
  game's. For LAND, `id` is `[x, y]`.
- **Path grids without bytes:** `POST /bridge/action {"action": "/api/paths/save", "args": {"cell": "#x,y" or an
  interior's name in lower case, "pts": [[x, y, z], ...], "edges": [[a, b], ...]}}`. Outdoors, points are world
  positions.

### An object's details (Workshop 2.9.9)

```
POST /bridge/ref_fields  {"cell": [-2, -9], "ref": {"file": "my mod.omwaddon", "index": 14000017},
                          "lock": 40, "key": "key_mi_chest", "trap": "", "owner": "mi_flima", "faction": "", "rank": 0,
                          "global": "", "soul": "", "uses": null, "charge": null,
                          "door": {"cell": "Seyda Neen, Census and Excise Office", "pos": [x, y, z, rx, ry, rz]}}
```

- **Fields work as in the Workshop's own object window.** Leave one out and it stays as it is; `""` or `0` clears
  it. Names are checked: the owner must be an NPC, the key a misc item, the trap a spell, and so on.
- **`door`** sets where a door leads: `pos` in degrees, and `cell` an interior's name (leave it out for outdoors).
  `"door": null` makes it lead nowhere.
- Works on objects of the mod and of the game. Each call is one change with Undo.

### Files

```
POST /bridge/file  {"path": "C:\\work\\animations\\xflima.kf", "to": "meshes/mi/xflima.kf", "replace": false}
  -> {"to": "meshes/mi/xflima.kf", "path": "<the mod's folder>\\meshes\\mi\\xflima.kf", "kept": null}
```

- `to` is the path the game looks for, starting with one of: meshes, textures, icons, bookart, sound, music,
  splash, video, fonts.
- File types taken: `.nif .kf .dds .tga .bmp .png .jpg .wav .mp3 .ogg .bik .fnt .tex`.
- A file already there is refused unless `"replace": true`. The one it replaces is kept beside it as
  `<name>.before-<time>`.
- **Animations:** send both halves (`xname.nif` and `xname.kf`). To give one character its own animation file,
  send the files, then set that NPC's animation through an action (see below) rather than changing every actor
  with the skeleton.

### Scenes

```
POST /bridge/check_scene   {"scene": {...}}   -> {"problems": [{"level": "error"|"warning", "text"}]}
POST /bridge/scene         {"scene": {...}}   -> {"kept": true, "scene": "<id>", "problems": [...]}
POST /bridge/scene/delete  {"scene": "<id>"}
```

A scene with an error isn't kept, and the answer says why. Kept scenes are part of the mod, with Undo, and are
written when the user saves. The Workshop keeps fields it doesn't know and sends them back as they were.

### Anything else the Workshop does

```
GET  /bridge/actions?search=npc animation
POST /bridge/action  {"action": "/api/edit", "method": "POST", "args": {...}}
```

This runs any of the Workshop's own actions, as its window would: records, NPCs, dialogue, furnishing, towns and
the rest. The answer is that action's own answer. Actions kept for the user are refused: opening or switching
mods, settings, Undo, starting the game, deleting files.

## 4. The scene file: openmw-scene/1

```json
{
  "format": "openmw-scene/1",
  "scene": "mi_welcome",
  "name": "Maggie Island welcome",
  "cell": [48, -44],
  "length": 20.0,
  "player": {"mark": "A", "controls": "off", "sheathe": true},
  "marks": {"A": [394500, -356800, 210, 20], "B": [394620, -356700, 212, 200]},
  "actors": [
    {"key": "flima", "ref": {"file": "Maggie Island.omwaddon", "index": 412}, "mark": "B",
     "clips": [
       {"at": 0.0, "group": "idle2", "loop": true},
       {"at": 5.0, "group": "mi_flima_welcome", "blend": 0.3, "speed": 1.0, "endMark": "B"},
       {"at": 12.0, "group": "mi_flima_summon", "keys": {"cast": "vfx:glow"}}
     ]}
  ],
  "shots": [
    {"at": 0.0, "name": "Wide", "pos": [394300, -357050, 420], "yaw": 35, "pitch": -12, "fov": 55},
    {"at": 5.0, "name": "Close-up", "aim": {"actor": "flima", "at": "head"}, "offset": [90, -60, 0], "fov": 30,
     "move": {"to": {"offset": [70, -40, 0]}, "ease": "inOut", "dur": 4.0}},
    {"at": 9.0, "name": "Over", "aim": {"actor": "flima"}, "from": {"actor": "player", "shoulder": "right"}, "fov": 45}
  ],
  "lines": [{"at": 5.2, "who": "flima", "text": "Welcome to Maggie Island, outlander.", "voice": "Sound/Vo/mi/flima_01.mp3"}],
  "sound": [{"at": 0.0, "music": "Music/mi/tense.mp3", "duck": true}],
  "vfx": [{"id": "glow", "on": "flima", "bone": "Bip01 R Hand", "model": "meshes/e/magic_hand.nif", "dur": 3.0}],
  "screen": [{"at": 0.0, "fade": "in", "letterbox": "2.39"}, {"at": 14.0, "exposure": -0.3, "temperature": -20}],
  "end": {"do": [{"controls": "on"}, {"quest": "mi_welcome", "stage": 10}],
          "onSkip": "end", "onLoad": "end", "onMissingActor": "end"}
}
```

Agreed rules:

- **Units:** game units with Z up, world positions, seconds, degrees, vertical field of view.
- **`cell`:** a grid cell `[x, y]` outdoors (a cell is 8192 units: x from 8192·x to 8192·(x+1)), or an interior's
  name. The check warns when a mark or fixed shot isn't in the scene's cell.
- **Actors** are placed objects: `"ref": {"file", "index"}`, or `"id"` with `"pick": "nearest"`. A cue for a
  dead or missing actor counts as done.
- **Shots** are either fixed (`pos`, `yaw`, `pitch`, world coordinates) or aimed (`aim`, with `offset` or `from`),
  never both in one shot.
  - `offset` is in the aimed actor's own frame, so a shot stays the same whichever way the actor faces: the origin
    is at the actor's feet, turned with its facing; x is to its right, y straight ahead, z up, in game units.
  - `"at": "head"` raises the aim point to head height, from the race's height and the actor's scale.
  - So `"offset": [90, -60, 0]` is 90 units to her right and 60 behind her.
- **Voices** are full data paths (`Sound/Vo/...`), played with `core.sound.say` so the lips move.
- **`end`** always runs: on finishing, on skip, on loading a save mid-scene, and when an actor is missing.
- **Exposure and colour temperature** need a post-processing shader, which the Workshop will ship. With
  post-processing off in a player's settings, those cues are skipped.
- **Video:** a cue in `screen`, `{"at": 12.0, "movie": "mi_intro.bik"}`, plays a video from the game's `Video`
  folder (`Video/mi_intro.bik` works too; send the file with `/bridge/file` to `video/...`). The whole game, the
  scene player included, stands still for the video's length, then the scene carries on.
- **Unknown fields** are kept by both programs.
- The **trigger** (what starts the scene) isn't in the file. The user picks it in the Workshop.

## 5. The scene player (in the game)

When the user saves, the Workshop writes the scene player beside the mod with the rest of its Lua, in
`scripts/<lua_slug>/scene/`, listed in the mod's `.omwscripts`:

| File | What it does |
|---|---|
| `data.lua` | Every scene of the mod, as sent, with its trigger |
| `global.lua` | The clock; finds the actors and sets them on their marks; clips, voices, effects, the end; triggers; save and load |
| `player.lua` | The camera (fixed and aimed shots, moves), fade and letterbox, music, the player's controls, skip (Space or Enter) |
| `actor.lua` | Added to each actor while a scene plays: its AI held, its clips (`playQueued`), text-key effects |

**Playing a scene from your own Lua** (your live link's preview), as global events:

```lua
core.sendGlobalEvent('WsScene_Play', {scene = 'mi_welcome', t = 0})                       -- a scene of the mod
core.sendGlobalEvent('WsScene_Play', {scene = 'draft', mod = '<lua_slug>', data = sceneTable}) -- a scene not saved yet
core.sendGlobalEvent('WsScene_Pause', {})    core.sendGlobalEvent('WsScene_Resume', {})
core.sendGlobalEvent('WsScene_Seek', {t = 7.5})    core.sendGlobalEvent('WsScene_Stop', {})    core.sendGlobalEvent('WsScene_Skip', {})
```

- `data` is the scene as a Lua table, the same fields as the JSON. It plays only in the mod named by `mod`, so two
  mods with scenes never both play it.
- From a global script, the interface `I.WorkshopScenes_<lua_slug>` has `play(id, t, data)`, `pause()`,
  `resume()`, `seek(t)`, `stop()`, `state()` (`{scene, t, paused, length}`), `scenes()` and `version`.
- It sends `WsScene_Started {scene, mod}` and `WsScene_Ended {scene, mod, how}`. `how` is `finish`, `skip`,
  `stop`, `load`, `actor_missing` or `replaced`.
- It sends `CameraClaim {name = "scene:<lua_slug>"}` when it starts and `CameraRelease` when it ends. When another
  program sends `CameraClaim`, it stops moving the camera until that program's `CameraRelease`.

**What starts a scene** is picked by the user on the Workshop's Scripts page, under Scenes. A scene you send again
keeps the trigger the user picked. The choices are:
- only when asked (the events above),
- the player comes near a spot,
- a quest reaches a stage,
- a global variable is set to 1 (from a dialogue result or MWScript).

**How each field plays:**

| Field | In the game |
|---|---|
| `player` | `controls: "off"` turns off moving, looking, fighting, magic and the view keys until the end. `sheathe` puts the weapon away. `mark` teleports the player there. |
| `marks` | Actors with a `mark` are teleported there, turned to its yaw (degrees, as the game stores turns). |
| `actors` | `ref` is found by its plugin and index. `id` + `pick: "nearest"` takes the nearest loaded one. Its AI is held until the end. |
| `clips` | `group` is played as MWScript's PlayGroup does. `loop: true` repeats it; otherwise it plays once. `speed` is supported. A group the actor doesn't have is written to openmw.log and passed over. `keys: {"<text key>": "vfx:<id>"}` starts that effect at the key. |
| `shots` | The current shot is the last one whose `at` has passed. `fov` is vertical, in degrees. `move.to` takes `offset` (aimed shots) or `pos` (fixed shots), over `dur` seconds with `ease` (`in`, `out`, `inOut`, `linear`). |
| `lines` | Played with `core.sound.say` (lips move) when the voice file exists. Without one, the text is shown as a message. |
| `sound` | `music` is streamed. `sound` plays a sound file once. The music stops at the end. |
| `vfx` | Added with `animation.addVfx` on `bone`, and removed after `dur`. One with `at` starts at that time; one without waits for a text key. |
| `screen` | `fade: "in"` / `"out"` over `dur` (1 s if not given). `letterbox: "2.39"` (or another ratio) adds the bars. `movie: "<file>"` plays a video (PlayBink, through a small MWScript the Workshop adds to the mod: a global `ws<mod>_mv`, a start script `ws<mod>_mvs`, kept in step with the scenes and with Undo). A preview (`data`) plays only movies that a saved scene of the mod already uses. |
| `end.do` | Runs in order: `{"controls": "on"}`, `{"quest": id, "stage": n}` (adds the journal entry), `{"global": name, "value": v}`, `{"event": name, "data": {...}}` (a global event). |
| `end.onSkip` | `"end"` (the default) ends the scene on skip. `"none"` turns skip off. |
| `end.onMissingActor` | `"end"` (the default) ends the scene when an actor is missing or dies. |

**Tested in OpenMW 0.52** (an isolated game, Seyda Neen, a Workshop-made mod with three scenes):
- the area trigger, a play from an event, skip, a missing actor ending the scene, pause and seek through the
  interface, the end steps, and the camera claim and release all ran as written;
- the controls were off during each scene and back after it;
- a movie cue 2 s in stopped the game for the video's 16.4 s, then the scene went on and ended on time;
- a fixed shot with pitch -30 looked down at the right angle;
- an aimed close-up stayed on the actor's head (at most 4° behind while the camera moves, exact once it stops).

## 6. The two live links in one game

For a linked mod the Workshop starts the game, from its test copy when anything is unsaved, with your program's
game scripts added. Each link keeps its own script and files, under three rules:

- **Each link moves only the objects it made or was told about.** Your object changes go through the Workshop, so
  in a linked mod your link previews only: camera, animations, time and pause, teleport, scene play / pause / seek.
- **One owner of the camera at a time.** Before taking the camera, a link sends the global event
  `CameraClaim {name}`. The other lets go until `CameraRelease {name}`. The scene player claims the camera the
  same way.
- **No in-game edit mode for a linked mod.** The game never changes the mod.

## 7. Not built yet

- `exposure` and `temperature` (the post-processing shader), and `duck` on music. Until then they are passed over.
- Starting the game for a linked mod with your program's scripts added.
- `CameraClaim` / `CameraRelease` on the Workshop's own link.
- The post-processing shader for exposure and colour temperature.

## 8. A short example (Python)

```python
import json, os, time, urllib.error, urllib.request
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))

def find():
    p = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Morrowind Workshop', 'running.json')
    try:
        return json.load(open(p, encoding='utf-8'))['bridge']
    except (OSError, ValueError, KeyError):
        return None

def call(base, path, body=None, key=None):
    h = {'Content-Type': 'application/json'}
    if key:
        h['Authorization'] = 'Bearer ' + key
    req = urllib.request.Request(base.rstrip('/') + path, headers=h,
                                 data=None if body is None else json.dumps(body).encode(),
                                 method='GET' if body is None else 'POST')
    try:
        with OP.open(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(json.loads(e.read()).get('error') or str(e))

base = find()                                   # e.g. "http://127.0.0.1:57243/bridge/"
ask = call(base, '/hello', {'program': 'OpenMW Suite (Blender)', 'version': '4.1.0'})
while True:                                     # the user presses Allow in the Workshop
    st = call(base, '/hello?id=' + ask['id'])
    if st['state'] != 'waiting':
        break
    time.sleep(1.5)
key = st['key']                                 # keep it
print(call(base, '/status', key=key))
```
