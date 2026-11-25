// ---------- Help: getting started guide, settings, problem report, about & licences ----------
// The guide opens by itself the first time the Workshop runs (Settings can turn that off).

// ----- the Help menu at the top
// (one top-bar menu open at a time: opening one closes the others)
function topMenusClose(except){ for (const id of ['helpmenu', 'omwmenu', 'learnmenu', 'filemenu']){ const m = $('#' + id); if (m && id !== except) m.style.display = 'none'; } }
$('#helpbtn').onclick = e => { e.stopPropagation(); topMenusClose('helpmenu'); const m = $('#helpmenu'); m.style.display = m.style.display === 'block' ? 'none' : 'block'; };
document.addEventListener('click', e => { if (!e.target.closest('#helpmenu')) $('#helpmenu').style.display = 'none'; });
$('#helpmenu').addEventListener('click', e => {
  const b = e.target.closest('[data-help]'); if (!b) return;
  $('#helpmenu').style.display = 'none';
  const a = b.dataset.help;
  if (a === 'guide' || a === 'settings') showView(a);
  else if (a === 'report') reportModal();
  else if (a === 'messages') recentMessages();
  else if (a === 'about') aboutModal();
  else if (a === 'learning') docModal('how-the-workshop-learns.md');
  else if (a === 'guides') guidesModal();
});

