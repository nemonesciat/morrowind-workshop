// ---------- Guided tours: the Home page's cards, one for each thing the Workshop does ----------
// (the user, 2026-11-26: "turn all of those into guided tutorials on various things that you guide the user through.
// each card has a feature like those first two suggest") Each tour is a few pointers over the real buttons, one at a
// time (coach.js runs them): a step goes on by itself once it's done, or with Next where there's nothing to wait for,
// and nothing is done for you. A finished tour gets a tick on its card.
const TOUR_DONE_KEY = 'ws-tours-done';
function tourDone(){ try { return JSON.parse(localStorage.getItem(TOUR_DONE_KEY) || '[]'); } catch (e){ return []; } }
function tourMark(id){ if (!id) return; const d = tourDone(); if (!d.includes(id)){ d.push(id); try { localStorage.setItem(TOUR_DONE_KEY, JSON.stringify(d)); } catch (e){} } }

// ----- steps many tours share
const T_MOD = {skip: () => S.summary && S.summary.project, at: () => $('#projpill'), title: 'First, start a mod',
  text: 'Click here and give it a name. Everything you make goes into it; Save (Ctrl+S) writes it, Undo (Ctrl+Z) takes anything back.',
  done: () => S.summary && S.summary.project};
const T_WORLD = {at: () => $('nav [data-view="world"]'), title: 'Open the World map', text: 'Places in 2D or 3D, where you build.',
  skip: () => pageOn('world'), done: () => pageOn('world')};
const T_PANEL = () => { if (typeof PNL !== 'undefined' && PNL.spaces.world) PNL.show('world', 'place'); };
const T_PLACE = (text, ok) => ({at: () => $('#w-goto'), title: 'Go to a place', text, above: false, start: T_PANEL,
  skip: () => pageOn('world') && W.key && W.cells[W.key] && (!ok || ok()), done: () => pageOn('world') && W.key && W.cells[W.key] && (!ok || ok())});
const T_PEOPLE = () => Object.values(W.cells || {}).some(c => (c.refs || []).some(r => r.type === 'NPC_'));
const T_3D = {at: () => $('[data-view3d="1"]'), title: 'See it in 3D', text: 'The 3D view, as in the game.', skip: () => V3.on, done: () => V3.on};
const T_CREATE = (ck, title, text, opened) => [
  {at: () => $('nav [data-view="createv"]'), title: 'Open Create', text: 'Quick starts for everything you can make.', skip: () => pageOn('createv'), done: () => pageOn('createv')},
  {at: () => $(`[data-ck="${ck}"]`), title, text, skip: () => typeof CR !== 'undefined' && CR.kind === ck && pageOn('createv'),
   done: opened || (() => typeof CR !== 'undefined' && CR.kind === ck)}];
const T_V3 = name => () => document.querySelector(`#v3tools [data-v3="${name}"]`);
// the form's own button that makes it (Create spell, Make it, Forge…)
const T_GO = () => $('#cr-go') || [...document.querySelectorAll('#createv button.primary')].find(b => b.offsetParent && !b.dataset.ck);
const T_OL = sel => () => { const b = typeof PNL !== 'undefined' && PNL.body('world', 'olist'); return b && b.querySelector(sel); };

