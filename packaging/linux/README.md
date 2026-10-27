# Morrowind Workshop for Linux

An easy, modern editor for making Morrowind mods with OpenMW. Build and furnish places, add people,
items, books, dialogue and quests, and try them in the running game, where your changes appear
as you make them.

Linux support is new. If something doesn't work, **? Help → Report a problem** makes a report to send.

## What you need

- **Python 3.10 or newer** (`python3`). Most distributions have it already.
- **[OpenMW](https://openmw.org/downloads/) 0.49 or newer**, set up once with its Launcher (it asks where
  Morrowind is installed). Your distribution's package, the Flatpak (`org.openmw.OpenMW`) and openmw.org's
  own download all work.
- **Morrowind itself** (for example from Steam or GOG).
- Recommended: **Chromium, Google Chrome, Brave, Edge or Vivaldi**, for the Workshop's own window. Without one
  it opens in your usual web browser.
- Recommended: **zenity** (or **kdialog** on KDE), for the "Choose a folder" and "Open a file" windows.

## Installing

1. Unpack the download somewhere in your home folder, for example `~/Morrowind Workshop`. The Workshop
   keeps your projects and settings in that folder, so it must be a place you can save files.
2. Start **morrowind-workshop** in that folder (double-click it, or `./morrowind-workshop` in a terminal).
   It opens in its own window and reads your game, which takes a minute the first time.
3. From then on it is in your desktop's app menu as **Morrowind Workshop**
   (`./morrowind-workshop --no-menu` takes it out again).

To update, unpack the new version over the old one. To remove it, run `./morrowind-workshop --no-menu`
and delete the folder.

Closing the Workshop's window quits it. When it opened in your usual browser instead, quit it with
`./morrowind-workshop --quit` (or Ctrl+C in the terminal you started it from).

## The AI assistant (optional)

The ✦ Assistant can build and change things from a plain request. It uses Claude, Anthropic's AI,
with **your own Anthropic API key**, and each request is billed to your Anthropic account. It needs one
Python package that isn't part of Python itself. To set it up, run this once in the Workshop's folder
(it needs the internet, and makes a Python environment of the Workshop's own in `python-env`; your
system's Python is not changed):

    ./morrowind-workshop --install-ai

On Debian and Ubuntu this needs the `python3-venv` package (`sudo apt install python3-venv`).
Then add your key in **? Help → Settings**. Everything else works without it.

## Where things are

- Your mods: OpenMW's data folder, `~/.local/share/openmw/data` (the Flatpak's is
  `~/.var/app/org.openmw.OpenMW/data/openmw/data`), unless your openmw.cfg says otherwise.
- OpenMW's settings and log: `~/.config/openmw` (the Flatpak's: `~/.var/app/org.openmw.OpenMW/config/openmw`).
- The Workshop's projects, backups and settings: the Workshop's own folder.
- The Workshop's log: `workshop.log` in its folder.

## Good to know

- If OpenMW isn't found, use **▶ OpenMW → Choose OpenMW's folder** and pick the folder with the `openmw`
  program in it (for a system install that is usually `/usr/bin` or `/usr/games`).
- **The Flatpak:** the game must be able to read the Workshop's folder for the live link. If the game starts
  but shows **○ Game not linked**, allow it once:
  `flatpak override --user --filesystem="$HOME/Morrowind Workshop" org.openmw.OpenMW`
  (with your own folder's path).
- The live link only works when the game is started from the Workshop.
- Deleted mods go to your desktop's bin, where they can be restored.
- Not made by or affiliated with Bethesda Softworks or the OpenMW project. The Workshop contains no
  Morrowind files; it reads the ones you own. Third-party software and its licences are listed in
  THIRD_PARTY_NOTICES.txt and under ? Help → About & licences.
