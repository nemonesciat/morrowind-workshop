# Morrowind Workshop

An easy, modern editor for making Morrowind mods with OpenMW. Build and furnish places, add people,
items, books, dialogue and quests, and try them in the running game, where your changes appear
as you make them.

## What you need

- Windows 10 or 11 (64-bit)
- [OpenMW](https://openmw.org/downloads/) 0.49 or newer, set up once with its Launcher (it asks where Morrowind is installed)
- Morrowind itself (for example from Steam or GOG)

Everything else comes with the Workshop: no Python or other downloads, and no administrator rights.

## Installing

1. Run **Morrowind Workshop Setup.exe**. Windows may say "Windows protected your PC", because the
   installer isn't signed by a company: click **More info**, then **Run anyway**.
2. Choose where to install (the suggested folder is fine) and press **Install**.
3. Start it from the Start menu or the desktop. It opens in its own window and reads your game,
   which takes a minute the first time.

Running the setup again later updates the Workshop and keeps your projects and settings.
To remove it, use Windows' **Installed apps** list; it asks whether to keep your projects.

**Rather not run an installer?** Download the **portable** zip instead, unzip it somewhere you can
save files (Documents or the desktop, not Program Files), and start **Morrowind Workshop.exe** in the
unzipped folder. Your projects and settings are kept in that folder. To update, unzip the new version
over it; to remove it, delete the folder.

## First steps

The **Getting started** page opens the first time, and is always under **? Help** at the top.

1. **＋ Start a mod** at the top, and give it a name. Everything you make or change is saved into
   your mod straight away; your game files are never changed. **Undo** (Ctrl+Z) takes back a change.
2. Find a place on the **World map**, in 2D or 3D, and drag things in from the sidebar, or use
   **Create** for new people, items, books, spells or a whole interior built from pieces.
3. **▶ OpenMW → Start the game** (or **Play here** on the map) starts OpenMW with your mod and the
   live link: changes in the Workshop appear in the game within a second.
4. When it's ready, **My mod → Get ready to share** checks it, writes a readme and packs a zip.

## The AI assistant (optional)

The ✦ Assistant can build and change things from a plain request. It uses Claude, Anthropic's AI,
with **your own Anthropic API key**, and each request is billed to your Anthropic account (usually a
few cents, up to about half a dollar for a big job). What you ask and details about what it works
on are sent to Anthropic. Everything else works without it.

## Your work is safe

- Your mods live in the Workshop's **projects** folder; the mod file the game loads goes into
  OpenMW's data folder.
- The Workshop keeps **automatic backups** of each mod and can restore any of them
  (? Help → Settings → Backups).
- Changing your load order in the Workshop makes a backup of OpenMW's settings first.

## Problems?

**? Help → Report a problem** makes a report with the details needed to look into it (versions,
setup and the end of the logs; your Windows user name and API key are left out). Copy it into the
place you got the Workshop from.

## Good to know

- The live link only works when the game is started from the Workshop. A game started from
  OpenMW's own Launcher shows **○ Game not linked** at the top.
- Brand-new places and records appear in the game after it is restarted; changes to existing
  things appear straight away.
- Not made by or affiliated with Bethesda Softworks or the OpenMW project. The Workshop contains no
  Morrowind files; it reads the ones you own. Third-party software and its licences are listed in
  THIRD_PARTY_NOTICES.txt and under ? Help → About & licences.