const TOURS = [
  // ----- start here
  {id: 'house', group: 'Start here', icon: '🏠', min: 2, title: 'Build your first house',
   text: 'Lay out a few rooms, let the Workshop build and furnish them from the game\'s own pieces, then look round it in 3D.', steps: () => COACH_STEPS},
  {id: 'around', group: 'Start here', icon: '🧭', min: 3, title: 'Getting around',
   text: 'Fly the 3D view, snap to the top or an isometric corner, take the whole window, and open the card that everything has.',
   steps: () => [T_WORLD, T_PLACE('Type a place\'s name, Balmora say, and pick it.'), T_3D,
     {at: null, title: 'Look round', text: 'Right-drag to look; W A S D to fly, Q and E down and up; the wheel goes forward and back, faster the higher you are. Double-tap a key to hurry.', next: true},
     {at: T_V3('view'), title: 'Camera views', text: '👁 View ▾ holds Top and the four isometric corners, Flat (no perspective) and Fog. The number pad does it too: 7, 1 and 5.', done: () => V3.viewOpen},
     {at: () => document.querySelector('[data-v3="camsnap"][data-k="ne"]'), title: 'An isometric view', text: 'Click a corner: the view looks down at it from there. Again goes round to the next.', done: () => !!V3.camSnap},
     {at: () => $('#w-full'), title: 'Full view', text: '⛶ gives the view the whole window; the panels fold away. The small tabs at the edges bring one side back.', done: () => PNL.spaces.world && PNL.spaces.world.full},
     {at: () => $('#w-full'), title: 'And back', text: '⛶ again brings everything back.', done: () => PNL.spaces.world && !PNL.spaces.world.full},
     {at: null, title: 'Everything has a card', text: 'Double-click anything in the view: its card opens, with its details, what it does and how it looks.',
      done: () => PCD.kind && $('#pc-dock') && $('#pc-dock').style.display !== 'none'},
     {at: () => $('#pc-tabs'), title: 'Its tabs', text: 'A door adds where it leads, a container what it holds, a person what they say and how they spend the week. ⧉ puts the card in a window.', last: true}]},
  // ----- build places
  {id: 'lists', group: 'Build places', icon: '📋', min: 3, title: 'Place from lists',
   text: 'Every kind of thing in a list: pick one, click it into the view as many times as you like, then nudge it into place.',
   steps: () => [T_MOD, T_WORLD, T_PLACE('A place to build in. An interior is the easiest.'), T_3D,
     {at: () => $('#w-panels'), title: 'Open an Object list', text: '▤ Panels › 📋 Object list: everything you can place, one kind at a time.', done: () => PNL.isOpen('world', 'olist')},
     {at: T_OL('.ol-types'), title: 'Pick a kind', text: 'Static, Door, Light, NPC… Click a column to sort it; Filter narrows it down.', next: true},
     {at: T_OL('[data-olstamp]'), title: '✚ Place', text: 'Turn it on: one click on a row then picks it up.', done: () => STAMP.on},
     {at: T_OL('[data-olr="0"]'), title: 'Pick something', text: 'Click a row. A see-through copy follows the mouse.', done: () => W.mode === 'place'},
     {at: null, title: 'Put it down', text: 'Click in the view to place one, again for more. The wheel turns it; X or Y + wheel tilts it, Alt + wheel sizes it. Esc stops.', done: () => W.mode !== 'place'},
     {at: null, title: 'Fine-tune it', text: 'With it selected, the arrow keys nudge it along the grid, Page Up and Page Down raise and lower it, , and . turn it. Shift goes further; Ctrl+Z undoes.', last: true}]},
  {id: 'land', group: 'Build places', icon: '🌄', min: 4, title: 'Shape the land',
   text: 'Raise hills and dig hollows, paint the ground the region\'s way or with a picture of your own, and tint it.',
   steps: () => [T_MOD, T_WORLD, T_PLACE('Somewhere outdoors with open ground: type -3, -9, say.', () => W.ext), T_3D,
     {at: T_V3('land'), title: '⛰ Ground', text: 'The ground tools open.', done: () => V3.landOpen},
     {at: () => $('[data-lt="raise"]'), title: 'Raise and lower', text: 'Pick ▲ Raise, then drag on the ground (Ctrl lowers). Size and Strength are below; Undo takes a stroke back.', next: true},
     {at: () => $('[data-lt="paint"]'), title: 'Paint', text: 'Pick a texture and drag. ✨ Auto paints it the way the region\'s own land is; ＋ New makes a ground texture from any picture.', done: () => V3.land && V3.land.tool === 'paint'},
     {at: () => $('[data-lt="tint"]'), title: 'Tint', text: 'The ground\'s own colour. Six boxes keep colours with your mod: click an empty one to keep the colour, a filled one to use it.', done: () => V3.land && V3.land.tool === 'tint'},
     {at: null, title: 'Bigger land', text: 'The Land panel (left) makes whole coasts, hills and valleys at once, with places on them.', last: true}]},
  {id: 'dungeon', group: 'Build places', icon: '⚙', min: 3, title: 'Make a dungeon',
   text: 'A Dwemer ruin, a cave or a tomb laid out and dressed in a minute, then checked and walked round.',
   steps: () => [T_MOD, ...T_CREATE('ruin', 'Dungeon', 'A ruin, a cave, a tomb…'),
     {at: () => $('#cr-name'), title: 'Name it, pick its kind', text: 'A name, then the kind and its shape (winding, branching, a maze), and how full it is of creatures and loot.', above: true, next: true},
     {at: T_GO, title: 'Make it', text: 'It is laid out and dressed, then opens on the World map.', start: () => { COACH.key = W.key; },
      done: () => pageOn('world') && W.key && W.key !== COACH.key && W.cells[W.key]},
     {at: () => $('#w-check'), title: 'Check it', text: '🩺 Check place lists anything that looks wrong, each with a marker and a fix.', next: true},
     {at: () => $('[data-view3d="1"]'), title: 'Walk round it', text: 'In 3D, as in the game.', done: () => V3.on},
     {at: () => $('#w-play'), title: 'Try it in the game', text: 'Play here starts OpenMW in it with a test character.', last: true}]},
  {id: 'furnish', group: 'Build places', icon: '🪑', min: 3, title: 'Furnish and check a room',
   text: 'Fill rooms by what they are for, add the traces of the people who live there, and find what is wrong.',
   steps: () => [T_MOD, T_WORLD, T_PLACE('An interior: a house of your own, or any. Type its name.', () => W.info && W.info.interior),
     {start: T_PANEL, at: () => $('#w-furnish'), title: 'Auto-furnish', text: 'Fills every room by what it is for, the game\'s way. It asks which rooms first.', next: true},
     {start: T_PANEL, at: () => $('#w-lived'), title: 'Lived in', text: 'What people leave round their beds, fires, tables and work spots.', next: true},
     {start: T_PANEL, at: () => $('#w-check'), title: 'Check place', text: 'Floating things, chairs with nothing to sit at, a home with no bed… each with a fix.', next: true},
     {start: T_PANEL, at: () => $('#w-fixit'), title: 'Find gaps', text: 'For places built from room pieces: black gaps and doorways that lead nowhere, and their fixes.', last: true}]},
  {id: 'town', group: 'Build places', icon: '🏘', min: 5, title: 'Make a town',
   text: 'Mark the ground, draw where the town goes, pick its people\'s style, and the Workshop lays out streets, houses and doors.',
   steps: () => [T_MOD, T_WORLD, T_PLACE('Outdoors, on open ground away from other towns. Type a cell, 10, -6 say.', () => W.ext),
     {start: () => PNL.show('world', 'land'), at: () => $('#lst-mark'), title: 'Mark the ground', text: 'In the Land panel: 🖌 Mark, then drag over the map\'s cells where the town will stand, a few of them.',
      done: () => typeof LM !== 'undefined' && LM.data && LM.data.marks && LM.data.marks.length > 0},
     {start: () => PNL.show('world', 'land'), at: () => $('[data-stage="1"]'), title: '2 Places', text: 'Open the second stage, where towns, castles, roads and farms go.',
      skip: () => typeof LM !== 'undefined' && LM.stageOpen === 1, done: () => typeof LM !== 'undefined' && LM.stageOpen === 1},
     {start: () => PNL.show('world', 'land'), at: () => $('[data-add="town"]'), title: 'A town', text: 'Town, then click round where it goes on the map (double-click closes it). Its ⚙ picks the people\'s style, its size and its wall.',
      done: () => typeof lstLayers === 'function' && lstLayers(1).some(([L]) => L.kind === 'town' && L.pts && L.pts.length >= 3)},
     {at: () => $('#lst-make1'), title: 'Make places', text: 'Streets, houses with their doors, wells and stalls go up; a minute or two. Then Keep it, Try again, or Drop it.',
      done: () => typeof lstStage === 'function' && !!lstStage()},
     {at: () => $('[data-view3d="1"]'), title: 'Walk its streets', text: 'In 3D, as in the game.', done: () => V3.on},
     {at: null, title: 'Inside', text: '3 Insides and people furnishes its houses and gives them households; double-click a door to go in.', last: true}]},
  {id: 'doors', group: 'Build places', icon: '🚪', min: 4, title: 'Doors and secret ways',
   text: 'Make a door lead where you want and set where you arrive, then turn a wall or a bookcase into a hidden door.',
   steps: () => [T_MOD, T_WORLD, T_PLACE('An interior with a door: a house of your own, or any. Type its name.', () => W.info && W.info.interior && (W.info.refs || []).some(r => r.type === 'DOOR')), T_3D,
     {at: null, title: 'A door\'s card', text: 'Double-click a door.', done: () => PCD.kind === 'thing' && PCD.d && PCD.d.type === 'DOOR'},
     {at: () => document.querySelector('#pc-tabs [data-pctab="door"]'), title: '🚪 Leads to', text: 'Where it goes.', done: () => PCD.tab === 'door'},
     {at: () => [...document.querySelectorAll('#pc-body [data-tcact]')].find(b => /lead somewhere/i.test(b.textContent)), title: 'Make it lead somewhere',
      text: 'Pick the place it opens into, then click the spot where you arrive. The door there leads back.', next: true},
     {at: null, title: 'A secret way', text: 'Double-click a wall, a bookcase or a tapestry.', done: () => PCD.kind === 'thing' && PCD.d && !['DOOR', 'NPC_', 'CREA'].includes(PCD.d.type)},
     {at: () => document.querySelector('#pc-tabs [data-pctab="does"]'), title: '⚡ Does', text: 'What it does.', done: () => PCD.tab === 'does'},
     {at: () => [...document.querySelectorAll('#pc-body [data-tcact]')].find(b => /hidden door|door to/i.test(b.textContent)), title: 'A hidden door',
      text: 'It keeps its looks but opens now: make it lead somewhere, or let it swing on its edge. Rotating and sliding panels are here too.', last: true}]},
  // ----- people and stories
  {id: 'person', group: 'People and stories', icon: '🧍', min: 4, title: 'A person\'s card',
   text: 'Give someone their own lines, a week of their own, and what they wear, sell and do.',
   steps: () => [T_MOD, T_WORLD, T_PLACE('A place with people: Seyda Neen, say.', T_PEOPLE), T_3D,
     {at: null, title: 'Right-click a person', text: '› 👤 About… opens their card under the view.', done: () => PCD.kind === 'npc'},
     {at: () => document.querySelector('#pc-tabs [data-pctab="talk"]'), title: '💬 Talk', text: 'What they say now, every topic with where the line comes from; Say something gives them a line of their own.', next: true},
     {at: () => document.querySelector('#pc-tabs [data-pctab="day"]'), title: '📅 Their week', text: 'Open Day.', done: () => PCD.tab === 'day'},
     {at: () => $('#pc-wadd'), title: '＋ Block here', text: 'A block at the spot in the middle of the view, 8:00 to 17:00 every day. Change its days and hours; another place works too.',
      done: () => PCD.week && PCD.week.blocks && PCD.week.blocks.length},
     {at: () => document.querySelector('#pc-tabs [data-pctab="gear"]'), title: 'And the rest', text: '🎒 what they wear and carry, 🪙 what they trade, 🧭 where they take travellers, 🧩 jobs they give.', next: true},
     {at: () => $('#pc-float'), title: '⧉ In a window', text: 'The card in a window you can move, size or dock.', last: true}]},
  {id: 'quest', group: 'People and stories', icon: '🧩', min: 5, title: 'A quest on the map',
   text: 'Start a quest from a person, a thing or the ground, then add each step where it happens.',
   steps: () => [T_MOD, T_WORLD, T_PLACE('A place with people: Seyda Neen, say.', T_PEOPLE), T_3D,
     {at: T_V3('quests'), title: '🧩 Quests', text: 'The quest maker opens under the view.', done: () => typeof QM !== 'undefined' && QM.dock},
     {at: null, title: 'Start a quest', text: 'Right-click a person › 🧩 Quest given by them…: name it, write the first journal line.', next: true},
     {at: null, title: 'What happens next', text: 'Right-click the next person, a thing or the ground: talk to, bring to, find, read, kill, reach a spot… Each step is one Undo.', next: true},
     {at: null, title: 'The route', text: 'Numbered pins and rings show it in 3D; ⚠ marks a stage nothing leads to. Try it with Play here.', last: true}]},
  {id: 'scene', group: 'People and stories', icon: '🎬', min: 5, title: 'Your first cutscene',
   text: 'Someone greets the player: put them on their spots, frame the shots, write the line, preview it, then try it in the game.',
   steps: () => (typeof SCN_TOUR !== 'undefined' ? SCN_TOUR : [])},
  {id: 'play', group: 'People and stories', icon: '🎮', min: 3, title: 'Test in the game',
   text: 'Start OpenMW right where you are, see your changes appear in the game as you make them, and test with what you need.',
   steps: () => [T_MOD, T_WORLD, T_PLACE('Any place you\'ve made or changed.'),
     {start: T_PANEL, at: () => $('#w-play'), title: '▶ Play here', text: 'Starts OpenMW here with a test character, your whole load order and your mod. Your own saves are untouched.', next: true},
     {at: () => $('#linkdot') && $('#linkdot').offsetParent ? $('#linkdot') : $('.hdr-right'), title: 'The live link', text: 'While the game runs from the Workshop, the top shows ● Game linked: what you change here shows in the game within a second.', next: true},
     {start: T_PANEL, at: () => $('#w-playspot'), title: 'Pick a spot', text: 'Click a spot on the map to start there, or, with the game running, to go there.', next: true},
     {start: T_PANEL, at: () => $('#q-setup'), title: 'Test setups', text: 'Items, spells, quest stages or variables given on top as the game starts; 👤 Play as starts as one of your own characters, from their last save.', last: true}]},
  // ----- items and magic
  {id: 'forge', group: 'Items and magic', icon: '⚒', min: 3, title: 'Forge weapons and armour',
   text: 'One piece or a whole set, with the game\'s own numbers for the material, then out into the world.',
   steps: () => [T_MOD, ...T_CREATE('forge', 'Forge a weapon or armour', 'The Forge opens.', () => typeof FG !== 'undefined' && FG.bg && FG.bg.isConnected),
     {at: () => $('.fg-tabs'), title: 'A piece, or a whole set', text: 'Then what it is, the material and the style. The stats come from the game\'s own for that material.', next: true},
     {at: () => $('#fg-go'), title: 'Forge it', text: 'Made into your mod, one Undo.', next: true},
     {at: () => $('[data-fgtab="world"]'), title: 'Into the world', text: 'Forged pieces can go into the loot lists, onto the people who carry such things and into merchants\' wares.', last: true}]},
  {id: 'spell', group: 'Items and magic', icon: '✨', min: 3, title: 'A spell of your own',
   text: 'Its effects and cost, then given to whoever should know it.',
   steps: () => [T_MOD, ...T_CREATE('spell', 'New spell', 'A spell, an ability, a power or a disease.'),
     {at: () => $('#cr-name'), title: 'Name it', text: 'Then add its effects below; the cost is worked out the game\'s way.', above: true, next: true},
     {at: T_GO, title: 'Create it', text: 'Into your mod, one Undo. "Give it to" teaches it to someone at once.', next: true},
     {at: () => $('[data-ck="givespell"]'), title: 'Teach it to people', text: 'Give spells to people: to everyone of a class, a faction or a race.', last: true}]},
  {id: 'skill', group: 'Items and magic', icon: '📈', min: 2, title: 'A new skill',
   text: 'A skill of your own (OpenMW 0.52), raised by what the player does, with books that teach it.',
   steps: () => [T_MOD, ...T_CREATE('skill', 'New skill', 'Start from an example, or from nothing.', () => typeof RC !== 'undefined' && RC.kind === 'skills'),
     {at: () => $('#rc-name'), title: 'Name it', text: 'Its attribute, its specialisation, and what raises it.', next: true},
     {at: null, title: 'Make it', text: 'Make the skill, below. It shows in the game with the others.', last: true}]},
  // ----- scripting
  {id: 'when', group: 'Scripting', icon: '⚡', min: 3, title: 'When… then…',
   text: 'Make the world react: when the player uses, opens or reads something, or comes somewhere, then something happens. No scripting.',
   steps: () => [T_MOD, ...T_CREATE('happen', 'When… then…', 'Events in plain words.', () => typeof RC !== 'undefined' && RC.kind === 'happens'),
     {at: () => $('#myrec'), title: 'When, and then', text: 'Pick what the player does and to what, then what happens: a message, an item, a sound, a quest stage, a scene… Start from an example if you like.', next: true},
     {at: null, title: 'Right on the thing', text: 'In the world, a thing\'s card has ⚡ Does with "When used / opened / read…" for that very thing.', last: true}]},
  // ----- share
  {id: 'share', group: 'Share', icon: '📦', min: 2, title: 'Check and pack your mod',
   text: 'Check it, write its readme and pack a zip to upload.',
   steps: () => [T_MOD, {at: () => $('nav [data-view="mymod"]'), title: 'My mod', text: 'What your mod holds.', done: () => pageOn('mymod')},
     {at: () => $('#mm-release'), title: 'Get ready to share', text: 'Checks the mod, lists what it needs, writes a readme and packs a zip.', done: () => pageOn('release')},
     {at: null, title: 'A clean test', text: 'Start a clean test plays it with only the base game and what your mod needs, as others will.', last: true}]},
];
const TOUR_GROUPS = ['Start here', 'Build places', 'People and stories', 'Items and magic', 'Scripting', 'Share'];
// (the tours Home shows, as the user picked them, 2026-11-26; every tour is in Help › All tours…)
const TOUR_HOME = ['house', 'around', 'lists', 'land', 'dungeon', 'furnish', 'town', 'doors', 'person', 'quest', 'scene', 'play', 'share'];