// ----- guides: how to do things, to read when you want to (no walkthrough). Each is a paper in web/docs, opened
// from Help > Guides or from a "?" beside the tool it explains, at its section
const GUIDES = [
  {file: 'getting-around.md', title: 'Getting around', what: 'Your mod, the pages, finding any record in Browse, panels, shortcuts, settings, backups.'},
  {file: 'the-world-map.md', title: 'The World map', what: 'Opening places, moving about in 2D and 3D, selecting, placing and changing things, the panels.'},
  {file: 'building-interiors.md', title: 'Building interiors', what: 'The room planner, styles and stairs, adding rooms, Extend, interiors for buildings, the prefab workbench, the Style palette, hidden doors.'},
  {file: 'furnishing-and-checking.md', title: 'Furnishing and checking', what: 'Auto-furnish, one room at a time, shelves and books, lighting and fog, Find gaps, Fix here, Check this place.'},
  {file: 'dungeons-and-ruins.md', title: 'Dungeons and ruins', what: 'Caves, Dwemer ruins, Velothi tombs and Daedric shrines, grown and stocked the game\'s way.'},
  {file: 'shaping-the-land.md', title: 'Shaping the land', what: 'The Ground brush, land shaping over many cells (coasts, ridges, rivers, rock), height maps, and recipes.'},
  {file: 'sky-regions-and-weather.md', title: 'Sky, regions and weather', what: 'Regions and painting them, weather and sounds, previewing the sky and time of day.'},
  {file: 'people-and-creatures.md', title: 'People and creatures', what: 'New people, the Characters page, Populate a place, leveled lists, teaching spells.'},
  {file: 'dialogue-and-quests.md', title: 'Dialogue and quests', what: 'How the game picks a line, conditions, the conversation builder and map, quests, testing.'},
  {file: 'items-spells-and-the-forge.md', title: 'Items, spells and the Forge', what: 'New items and books, the item editor, weapons and armour from the Forge and into the world, spells, your own magic effects.'},
  {file: 'openmw-052.md', title: 'What OpenMW 0.52 adds', what: 'Your own skills, attributes, weathers, traps, loot rules and list additions; magic effects that burst, strike, glow and act where the bolt strikes.'},
  {file: 'library-and-assets.md', title: 'Library and assets', what: 'Your own models, pictures and sounds, retexturing, Blender, animations, packs.'},
  {file: 'scripts-and-game-rules.md', title: 'Scripts and game rules', what: 'MWScript and Lua, global variables, game settings, factions, classes, races and the rest.'},
  {file: 'coding-with-ai.md', title: 'Coding with AI', what: 'Lua, effects and dialogue written by a model on your PC, and coding agents (Claude Code, Codex…) on your mod.'},
  {file: 'playing-and-testing.md', title: 'Playing and testing', what: 'Play here, playing as your own character, test setups, the live link, the OpenMW menu.'},
  {file: 'sharing-your-mod.md', title: 'Sharing your mod', what: 'My mod, Get ready to share, Health check, Load order, merging, .esp files, building together, backups.'},
  {file: 'how-the-workshop-learns.md', title: 'How the Workshop learns', what: 'Where its building and decorating know-how comes from: your own game, on your PC.'},
];
const GUIDE_TEXT = {};
async function guideText(file){
  if (!(file in GUIDE_TEXT)){ try { const r = await fetch('/web/docs/' + file, {cache: 'no-store'}); GUIDE_TEXT[file] = r.ok ? await r.text() : ''; } catch (e){ GUIDE_TEXT[file] = ''; } }
  return GUIDE_TEXT[file];
}
function guidesModal(){
  const bg = document.createElement('div'); bg.className = 'modal-bg';
  bg.innerHTML = `<div class="modal" style="width:min(560px,95vw)"><h3 style="margin-top:0">Guides</h3>
    <input class="inp" id="gd-q" placeholder="Search the guides… (e.g. river, cliffs, height map)" style="width:100%;box-sizing:border-box">
    <div id="gd-list" class="gd-list"></div>
    <div class="foot"><button class="btn" id="gd-close">Close</button></div></div>`;
  document.body.appendChild(bg);
  const list = bg.querySelector('#gd-list'), q = bg.querySelector('#gd-q');
  const draw = async () => {
    const words = q.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const rows = [];
    for (const g of GUIDES){
      if (!words.length){ rows.push({g, hits: []}); continue; }
      const md = (await guideText(g.file)).replace(/\r/g, '');
      // (the sections the words are all in, to open the guide there)
      const secs = md.split(/\n(?=#{2,3} )/).filter(s => words.every(w => s.toLowerCase().includes(w)));
      if (secs.length || words.every(w => (g.title + ' ' + g.what).toLowerCase().includes(w)))
        rows.push({g, hits: secs.map(s => s.match(/^#{1,3} (.*)/)).filter(Boolean).map(m => m[1]).slice(0, 6)});
    }
    list.innerHTML = rows.length ? rows.map(({g, hits}) => `<button class="gd-row" data-gd="${esc(g.file)}"><b>${esc(g.title)}</b><small>${esc(g.what)}</small></button>
      ${hits.map(h => `<button class="gd-hit" data-gd="${esc(g.file)}" data-at="${esc(docSlug(h))}">→ ${esc(h)}</button>`).join('')}`).join('')
      : '<div class="msg">Nothing found.</div>';
    list.querySelectorAll('[data-gd]').forEach(b => b.onclick = () => { bg.remove(); docModal(b.dataset.gd, b.dataset.at); });
  };
  q.oninput = draw; draw(); q.focus();
  bg.querySelector('#gd-close').onclick = () => bg.remove();
  bg.addEventListener('click', e => { if (e.target === bg) bg.remove(); });
}
// a "?" that opens a guide at one of its sections (beside the tools it explains)
function guideLink(file, section, tip){
  return `<button class="gd-q" data-guide="${esc(file)}" data-at="${esc(docSlug(section))}" title="${esc(tip || 'How this works')}">?</button>`;
}
document.addEventListener('click', e => {
  const b = e.target.closest('[data-guide]'); if (!b) return;
  e.preventDefault(); e.stopPropagation(); docModal(b.dataset.guide, b.dataset.at);
}, true);
function docSlug(s){ return String(s).toLowerCase().replace(/[`*]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''); }

// ----- the Workshop's own papers (web/docs/*.md), read in a window: headings, paragraphs, lists (one level
// nested), tables, bold, italics, code and links; the same file is the one on GitHub. at: a heading to open at
async function docModal(name, at){
  let md;
  try { const r = await fetch('/web/docs/' + name, {cache: 'no-store'}); if (!r.ok) throw new Error('The paper is missing.'); md = await r.text(); }
  catch (e){ return toast(e.message, true); }
  // (which OpenMW you play on, where the paper speaks of what a newer one adds)
  let ver = '';
  if (/OpenMW 0\.5[2-9]/.test(md)){
    try { const v = await api('/api/openmw/version'); ver = `<div class="msg" style="margin-bottom:10px;font-size:12.5px">You're on OpenMW ${esc(v.openmw)}: ${v.new ? `everything here works.` : `parts marked "OpenMW ${esc(v.new_in)}" need it, the rest works.`}</div>`; } catch (e){ /* (shown without) */ }
  }
  const bg = document.createElement('div'); bg.className = 'modal-bg';
  bg.innerHTML = `<div class="modal doc" style="width:min(820px,95vw);max-height:88vh;overflow:auto">${ver}${docHtml(md, true)}
    <div class="foot"><button class="btn" id="doc-guides">All guides…</button><button class="btn primary" id="doc-close">Close</button></div></div>`;
  document.body.appendChild(bg);
  bg.querySelector('#doc-close').onclick = () => bg.remove();
  bg.querySelector('#doc-guides').onclick = () => { bg.remove(); guidesModal(); };
  bg.addEventListener('click', e => { if (e.target === bg) bg.remove(); });
  bg.querySelectorAll('a[href^="http"]').forEach(a => { a.target = '_blank'; a.rel = 'noopener'; });
  // (links inside the paper to its own sections, and the contents list)
  const box = bg.querySelector('.modal');
  const goTo = h => { box.scrollTop += h.getBoundingClientRect().top - box.getBoundingClientRect().top - 8; };
  bg.querySelectorAll('a[href^="#"]').forEach(a => a.onclick = e => {
    e.preventDefault(); const h = box.querySelector('#doc-' + a.getAttribute('href').slice(1)); if (h) goTo(h);
  });
  if (at){ const h = box.querySelector('#doc-' + docSlug(at)); if (h){ goTo(h); h.classList.add('doc-here'); } }
}
function docInline(s){
  return esc(s)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
    .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, '$1<i>$2</i>')
    .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2">$1</a>')
    .replace(/\[([^\]]+)\]\(#([a-z0-9-]+)\)/g, '<a href="#$2">$1</a>')
    .replace(/&lt;(https?:[^&\s]+)&gt;/g, '<a href="$1">$1</a>');
}
function docHtml(md, contents){
  const L = md.replace(/\r/g, '').split('\n'), out = [];
  let i = 0;
  const para = [];
  const flush = () => { if (para.length){ out.push('<p>' + docInline(para.join(' ')) + '</p>'); para.length = 0; } };
  // (headings carry ids to open the paper at; a long paper gets a list of its sections after its title)
  const secs = L.filter(l => /^## /.test(l)).map(l => l.slice(3).trim());
  let listed = !(contents && secs.length >= 4);
  while (i < L.length){
    const line = L[i];
    if (!line.trim()){ flush(); i++; continue; }
    const h = line.match(/^(#{1,3})\s+(.*)$/);
    if (h){
      flush(); const n = h[1].length;
      if (n === 2 && !listed){ listed = true; out.push(`<nav class="doc-toc"><b>In this guide</b>${secs.map(s => `<a href="#${docSlug(s)}">${docInline(s)}</a>`).join('')}</nav>`); }
      out.push(`<h${n + 1} id="doc-${docSlug(h[2])}">${docInline(h[2])}</h${n + 1}>`); i++; continue;
    }
    if (/^\|/.test(line)){
      flush();
      const rows = [];
      while (i < L.length && /^\|/.test(L[i])){ rows.push(L[i]); i++; }
      const cells = r => r.replace(/^\||\|$/g, '').split('|').map(c => docInline(c.trim()));
      const body = rows.filter((r, n) => n !== 1 || !/^\|[\s:|-]+\|$/.test(r));
      out.push('<table class="t doc-t"><tr>' + cells(body[0]).map(c => `<th>${c}</th>`).join('') + '</tr>' +
        body.slice(1).map(r => '<tr>' + cells(r).map(c => `<td>${c}</td>`).join('') + '</tr>').join('') + '</table>');
      continue;
    }
    if (/^\s*- /.test(line)){
      flush();
      // (a list; an item may run on over indented lines, and hold a list of its own, two spaces in)
      const items = [];
      while (i < L.length && (/^\s*- /.test(L[i]) || (/^\s+\S/.test(L[i]) && items.length))){
        const m = L[i].match(/^(\s*)- (.*)$/);
        if (m) items.push({lvl: m[1].length >= 2 ? 1 : 0, text: m[2]});
        else items[items.length - 1].text += ' ' + L[i].trim();
        i++;
      }
      let html = '<ul>', open = false;
      for (const it of items){
        if (it.lvl && !open){ html = html.replace(/<\/li>$/, ''); html += '<ul>'; open = true; }
        else if (!it.lvl && open){ html += '</ul></li>'; open = false; }
        html += '<li>' + docInline(it.text) + '</li>';
      }
      if (open) html += '</ul></li>';
      out.push(html + '</ul>');
      continue;
    }
    para.push(line.trim()); i++;
  }
  flush();
  return out.join('\n');
}
const HELP_KEY = s => `<kbd>${s}</kbd>`;
function helpGo(view){ return `<button class="btn sm" data-gview="${view}">Open ${{world: 'the World map', createv: 'Create', dialog: 'Dialogue', mymod: 'My mod', plugins: 'Load order', settings: 'Settings', chars: 'Characters'}[view] || view}</button>`; }

// ----- Home: where the Workshop opens. What to do first, the places you were in lately, and the guide
// underneath (Help > Getting started comes here too)
function homeStart(){ try { return localStorage.getItem('ws-start') !== 'browse'; } catch (e){ return true; } }
function homeStartSet(on){ try { localStorage.setItem('ws-start', on ? 'home' : 'browse'); } catch (e){} }
function renderGuide(){
  const s = S.summary || {}, p = s.project;
  try { post('/api/settings', {guide_seen: true}); } catch (e) {}
  const places = (typeof WP !== 'undefined' ? WP.places : []).slice(0, 8);
  const card = (k, ic, kick, title, text) => `<button class="ccard" data-home="${k}"><span class="ic">${ic}</span><span class="kick">${kick}</span><b>${title}</b><span class="msg">${text}</span></button>`;
  $('#guidewrap').innerHTML = `
  <div class="home-hero">
    <h1>Morrowind Workshop</h1>
    <p class="lead">Build places, people, quests and dungeons for Morrowind, and walk into them in <b>OpenMW</b> as you make them.
      Your game files are never changed: everything goes into a mod of your own.</p>
    <div class="home-proj">${p
      ? `<span>Working on <b>${esc(p.name)}</b></span><button class="btn sm" data-gview="mymod">My mod</button><button class="btn sm" id="home-switch">Open another…</button>`
      : `<button class="btn primary" id="home-new">＋ Start a mod</button><span class="msg">Give it a name. Save (${HELP_KEY('Ctrl+S')}) writes your work into it, and Undo (${HELP_KEY('Ctrl+Z')}) takes anything back.</span>`}</div>
  </div>

  <div class="cgrid home-cards">
    ${card('tour', '🏠', 'Guided · about 2 minutes', 'Build your first house', 'Lay out a few rooms, let the Workshop build and furnish them from the game\'s own pieces, then look round it in 3D.')}
    ${card('world', '🗺', 'World map', 'Open a place', 'Any town, house or cave of your game, in 2D or 3D. Move things, drag new ones in, furnish rooms, then Play here.')}
    ${card('create', '⚒', 'Create', 'Make something new', 'A house, a dungeon or ruin, a person, a spell, a book, or weapons and armour from the Forge, each one change you can undo.')}
    ${card('browse', '🔎', 'Browse', 'Find anything', 'Search every record in your load order by name, ID, dialogue or model, and open it to see and change it.')}
    ${card('new052', '✨', 'New with OpenMW 0.52', 'New skills, weathers and more', 'Start from an example: a Fishing skill, Piety with its shrines and books, an aurora, a cursed chest. Then change it your way.')}
  </div>

  ${places.length ? `<h2>Where you were lately</h2><div class="home-places">${places.map((pl, n) => `<button class="btn sm" data-homeplace="${n}">${pl.interior ? '🏠' : '🌄'} ${esc(pl.name)}</button>`).join('')}</div>` : ''}

  <label class="msg home-onstart"><input type="checkbox" id="g-onstart" ${homeStart() ? 'checked' : ''}> Open on this page when the Workshop starts</label>

  <details class="home-guide"><summary>How the Workshop works</summary>

  <div class="gcards">
    <div class="gcard"><b>1 · It reads your game</b><p>The Workshop reads OpenMW's own settings, so it sees your Morrowind files and the mods you have switched on,
      in the same order as the game. It never changes your game files: your work goes into a mod file of your own.</p></div>
    <div class="gcard"><b>2 · Start a mod</b><p>Press <b>＋ Start a mod</b> at the top and give it a name. Everything you make or change from then on
      goes into it when you <b>Save</b> (${HELP_KEY('Ctrl+S')}); the title shows a * until then. <b>Undo</b> (${HELP_KEY('Ctrl+Z')}) takes back the last change and <b>Redo</b> (${HELP_KEY('Ctrl+Y')}) puts it back.</p>
      ${p ? `<p class="msg">You're working on <b>${esc(p.name)}</b>.</p>` : '<button class="btn sm primary" onclick="projectModal()">＋ Start a mod</button>'}</div>
    <div class="gcard"><b>3 · Try it in the game</b><p><b>▶ OpenMW → Start the game</b> at the top, or <b>Play here</b> on the World map, starts OpenMW
      with your mod and the <b>live link</b>: what you change in the Workshop appears in the game within a second.</p></div>
  </div>

  <h2>Finding your way</h2>
  <table class="t gtable">
    <tr><td><b>Browse</b></td><td>Every record in your game: search anything (names, IDs, dialogue, models) and click to see it, with links between records.
      <b>▦ Table</b> shows columns you choose and sort; <b>📌</b> pins a record in its own panel to compare it with others.</td></tr>
    <tr><td><b>World map</b></td><td>Places in 2D or 3D. Drag things in from the Place panel, click to select, drag to move. In 3D: right-drag to look,
      ${HELP_KEY('W')}${HELP_KEY('A')}${HELP_KEY('S')}${HELP_KEY('D')} to fly, ${HELP_KEY('G')} move, ${HELP_KEY('R')} turn; <b>View ▾</b> has a grid, wireframe and, outdoors, the view distance; <b>?</b> lists every control.
      Outdoors, <b>⛰ Ground</b> shapes and paints the land and scatters grass and plants.</td></tr>
    <tr><td><b>Create</b></td><td>Quick starts: a whole house built from a style's wall and floor pieces and furnished (or a place the game made, copied with a door from outside), new people, items, spells, books, random loot lists and containers. Each is one change you can undo.
      <b>The Forge</b> makes weapons and armour, one piece or a whole set, with the game's own numbers for the material, then puts them into the world: the loot lists, the people who carry such things, the merchants who sell them.</td></tr>
    <tr><td><b>Characters</b></td><td>People and creatures: looks, stats, what they sell, where they stand.</td></tr>
    <tr><td><b>Dialogue</b></td><td>Greetings, topics and quests with their journal stages. Lines can depend on quest stages, items and more.</td></tr>
    <tr><td><b>Scripts</b></td><td>Morrowind scripts and OpenMW Lua scripts, checked as you type.</td></tr>
    <tr><td><b>Rules</b></td><td>Factions, classes, races, birthsigns, skills, regions and weather, sounds (and the sounds creatures make), magic effects, global variables and game settings.</td></tr>
    <tr><td><b>My mod</b></td><td>What your mod contains, and <b>Get ready to share</b>: checks it, writes a readme and packs a zip.</td></tr>
    <tr><td><b>📁 File</b> (at the top)</td><td><b>Open…</b> opens any .esp or .omwaddon, or one of your mods, from your computer's file picker. As in the Construction Set the file is the <b>active file</b>, saved back into; its placed objects keep their numbers, so saved games still work. <b>Save</b> (Ctrl+S) writes your changes into the mod; until then they are held here. <b>Save as…</b> puts everything into a new mod and you carry on in the copy. <b>Save a version</b> and <b>Earlier versions</b> keep and bring back the mod as it was saved. <b>Merge a mod into this one</b> folds another of your mods into this one as one change; <b>Merge a plugin file</b> does the same for any .esp or .omwaddon. <b>Manage mods</b> lists them all, to switch or delete.</td></tr>
    <tr><td><b>Health check</b></td><td>Problems in your load order, like missing masters, models or textures, and <b>Check my mod</b>: every record of your mod checked the way the game's editor checks them.</td></tr>
    <tr><td><b>Load order</b></td><td>Switch plugins on or off and change their order (saved to OpenMW's settings, with a backup).</td></tr>
  </table>

  <h2>Working faster</h2>
  <ul class="glist">
    <li><b>Panels:</b> every page's tools are panels. Drag a tab to move it, dock it on a side or tab it with others; drag the edges to resize; ⋮ to float or close it.
      <b>▤ Panels</b> opens any panel and has ready-made layouts, and you can save your own.</li>
    <li>The buttons over the map come in groups: drag a group's grip <b>⋮⋮</b> to put it where you like, and it stays there (near the right or bottom edge, it keeps to that edge). Right-click a grip to put the buttons back in a row, or to lock them and hide the grips.</li>
    <li>${HELP_KEY('Ctrl+K')} finds any command, page, panel, place or record. ${HELP_KEY('Ctrl+/')} lets you change the keyboard shortcuts.</li>
    <li><b>Right-click</b> anything on the World map, in 3D or in a list for what you can do with it. The bar under the map shows the place, the mouse or camera position, and what's selected (click a position to copy it).</li>
    <li>${HELP_KEY('F1')} on something shows <b>where it's used</b>: the places it stands in, who carries it, the scripts and dialogue that name it.</li>
    <li>Your mod's changes are marked on the map: green new, gold changed, a red ✕ where you took something out (right-click it to bring it back). <b>My changes</b> lists them all.</li>
    <li>${HELP_KEY('H')} hides what's selected so you can get at what's behind, ${HELP_KEY('Shift+H')} hides everything else, ${HELP_KEY('Alt+H')} shows it all again.</li>
    <li><b>Hidden doors:</b> right-click a wall (or any piece of scenery) → <b>Make it a hidden door</b>. It keeps its looks and its spot but is now a door: make it lead somewhere, or leave it to swing open on its edge. <b>Make it an activator</b> does the same for a piece a script should react to.</li>
    <li>Select a door and press ${HELP_KEY('Enter')} to go through it; ${HELP_KEY('Alt+←')} comes back. ${HELP_KEY('Ctrl+H')} replaces every one of an object with another.</li>
    <li><b>Walking paths</b> (the path grid people and creatures follow): the <b>🚶 Paths</b> panel → <b>✎ Edit by hand</b>, on the map or in 3D. Click to add a point, joined to the selected one (${HELP_KEY('Ctrl')}+click: not joined); drag a point to move it; ${HELP_KEY('Shift')}+click another point to join or unjoin them; ${HELP_KEY('Delete')} takes one out, ${HELP_KEY('Ctrl+Z')} undoes. ${HELP_KEY('Esc')} or ✓ Done saves it all as one Undo; Discard leaves the paths as they were. <b>Make them for me</b> works out a whole set for you, to touch up by hand.</li>
    <li><b>👤 Play as</b> (by Play here) starts the game as one of your own characters, from their latest save, at the spot you pick. <b>🧪 Test setups</b> add items, spells, quest stages or variables on top.</li>
    <li><b>Settings → Appearance</b> has themes and your own colours.</li>
  </ul>

  <h2>Playing with the live link</h2>
  <p>While the game runs from the Workshop, the top shows <b>● Game linked</b>. Then:</p>
  <ul class="glist">
    <li>Edits you make in the Workshop appear in the game. Brand-new places and records need a restart of the game.</li>
    <li><b>Me</b>, with the map pin (jump to my character) shows where you are on the map; <b>Follow my character</b> on the map keeps up with you.</li>
    <li>On the Dialogue page you can set quest stages, give items and change variables in the running game, and see which conditions are true right now.</li>
    <li>You build in the Workshop; the game only shows it. Nothing you do in game changes your mod, so you can play normally while it's linked.</li>
    <li>A game started from OpenMW's own Launcher isn't linked (the top says <b>○ Game not linked</b>): start it from the Workshop instead.</li>
  </ul>

  <h2>Sharing your mod</h2>
  <p>Open <b>My mod → Get ready to share</b>. It checks the mod, lists the other mods it needs, writes a readme and makes a zip you can upload,
    for example to Nexus Mods. <b>Start a clean test</b> (step 3 there) starts the game with only the base game and your mod's requirements, to see it as others will.</p>

  <h2>AI (optional)</h2>
  <p>Everything in the Workshop works without AI. Two ways to use it, set up in <b>Settings → AI</b>:</p>
  <ul class="glist">
    <li><b>The Lua and dialogue writer</b>: <b>✦ Write with AI</b> and <b>✦ Fix</b> in the Lua editor, and the ✦ beside dialogue lines, by a model
      running on your own PC (Ollama, LM Studio…), free.</li>
    <li><b>Coding agents</b>: Claude Code, Codex, Cursor and others, on your own plan or model, work on your open mod with the Workshop's own tools
      (MCP): ask in plain words ("furnish this room like a poor fisherman's hut", "make a short quest for Fenas") and they build it.</li>
  </ul>
  <p>Whatever an AI does goes into your mod like your own edits: it shows in My changes, and <b>Undo</b> takes it back. Try AI-written scripts in the
    game before sharing. <b>? Help → Guides → Coding with AI</b> has the details.</p>

  <h2>If something goes wrong</h2>
  <ul class="glist">
    <li><b>Undo</b> takes back changes one by one. The Workshop also keeps <b>automatic backups</b> of your mod (Settings → Backups), and can restore any of them.</li>
    <li><b>? Help → Report a problem</b> makes a report with the details needed to fix it, ready to copy and send.</li>
    <li>Your work is kept in the Workshop's <b>projects</b> folder; the mod file the game loads goes into OpenMW's data folder.</li>
  </ul>

  <div class="actions" style="margin-top:18px">${helpGo('world')}${helpGo('createv')}${helpGo('settings')}</div>
  </details>`;
  const w = $('#guidewrap');
  $('#g-onstart').onchange = e => homeStartSet(e.target.checked);
  const nw = $('#home-new'); if (nw) nw.onclick = () => projectModal();
  const sw = $('#home-switch'); if (sw) sw.onclick = () => projectModal();
  w.querySelectorAll('[data-home]').forEach(b => b.onclick = () => {
    const k = b.dataset.home;
    if (k === 'tour') coachHouse();
    else if (k === 'world') showView('world');
    else if (k === 'create') showView('createv');
    else if (k === 'new052') rcOpenKind('happens');
    else { showView('browse'); $('#q').focus(); }
  });
  w.querySelectorAll('[data-homeplace]').forEach(b => b.onclick = () => { showView('world'); wpPlaceOpen(+b.dataset.homeplace); });
}
document.addEventListener('click', e => { const g = e.target.closest('[data-gview]'); if (g) showView(g.dataset.gview); });
// (the logo, top left, goes Home)
document.addEventListener('click', e => { if (e.target.closest && e.target.closest('.brand')) showView('guide'); });

// ----- settings
// Coding agents (Settings › AI › Coding agents): what to paste into each, from the Workshop's address (Streamable
// HTTP) or, for agents that only start a command, the stdio bridge (mcp_stdio.py) with the Workshop's own Python.
const MCP_NAME = 'morrowind-workshop';
const MCP_AGENTS = [
  {id: 'claudecode', label: 'Claude Code', hint: 'Connect Claude Code above does this for you. Or, where the claude command works, run this once.',
   snip: m => `claude mcp add --scope user --transport http ${MCP_NAME} "${m.address}"`},
  {id: 'claudedesktop', label: 'Claude Desktop', hint: 'Settings › Developer › Edit Config (claude_desktop_config.json): add this under "mcpServers", then restart Claude.',
   snip: m => JSON.stringify({mcpServers: {[MCP_NAME]: {command: m.python, args: [m.bridge]}}}, null, 2)},
  {id: 'codex', label: 'Codex CLI', hint: 'Add to ~/.codex/config.toml.',
   snip: m => `[mcp_servers.${MCP_NAME}]\ncommand = '${m.python}'\nargs = ['${m.bridge}']`},
  {id: 'cursor', label: 'Cursor', hint: 'Settings › MCP › Add new MCP server, or ~/.cursor/mcp.json.',
   snip: m => JSON.stringify({mcpServers: {[MCP_NAME]: {url: m.address}}}, null, 2)},
  {id: 'vscode', label: 'VS Code (Copilot)', hint: 'In .vscode/mcp.json, or MCP: Add Server in the command palette.',
   snip: m => JSON.stringify({servers: {[MCP_NAME]: {type: 'http', url: m.address}}}, null, 2)},
  {id: 'opencode', label: 'opencode', hint: 'In opencode.json (it works with models on this PC too).',
   snip: m => JSON.stringify({mcp: {[MCP_NAME]: {type: 'remote', url: m.address}}}, null, 2)},
  {id: 'http', label: 'Another agent (address)', hint: 'Any agent that takes a Streamable HTTP MCP address. The key is in it; keep it to yourself.',
   snip: m => m.address},
  {id: 'stdio', label: 'Another agent (command)', hint: 'Any agent that starts an MCP server as a command (stdio). The Workshop must be running.',
   snip: m => `"${m.python}" "${m.bridge}"`},
];
// Claude Code's line under Set up: whether it is on this PC and has the Workshop's address (mcpserver.claude_code)
function mcpCcHtml(cc){
  if (!cc) return '';
  if (!cc.here) return `<span class="msg" style="flex:1">Claude Code isn't on this PC. Install the Claude app, open its Code tab once, then come back here.</span>
    <a class="btn sm" href="https://claude.ai/download" target="_blank" rel="noopener">Get the Claude app</a>`;
  if (cc.connected === 'yes') return `<span class="msg" style="flex:1;color:var(--green)" title="Claude Code has this address for every folder. Its sessions started before connecting don't see it.">✓ Connected: start a new Claude Code session and ask it about your mod.</span>
    <button class="btn sm" id="st-ccgo" title="Give Claude Code the address again">Connect again</button>`;
  return `${cc.connected === 'old' ? '<span class="msg" style="color:var(--red)" title="Its address has an earlier key, or another port">Claude Code has an old address.</span>' : ''}
    <button class="btn primary sm" id="st-ccgo" title="Gives Claude Code the Workshop's address, for every folder: no terminal needed">Connect Claude Code</button>`;
}
async function renderSettings(){
  const w = $('#settingswrap');
  let st, bk;
  let mcp = null;
  try { st = await api('/api/settings'); bk = await api('/api/backups'); try { mcp = await api('/api/mcp/status'); } catch (e){} }
  catch (e){ w.innerHTML = `<h1>Settings</h1><div class="msg err">${esc(e.message)}</div>`; return; }
  const p = S.summary && S.summary.project;
  const when = t => new Date(t * 1000).toLocaleString();
  w.innerHTML = `<h1>Settings${typeof guideLink === 'function' ? guideLink('getting-around.md', 'Settings') : ''}</h1>${typeof thSection === 'function' ? thSection() : ''}
  <section class="card setsec"><h3>OpenMW</h3>
    <div class="setrow"><span>Installed in</span><b>${st.openmw_install ? esc(st.openmw_install) : '<span style="color:var(--amber)">not found</span>'}</b></div>
    <div class="setrow"><span>Its settings (load order)</span><span class="msg">${esc(st.openmw_cfg || '')}</span></div>
    <div class="actions"><button class="btn sm" id="st-pick">Choose OpenMW's folder…</button>
      ${st.openmw_chosen ? '<button class="btn sm" id="st-auto" title="Forget the chosen folder and look for OpenMW by itself">Find it automatically</button>' : ''}
      <button class="btn sm" data-open="openmw">Open OpenMW's settings folder</button></div></section>

  <section class="card setsec"><h3>AI${typeof guideLink === 'function' ? guideLink('coding-with-ai.md', 'Which AI does what') : ''}</h3>
    <p class="msg">All optional: everything else in the Workshop works without AI.</p>

    <h4 class="aisub">Lua and dialogue writer${typeof guideLink === 'function' ? guideLink('coding-with-ai.md', 'Setting up a model on your PC') : ''}</h4>
    <p class="msg" title="Scripts › a Lua script › ✦ Write with AI and ✦ Fix; your own magic effects' ✦ Write it for me; the ✦ beside dialogue lines">✦ Write with AI, ✦ Fix and the ✦ suggestions, by a model running on this PC, free.</p>
    <div class="actions" id="st-local">
      <input class="inp" id="st-lurl" value="${esc(st.ai_local_url || 'http://127.0.0.1:11434/v1')}" style="max-width:240px" title="Any app with the usual chat address. Ollama: http://127.0.0.1:11434/v1 · LM Studio: http://127.0.0.1:1234/v1 (its server switched on) · llama.cpp's llama-server: http://127.0.0.1:8080/v1 · KoboldCpp: http://127.0.0.1:5001/v1">
      <select class="inp" id="st-lmodel" style="max-width:240px">${st.ai_local_model ? `<option selected>${esc(st.ai_local_model)}</option>` : '<option value="">(no model chosen)</option>'}</select>
      <button class="btn sm" id="st-lfind" title="Ask the app at that address which models it has">Find models</button></div>

    <h4 class="aisub">Coding agents <span class="msg">MCP</span>${typeof guideLink === 'function' ? guideLink('coding-with-ai.md', 'Coding agents', 'Using a coding agent') : ''}</h4>
    <p class="msg" title="The Workshop is an MCP server: agents use its tools on the mod you have open, every change in My changes marked as theirs, and Undo takes it back. Only programs on this PC can reach it, with the key in its address.">Let Claude Code, Codex, Cursor and other agents work on your open mod with the Workshop's own tools.</p>
    <label class="msg" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="st-mcp" ${mcp && mcp.on ? 'checked' : ''}> Let coding agents connect</label>
    ${mcp && mcp.on ? `<label class="msg" style="display:flex;gap:6px;align-items:center" title="This window goes to the place an agent opens or changes and selects what it places or moves; a line at the foot says what it is doing"><input type="checkbox" id="st-agfollow" ${typeof agFollowOn !== 'function' || agFollowOn() ? 'checked' : ''}> Show me what agents do</label>` : ''}
    ${mcp && mcp.on ? `<div class="setrow" style="margin-top:6px"><span>Address</span>
      <span style="display:flex;gap:6px;flex:1;justify-content:flex-end"><input class="inp" id="st-mcpurl" readonly value="${esc(mcp.address)}" style="max-width:420px;font-family:var(--mono,monospace);font-size:12px">
      <button class="btn sm" data-mcpcopy="url">Copy</button><button class="btn sm" id="st-mcpkey" title="A new key in the address: agents set up with the old one can't connect until given the new one">New key</button></span></div>
    <div class="setrow"><span>Set up</span><select class="inp" id="st-mcpagent" style="max-width:260px">${MCP_AGENTS.map(a => `<option value="${a.id}">${esc(a.label)}</option>`).join('')}</select></div>
    <div class="actions" id="st-cc" style="margin:6px 0 2px">${mcpCcHtml(mcp.claude_code)}</div>
    <pre class="mcpsnip" id="st-mcpsnip"></pre><div class="actions" style="margin-top:4px"><span class="msg" id="st-mcphint" style="flex:1"></span><button class="btn sm" data-mcpcopy="snip">Copy</button></div>
    ${mcp.clients && mcp.clients.length ? `<div class="msg" style="margin-top:6px">Connected lately: ${mcp.clients.map(c => `<b>${esc(c.name)}</b> ${c.last < 90 ? 'now' : Math.round(c.last / 60) + ' min ago'} (${c.calls} call${c.calls === 1 ? '' : 's'})`).join(' · ')}</div>` : ''}` : ''}
  </section>

  <section class="card setsec" id="st-bridge-sec" hidden><h3>Connected programs</h3>
    <p class="msg" title="Modding programs you allowed to work on your open mod. Their changes join your unsaved work, marked ⇄ in My changes, each with Undo.">Programs you allowed to work on your open mod.</p>
    <div id="st-bridge"></div></section>

  <section class="card setsec"><h3>Backups of your mod</h3>
    <p class="msg">The Workshop copies your mod's project file when you open it and then regularly while you work, and keeps the newest ones.</p>
    <div class="setrow"><span>Make a backup every</span><span><input class="inp num" id="st-bmin" type="number" min="1" max="240" value="${st.backup_minutes}" style="width:70px"> minutes while you work</span></div>
    <div class="setrow"><span>Keep the newest</span><span><input class="inp num" id="st-bkeep" type="number" min="1" max="500" value="${st.backup_keep}" style="width:70px"> backups of each mod</span></div>
    <div class="setrow"><span>Space for them</span><span><input class="inp num" id="st-bmb" type="number" min="0" max="100000" value="${st.backup_mb || 0}" style="width:80px" title="The oldest go first once a mod's backups take more. 0: no limit"> MB a mod at most (0: no limit)</span></div>
    <label class="msg" style="display:flex;gap:6px;align-items:center;margin-top:6px"><input type="checkbox" id="st-bzip" ${st.backup_zip ? 'checked' : ''}> Store them compressed <span title="About a tenth of the size; a backup takes a moment longer to make and to restore. Ones made before stay as they are">(about a tenth of the size)</span></label>
    ${p ? `<h4 style="margin:14px 0 6px">Backups of ${esc(p.name)} (${bk.backups.length}${bk.total ? ` · ${fmtN(Math.round(bk.total / 1048576))} MB` : ''})${bk.backups.length > 3 ? ` <button class="btn sm" id="st-bclear" title="Delete all but the newest 3 backups of this mod">Clear old ones</button>` : ''}</h4>
      <div class="bklist">${bk.backups.map(b => `<div class="setrow"><span>${esc(when(b.time))}${b.why ? ` <span class="chip">${esc(b.why)}</span>` : ''}</span>
        <span><span class="msg">${fmtN(Math.round(b.size / 1024))} KB</span> <button class="btn sm" data-restore="${esc(b.file)}">Restore</button></span></div>`).join('')
        || '<div class="msg">None yet: the first is made a few minutes after you start working on it.</div>'}</div>` : '<p class="msg">Open a mod to see its backups.</p>'}
    <div class="actions"><button class="btn sm" data-open="backups">Open the backups folder</button></div></section>

  <section class="card setsec"><h3>Starting up</h3>
    <label style="display:flex;gap:8px;align-items:center"><input type="checkbox" id="st-guide" ${homeStart() ? 'checked' : ''}> Open on the Home page (unticked: on Browse). Click the logo at the top left to go Home any time.</label></section>

  <section class="card setsec"><h3>Folders</h3>
    <div class="setrow"><span>Your projects</span><span class="msg">${esc(st.projects_folder)}</span></div>
    <div class="setrow"><span>The Workshop</span><span class="msg">${esc(st.app_folder)} · version ${esc(st.version)}</span></div>
    <div class="actions"><button class="btn sm" data-open="projects">Open the projects folder</button><button class="btn sm" data-open="app">Open the Workshop's folder</button></div></section>`;

  if (typeof thBind === 'function') thBind(w);
  if (typeof lpSettings === 'function') lpSettings();      // (Connected programs: bridge.js)
  const save = body => post('/api/settings', body).then(() => toast('Saved.')).catch(e => toast(e.message, true));
  $('#st-pick').onclick = async () => { try { toast('Choose OpenMW\'s folder in the window that opens…'); const r = await post('/api/openmw/pick', {}); if (r.ok){ toast('Using OpenMW in ' + r.install + '. Reading your game again…'); setTimeout(poll, 300); } } catch (e){ toast(e.message, true); } };
  const auto = $('#st-auto'); if (auto) auto.onclick = async () => { await post('/api/settings', {openmw_reset: true}); toast('Looking for OpenMW by itself. Reading your game again…'); setTimeout(poll, 300); };
  // (a model on this PC: Ollama or LM Studio, for the writers of Lua and dialogue lines; ai.Assistant._write)
  // (coding agents: mcpserver.py; the line or config to paste for the agent picked)
  const mcpBox = $('#st-mcp');
  if (mcpBox) mcpBox.onchange = async e => { try { await post('/api/mcp/turn', {on: e.target.checked}); renderSettings(); } catch (x){ toast(x.message, true); } };
  const agf = $('#st-agfollow');
  if (agf) agf.onchange = e => { try { localStorage.setItem('ws-agfollow', e.target.checked ? '1' : '0'); } catch (x){} };
  const mk = $('#st-mcpkey');
  if (mk) mk.onclick = async () => { if (!confirm('Make a new key? Agents set up with the old address can\'t connect until you give them the new one.')) return; await post('/api/mcp/newkey', {}); renderSettings(); };
  const ag = $('#st-mcpagent');
  if (ag && mcp){
    const show = () => { const a = MCP_AGENTS.find(x => x.id === ag.value) || MCP_AGENTS[0]; $('#st-mcpsnip').textContent = a.snip(mcp); $('#st-mcphint').textContent = a.hint;
      const cc = $('#st-cc'); if (cc) cc.style.display = a.id === 'claudecode' ? '' : 'none'; };
    // (Connect Claude Code: one click, no terminal; mcpserver.connect_claude_code)
    const go = $('#st-ccgo');
    if (go) go.onclick = async () => {
      go.disabled = true; go.innerHTML = '<span class="spin"></span> Connecting…';
      try { mcp.claude_code = await post('/api/mcp/claudecode', {}); toast('Claude Code has the Workshop. Start a new Claude Code session and ask it about your mod.'); }
      catch (x){ toast(x.message, true); }
      renderSettings();
    };
    try { ag.value = localStorage.getItem('ws-mcpagent') || 'claudecode'; } catch (x){}
    ag.onchange = () => { try { localStorage.setItem('ws-mcpagent', ag.value); } catch (x){} show(); };
    show();
  }
  w.querySelectorAll('[data-mcpcopy]').forEach(b => b.onclick = async () => {
    const t = b.dataset.mcpcopy === 'url' ? $('#st-mcpurl').value : $('#st-mcpsnip').textContent;
    try { await navigator.clipboard.writeText(t); toast('Copied.'); } catch (x){ toast('Select it and copy with Ctrl+C.'); }
  });
  $('#st-lurl').onchange = e => save({ai_local_url: e.target.value.trim()});
  $('#st-lmodel').onchange = e => save({ai_local_model: e.target.value});
  $('#st-lfind').onclick = async () => {
    const b = $('#st-lfind'), sel = $('#st-lmodel'), url = $('#st-lurl').value.trim();
    b.disabled = true;
    try {
      const r = await post('/api/ai/local/models', {url});
      if (!r.models.length){ toast('The app at ' + url + ' has no models yet.', true); return; }
      const cur = sel.value;
      sel.innerHTML = r.models.map(m => `<option${m === cur ? ' selected' : ''}>${esc(m)}</option>`).join('');
      await save({ai_local_url: url, ai_local_model: sel.value});
    } catch (e){ toast(e.message, true); }
    finally { b.disabled = false; }
  };
  $('#st-bmin').onchange = e => save({backup_minutes: +e.target.value});
  $('#st-bkeep').onchange = e => save({backup_keep: +e.target.value});
  $('#st-bmb').onchange = e => save({backup_mb: +e.target.value});
  $('#st-bzip').onchange = e => save({backup_zip: e.target.checked});
  const bc = $('#st-bclear'); if (bc) bc.onclick = async () => {
    if (!confirm('Delete all but the newest 3 backups of this mod?')) return;
    try { const r = await post('/api/backups/clear', {keep: 3}); toast(`${r.gone} backup${r.gone === 1 ? '' : 's'} deleted.`); renderSettings(); }
    catch (e){ toast(e.message, true); }
  };
  $('#st-guide').onchange = e => { homeStartSet(e.target.checked); toast('Saved.'); };
  w.querySelectorAll('[data-open]').forEach(b => b.onclick = () => post('/api/open_place', {what: b.dataset.open}).catch(e => toast(e.message, true)));
  w.querySelectorAll('[data-restore]').forEach(b => b.onclick = async () => {
    const f = b.dataset.restore;
    if (!confirm(`Put your mod back to how it was in this backup?\n\n${f}\n\nHow it is now is backed up first, so you can come back to it.`)) return;
    try { await post('/api/backups/restore', {file: f}); toast('Restored. Reading your mod again…'); setTimeout(poll, 300); }
    catch (e){ toast(e.message, true); }
  });
}

// ----- report a problem
// what the page itself saw, for the report: its faults, the problems it showed, and where you were
function reportPage(){
  const errs = typeof PAGE_ERRORS !== 'undefined' ? PAGE_ERRORS : [];
  // (a fault's own message isn't counted twice)
  const probs = typeof TOASTS !== 'undefined' ? TOASTS.filter(x => x.err && !x.msg.startsWith('Something went wrong in the page:')).slice(-15) : [];
  return {view: (document.querySelector('.view.on') || {}).id || '', place: typeof W !== 'undefined' ? W.key || '' : '',
    three_d: typeof V3 !== 'undefined' && !!V3.on, theme: typeof thGet === 'function' ? (thGet().theme || '') : '',
    window: innerWidth + 'x' + innerHeight, browser: navigator.userAgent.slice(0, 160),
    errors: errs.map(e => `${e.t} ${e.where ? '(' + e.where + ') ' : ''}${e.msg}`),
    problems: probs.map(x => `${x.t} ${x.msg}`)};
}
function reportModal(){
  const pg = reportPage(), n = pg.errors.length + pg.problems.length;
  const bg = document.createElement('div'); bg.className = 'modal-bg';
  bg.innerHTML = `<div class="modal" style="width:min(640px,94vw)"><h2>Report a problem</h2>
    <div class="msg">A report with the versions, your setup, ${n ? `<b>the ${n} problem${n === 1 ? '' : 's'} the page showed</b>, ` : ''}the page you were on and the end of the logs. No user name.</div>
    <label>What happened? What did you do just before?</label>
    <textarea class="inp" id="rp-what" style="min-height:90px" placeholder="e.g. I pressed Auto-furnish in a Dres house and nothing appeared."></textarea>
    <div id="rp-out"></div>
    <div class="foot"><button class="btn" id="rp-close">Close</button><button class="btn primary" id="rp-make">Make the report</button></div></div>`;
  document.body.appendChild(bg);
  $('#rp-close').onclick = () => bg.remove();
  $('#rp-make').onclick = async () => {
    try {
      const r = await post('/api/report', {what: $('#rp-what').value, page: reportPage()});
      $('#rp-out').innerHTML = `<label>The report (saved as a text file too)</label><textarea class="inp code" id="rp-text" style="min-height:200px;font-size:11.5px" readonly>${esc(r.text)}</textarea>
        <div class="actions"><button class="btn sm primary" id="rp-copy">Copy to clipboard</button><button class="btn sm" id="rp-folder">Open the reports folder</button></div>
        <div class="msg">Read it over, then paste it where you got the Workshop (for example its Nexus Mods bugs page), or send the file.</div>`;
      $('#rp-copy').onclick = async () => { try { await navigator.clipboard.writeText(r.text); toast('Copied.'); } catch (e){ $('#rp-text').select(); document.execCommand('copy'); toast('Copied.'); } };
      $('#rp-folder').onclick = () => post('/api/open_place', {what: 'reports'});
      $('#rp-make').textContent = 'Make it again';
    } catch (e){ toast(e.message, true); }
  };
}

// ----- about & licences
// (one at a time: opened slowly behind a big town build, a second click made a second window, and its Close was bound
// to the first window's button, so the one in front wouldn't close by Close, Esc or anything, the user 2026-11-01)
let AB_OPENING = false;
async function aboutModal(){
  if (AB_OPENING || document.getElementById('ab-modal')) return;
  AB_OPENING = true;
  let a;
  try { a = await api('/api/about'); } catch (e){ return toast(e.message, true); } finally { AB_OPENING = false; }
  if (document.getElementById('ab-modal')) return;
  const bg = document.createElement('div'); bg.className = 'modal-bg'; bg.id = 'ab-modal';
  // (the logo from the top left, at the window's top right)
  const logo = document.querySelector('.brand svg.logo, .brand svg');
  // (it floats in the free space right of the title and version, so the text keeps its own spacing)
  bg.innerHTML = `<div class="modal" style="width:min(680px,94vw);max-height:86vh;overflow:auto;position:relative">
    <div style="display:flex;gap:18px;align-items:flex-start"><div style="flex:1;min-width:0">
    <h2>Morrowind Workshop</h2>
    <div class="msg">Version <b>${esc(a.version)}</b> · OpenMW ${esc(a.openmw)} · Python ${esc(a.python)}</div>
    <div class="msg" style="font-size:12px">${a.openmw_new ? `OpenMW ${esc(a.new_in)}'s new features are on: your own skills, attributes, weathers, traps and loot rules; spells that burst, strike, glow and act where their bolt strikes.`
      : `Features marked "OpenMW ${esc(a.new_in)}" need it; everything else works on your OpenMW.`}</div></div>
    ${logo ? `<div class="ab-logo" style="flex:none;height:96px;pointer-events:none">${logo.outerHTML}</div>` : ''}</div>
    ${a.credits ? `<table class="t" style="font-size:12.5px;margin-top:8px">
      <tr><td style="white-space:nowrap">Made by</td><td><b>${esc(a.credits.author)}</b>, with ${esc(a.credits.with)}</td></tr>
      <tr><td>Licence</td><td>© 2026 ${esc(a.credits.author)} · <a href="${esc(a.credits.license_url)}" target="_blank" rel="noopener">${esc(a.credits.license)}</a>: share and change it, with credit, but not for commercial purposes</td></tr>
      ${a.credits.github ? `<tr><td>Source</td><td><a href="${esc(a.credits.github)}" target="_blank" rel="noopener">${esc(a.credits.github.replace(/^https?:\/\//, ''))}</a></td></tr>` : ''}
    </table>` : ''}
    <p class="msg" style="line-height:1.6">A workshop for Morrowind mods with OpenMW. Not made by or affiliated with Bethesda Softworks or the OpenMW project.
      Morrowind is a trademark of Bethesda Softworks / ZeniMax Media; the Workshop includes none of its files, it reads the ones you own.</p>
    <h3 style="margin-top:12px">Built with</h3>
    <table class="t" style="font-size:12.5px">${a.components.map((c, n) => `<tr><td><b>${esc(c.name)}</b> ${esc(c.version)}${c.by ? `<div class="msg">${esc(c.by)}</div>` : ''}</td>
      <td>${esc(c.license)}${c.text ? ` · <span class="lnk" data-lic="${n}">read</span>` : ''}</td>
      <td>${c.url ? `<a href="${esc(c.url)}" target="_blank" rel="noopener">website</a>` : ''}</td></tr>`).join('')}</table>
    <pre id="ab-lic" class="code" style="display:none;white-space:pre-wrap;font-size:11.5px;max-height:260px;overflow:auto;background:var(--panel2);padding:10px;border-radius:8px"></pre>
    <div class="msg" style="margin-top:8px">The full notices are in THIRD_PARTY_NOTICES.txt in the Workshop's folder.</div>
    <div class="foot"><button class="btn primary" id="ab-close">Close</button></div></div>`;
  document.body.appendChild(bg);
  const lg = bg.querySelector('.ab-logo svg'); if (lg){ lg.style.height = '100%'; lg.style.width = 'auto'; lg.style.display = 'block'; }
  bg.querySelector('#ab-close').onclick = () => bg.remove();
  bg.addEventListener('click', e => { if (e.target === bg) bg.remove(); });
  bg.querySelectorAll('[data-lic]').forEach(l => l.onclick = () => { const pre = bg.querySelector('#ab-lic'); pre.textContent = a.components[+l.dataset.lic].text; pre.style.display = 'block'; pre.scrollIntoView({block: 'nearest'}); });
}

// (a right-click on the logo, top left: About)
document.addEventListener('contextmenu', e => {
  const b = e.target.closest && e.target.closest('.brand'); if (!b) return;
  e.preventDefault(); e.stopPropagation();
  pnlMenu({x: e.clientX, y: e.clientY}, [{label: 'ℹ About Morrowind Workshop…', act: () => aboutModal()}]);
}, true);

// ----- links into the Workshop: #view=dialog, #cell=balmora&3d=1&cam=x,y,z,yaw,pitch, #quest=..., #search=...
async function openFromLink(hash){
  const h = new URLSearchParams(hash.replace(/^#/, ''));
  if (h.get('search')){ $('#q').value = S.q = h.get('search'); S.types = h.get('type') ? [h.get('type')] : []; buildSide(); showView('browse'); await runSearch();
    if (h.get('open') && S.rows.length) openRecord(S.rows[0].i, true); }
  if (h.get('cell')){
    showView('world'); await worldOpen(h.get('cell').toLowerCase());
    if (h.get('zoom')){ W.cam.z = +h.get('zoom'); if (h.get('at')){ const [x, y] = h.get('at').split(',').map(Number); W.cam.x = x; W.cam.y = y; } drawMap(); if (W.ext) recentre(); }
    if (h.get('3d') === '1'){
      if (h.has('show')){                       // e.g. show=grid,wire: just these View menu options
        const on = h.get('show').split(',');
        for (const k of Object.keys(V3.view)) V3.view[k] = on.includes(k) || ((k === 'ground' || k === 'water') && !on.includes('no' + k));
      }
      await v3Enable(true);
      if (h.get('cam')){ const [x, y, z, yaw, pitch] = h.get('cam').split(',').map(Number);
        V3.pos.set(x - V3.origin[0], y - V3.origin[1], z - V3.origin[2]); V3.yaw = yaw || 0; V3.pitch = pitch || -0.3; v3Refresh(); }
      if (h.get('light')){ V3.lightMode = h.get('light'); v3ApplyLighting(); v3Tools(); }
    } else if (V3.on) await v3Enable(false);
  }
  if (h.get('quest')){ showView('dialog'); await dOpen('quest', h.get('quest').toLowerCase()); }
  if (h.get('topic')){ showView('dialog'); await dOpen('topic', h.get('topic').toLowerCase()); }
  if (h.get('view')) showView(h.get('view'));
  if (h.get('demo') === 'furnish' && typeof demoFurnish === 'function') DEMO.result = await demoFurnish({name: h.get('name') || undefined});
  if (h.get('demo') === 'shot' && typeof demoShot === 'function') await demoShot(h.get('s'), h.get('arg'));
}

// ----- first start: show the guide once the game data is read (unless a link says where to go)
(function firstRun(){
  const t = setInterval(async () => {
    if (!S.summary || S.summary.state !== 'ready') return;
    clearInterval(t);
    try {
      const st = await api('/api/settings');
      if (location.hash.length > 1) await openFromLink(location.hash);
      else if (!st.guide_seen || homeStart()) showView('guide');
      setTimeout(() => { if (typeof crPrefetch === 'function') crPrefetch(); }, 4000);
    } catch (e){ console.warn(e); }
  }, 700);
})();
window.addEventListener('hashchange', () => { if (S.summary && S.summary.state === 'ready') openFromLink(location.hash); });
