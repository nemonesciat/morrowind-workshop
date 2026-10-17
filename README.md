# Morrowind Workshop

An easy, modern editor for making Morrowind mods with [OpenMW](https://openmw.org). Build and furnish
places in 2D and 3D, add people, items, books, dialogue and quests, and try it all in the running
game: the Workshop is linked to OpenMW, so changes appear in the game as you make them.

**Download the installer from Nexus Mods** (Morrowind → Utilities → Morrowind Workshop). This
repository is the source code it is built from.

## What it is made of

- **`app/`**: the Workshop itself, a small web server written in Python (standard library only, plus
  Anthropic's `anthropic` library for the optional AI assistant) and its page (`app/web`, plain
  HTML and JavaScript, with three.js and two fonts bundled in `app/web/vendor`).
  - `workshop.py` starts it. `database.py` and `esm.py` read OpenMW's settings, plugins and archives;
    `editing.py` and `project.py` keep your mod; the other files are the editors (dialogue,
    building, furnishing, regions, Lua scripts and so on).
  - `link_scripts/` are the OpenMW Lua scripts for the live link with the running game.
- **`packaging/`**: everything that turns `app/` into the Windows installer.
  - `build.py` makes `packaging/out/Morrowind Workshop Setup.exe`.
  - `launcher.cs`, `appwindow.cs`, `setup.cs` and `common.cs` are the two small Windows programs in it
    (the launcher, and the installer); they are compiled with the C# compiler that comes with Windows.
  - `README.md` is the readme that goes into the installer.

## Running it from the source

1. Install OpenMW and set it up with its Launcher, so it knows where Morrowind is.
2. Install [Python 3.13](https://www.python.org/downloads/) (64-bit).
3. Double-click **`Start Morrowind Workshop.bat`**. It installs the `anthropic` library the first
   time and opens the Workshop in your browser.

## Building the installer

See [BUILDING.md](BUILDING.md).

## AI disclosure

The code in this repository was written with the help of Claude, an AI by Anthropic, under the
author's direction and testing. The Workshop contains no AI-generated game assets. Its optional
assistant uses Claude through the user's own Anthropic API key.

## Licence

The Workshop's own code is © 2026 Nemo and licensed under
[Creative Commons Attribution-NonCommercial 4.0](LICENSE.cc-by-nc-4.0.txt): you may share and
change it, with credit, but not for commercial purposes. See [LICENSE](LICENSE).

The bundled third-party files keep their own licences: three.js (MIT) and the Cinzel and Inter fonts
(SIL Open Font License 1.1), in `app/web/vendor` with their licence texts in
`app/web/vendor/licenses`. The installer also includes Python (PSF License) and the `anthropic`
library and its dependencies (MIT, BSD, Apache 2.0); the built installer lists them all in
`THIRD_PARTY_NOTICES.txt`.

Not made by or affiliated with Bethesda Softworks or the OpenMW project. Contains no Morrowind files.