function tourRun(id){
  const t = TOURS.find(x => x.id === id); if (!t) return;
  const steps = t.steps();
  if (!steps || !steps.length) return toast('This tour isn\'t here.', true);
  coachHouse(steps, id);
}

// the Home page's tour cards, by group, each with its time and a tick when done
// a checklist (the user's pick over cards, 2026-11-26): a box ticked when the tour's last step is reached
function tourHubHtml(all){
  const done = tourDone();
  return TOUR_GROUPS.map(g => {
    const ts = TOURS.filter(t => t.group === g && (all || TOUR_HOME.includes(t.id)));
    if (!ts.length) return '';
    return `<h2 class="tour-h">${esc(g)} <span class="msg">${ts.filter(t => done.includes(t.id)).length} of ${ts.length} done</span></h2>
      <div class="tourlist">${ts.map(t => { const d = done.includes(t.id); return `<button class="tourrow ${d ? 'tour-done' : ''}" data-tour="${t.id}" title="${d ? 'Done. Click to take it again.' : 'Start this tour'}">
        <span class="tr-box">${d ? '✓' : ''}</span><span class="ic">${t.icon}</span><b>${esc(t.title)}</b><span class="msg">${esc(t.text)}</span>
        <span class="tr-k">${t.min} min</span></button>`; }).join('')}</div>`;
  }).join('');
}
function tourHubBind(root, after){ root.querySelectorAll('[data-tour]').forEach(b => b.onclick = () => { if (after) after(); tourRun(b.dataset.tour); }); }
// Help › All tours…: every tour, the ones not on Home too
function toursModal(){
  const bg = document.createElement('div'); bg.className = 'modal-bg';
  bg.innerHTML = `<div class="modal" style="width:min(1000px,94vw);max-height:88vh;overflow:auto"><h2>All tours</h2>
    <p class="msg">Each points at the real buttons, one at a time; nothing is done for you. A tick marks the ones you've finished.</p>
    ${tourHubHtml(true)}<div class="foot"><button class="btn" data-close>Close</button></div></div>`;
  document.body.appendChild(bg);
  bg.querySelector('[data-close]').onclick = () => bg.remove();
  bg.addEventListener('click', e => { if (e.target === bg) bg.remove(); });
  tourHubBind(bg, () => bg.remove());
}
