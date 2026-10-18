// ---------- Help: getting started guide, settings, problem report, about & licences ----------
// The guide opens by itself the first time the Workshop runs (Settings can turn that off).

// ----- the Help menu at the top
$('#helpbtn').onclick = e => { e.stopPropagation(); const m = $('#helpmenu'); m.style.display = m.style.display === 'block' ? 'none' : 'block'; };
document.addEventListener('click', e => { if (!e.target.closest('#helpmenu')) $('#helpmenu').style.display = 'none'; });
$('#helpmenu').addEventListener('click', e => {
  const b = e.target.closest('[data-help]'); if (!b) return;
  $('#helpmenu').style.display = 'none';
  const a = b.dataset.help;
  if (a === 'guide' || a === 'settings') showView(a);
  else if (a === 'report') reportModal();
  else if (a === 'about') aboutModal();
});
const HELP_KEY = s => `<kbd>${s}</kbd>`;
function helpGo(view){ return `<button class="btn sm" data-gview="${view}">Open ${{world: 'the World map', createv: 'Create', dialog: 'Dialogue', mymod: 'My mod', plugins: 'Load order', settings: 'Settings', chars: 'Characters'}[view] || view}</button>`; }

// ----- the guide
function renderGuide(){
  const s = S.summary || {}, p = s.project;
  try { post('/api/settings', {guide_seen: true}); } catch (e) {}
  $('#guidewrap').innerHTML = `
  <h1>Getting started</h1>
  <p class="lead">Morrowind Workshop is an easy, modern editor for making Morrowind mods with <b>OpenMW</b>. You build and furnish places,
    add people, items, books, dialogue and quests, and try it all in the running game, where your changes appear as you make them.</p>

  <div class="gcards">
    <div class="gcard"><b>1 · It reads your game</b><p>The Workshop reads OpenMW's own settings, so it sees your Morrowind files and the mods you have switched on,
      in the same order as the game. It never changes your game files: your work goes into a mod file of your own.</p></div>
    <div class="gcard"><b>2 · Start a mod</b><p>Press <b>＋ Start a mod</b> at the top and give it a name. Everything you make or change from then on
      is saved into it straight away. There's no Save button, and <b>Undo</b> (${HELP_KEY('Ctrl+Z')}) takes back the last change.</p>
      ${p ? `<p class="msg">You're working on <b>${esc(p.name)}</b>.</p>` : '<button class="btn sm primary" onclick="projectModal()">＋ Start a mod</button>'}</div>
    <div class="gcard"><b>3 · Try it in the game</b><p><b>▶ OpenMW → Start the game</b> at the top, or <b>Play here</b> on the World map, starts OpenMW
      with your mod and the <b>live link</b>: what you change in the Workshop appears in the game within a second.</p></div>
  </div>

  <h2>Finding your way</h2>
  <table class="t gtable">
    <tr><td><b>Browse</b></td><td>Every record in your game: search anything (names, IDs, dialogue, models) and click to see it, with links between records.
      <b>▦ Table</b> shows columns you choose and sort; <b>📌</b> pins a record in its own panel to compare it with others.</td></tr>
    <tr><td><b>World map</b></td><td>Places in 2D or 3D. Drag things in from the Place panel, click to select, drag to move. In 3D: right-drag to look,
      ${HELP_KEY('W')}${HELP_KEY('A')}${HELP_KEY('S')}${HELP_KEY('D')} to fly, ${HELP_KEY('G')} move, ${HELP_KEY('R')} turn; <b>View ▾</b> has a grid and wireframe; <b>?</b> lists every control.
      Outdoors, <b>⛰ Ground</b> shapes and paints the land and scatters grass and plants.</td></tr>
    <tr><td><b>Create</b></td><td>New people, creatures, items, books and spells, or a whole interior built from wall and floor pieces, which <b>Auto-furnish</b> can fill.</td></tr>
    <tr><td><b>Characters</b></td><td>People and creatures: looks, stats, what they sell, where they stand.</td></tr>
    <tr><td><b>Dialogue</b></td><td>Greetings, topics and quests with their journal stages. Lines can depend on quest stages, items and more.</td></tr>
    <tr><td><b>Scripts</b></td><td>Morrowind scripts and OpenMW Lua scripts, checked as you type.</td></tr>
    <tr><td><b>Rules</b></td><td>Factions, classes, races, birthsigns, regions and weather, global variables and game settings.</td></tr>
    <tr><td><b>My mod</b></td><td>What your mod contains, and <b>Get ready to share</b>: checks it, writes a readme and packs a zip.</td></tr>
    <tr><td><b>Health check</b></td><td>Problems in your load order or your mod, like missing masters, models or textures.</td></tr>
    <tr><td><b>Load order</b></td><td>Switch plugins on or off and change their order (saved to OpenMW's settings, with a backup).</td></tr>
  </table>

  <h2>Working faster</h2>
  <ul class="glist">
    <li><b>Panels:</b> every page's tools are panels. Drag a tab to move it, dock it on a side or tab it with others; drag the edges to resize; ⋮ to float or close it.
      <b>▤ Panels</b> opens any panel and has ready-made layouts, and you can save your own.</li>
    <li>${HELP_KEY('Ctrl+K')} finds any command, page, panel, place or record. ${HELP_KEY('Ctrl+/')} lets you change the keyboard shortcuts.</li>
    <li><b>Right-click</b> anything on the World map, in 3D or in a list for what you can do with it. The bar under the map shows the place, the mouse or camera position, and what's selected (click a position to copy it).</li>
    <li>${HELP_KEY('F1')} on something shows <b>where it's used</b>: the places it stands in, who carries it, the scripts and dialogue that name it.</li>
    <li>Your mod's changes are marked on the map: green new, gold changed, a red ✕ where you took something out (right-click it to bring it back). <b>My changes</b> lists them all.</li>
    <li>${HELP_KEY('H')} hides what's selected so you can get at what's behind, ${HELP_KEY('Shift+H')} hides everything else, ${HELP_KEY('Alt+H')} shows it all again.</li>
    <li>Select a door and press ${HELP_KEY('Enter')} to go through it; ${HELP_KEY('Alt+←')} comes back. ${HELP_KEY('Ctrl+H')} replaces every one of an object with another.</li>
    <li><b>👤 Play as</b> (by Play here) starts the game as one of your own characters, from their latest save, at the spot you pick. <b>🧪 Test setups</b> add items, spells, quest stages or variables on top.</li>
    <li><b>Settings → Appearance</b> has themes and your own colours.</li>
  </ul>

  <h2>Playing with the live link</h2>
  <p>While the game runs from the Workshop, the top shows <b>● Game linked</b>. Then:</p>
  <ul class="glist">
    <li>Edits you make in the Workshop appear in the game. Brand-new places and records need a restart of the game.</li>
    <li><b>⌖ Jump to my character</b> shows where you are on the map; <b>Follow my character</b> on the map keeps up with you.</li>
    <li>On the Dialogue page you can set quest stages, give items and change variables in the running game, and see which conditions are true right now.</li>
    <li>In the game, hold ${HELP_KEY('Shift')}: ${HELP_KEY('B')} build menu · ${HELP_KEY('J')} place the chosen object · ${HELP_KEY('G')} grab and move what you look at (mouse wheel turns it) ·
      ${HELP_KEY('K')} select it in the Workshop · ${HELP_KEY('Delete')} remove it · ${HELP_KEY('Z')} undo · ${HELP_KEY('X')} cancel.</li>
    <li>A game started from OpenMW's own Launcher isn't linked (the top says <b>○ Game not linked</b>): start it from the Workshop instead.</li>
  </ul>

  <h2>Sharing your mod</h2>
  <p>Open <b>My mod → Get ready to share</b>. It checks the mod, lists the other mods it needs, writes a readme and makes a zip you can upload,
    for example to Nexus Mods. <b>Start a clean test</b> (step 3 there) starts the game with only the base game and your mod's requirements, to see it as others will.</p>

  <h2>The AI assistant (optional)</h2>
  <p>The <b>✦ Assistant</b> button opens a helper you can ask in plain words ("furnish this room like a poor fisherman's hut"). It uses Claude, Anthropic's AI,
    with <b>your own Anthropic API key</b>, and each request is billed to your Anthropic account: usually a few cents, up to about half a dollar for a big job.
    Everything else in the Workshop works without it.</p>

  <h2>If something goes wrong</h2>
  <ul class="glist">
    <li><b>Undo</b> takes back changes one by one. The Workshop also keeps <b>automatic backups</b> of your mod (Settings → Backups), and can restore any of them.</li>
    <li><b>? Help → Report a problem</b> makes a report with the details needed to fix it, ready to copy and send.</li>
    <li>Your work is kept in the Workshop's <b>projects</b> folder; the mod file the game loads goes into OpenMW's data folder.</li>
  </ul>

  <div class="actions" style="margin-top:18px">${helpGo('world')}${helpGo('createv')}${helpGo('settings')}
    <label class="msg" style="display:inline-flex;gap:6px;align-items:center;margin-left:8px"><input type="checkbox" id="g-onstart"> Show this page every time the Workshop starts</label></div>`;
  api('/api/settings').then(st => { const c = $('#g-onstart'); if (c){ c.checked = st.guide_on_start; c.onchange = () => post('/api/settings', {guide_on_start: c.checked}); } }).catch(() => {});
}
document.addEventListener('click', e => { const g = e.target.closest('[data-gview]'); if (g) showView(g.dataset.gview); });

// ----- settings
async function renderSettings(){
  const w = $('#settingswrap');
  let st, bk;
  try { st = await api('/api/settings'); bk = await api('/api/backups'); }
  catch (e){ w.innerHTML = `<h1>Settings</h1><div class="msg err">${esc(e.message)}</div>`; return; }
  const p = S.summary && S.summary.project;
  const when = t => new Date(t * 1000).toLocaleString();
  w.innerHTML = `<h1>Settings</h1>${typeof thSection === 'function' ? thSection() : ''}
  <section class="card setsec"><h3>OpenMW</h3>
    <div class="setrow"><span>Installed in</span><b>${st.openmw_install ? esc(st.openmw_install) : '<span style="color:var(--amber)">not found</span>'}</b></div>
    <div class="setrow"><span>Its settings (load order)</span><span class="msg">${esc(st.openmw_cfg || '')}</span></div>
    <div class="actions"><button class="btn sm" id="st-pick">Choose OpenMW's folder…</button>
      ${st.openmw_chosen ? '<button class="btn sm" id="st-auto" title="Forget the chosen folder and look for OpenMW by itself">Find it automatically</button>' : ''}
      <button class="btn sm" data-open="openmw">Open OpenMW's settings folder</button></div></section>

  <section class="card setsec"><h3>AI assistant</h3>
    <p class="msg">Optional. It uses Claude, Anthropic's AI, with your own Anthropic API key; each request is billed to your Anthropic account
      (usually a few cents, up to about half a dollar for a big job). What you ask, and details about the place and records it works with, are sent to Anthropic.</p>
    <div class="setrow"><span>API key</span><b>${st.ai_configured ? `saved, ends in …${esc(st.ai_key_end)}${st.ai_from_env ? ' (from the ANTHROPIC_API_KEY setting on this PC)' : ''}` : 'none'}</b></div>
    <div class="actions"><input class="inp" id="st-key" type="password" placeholder="Paste a new key: sk-ant-…" style="max-width:320px" autocomplete="off">
      <button class="btn sm" id="st-savekey">Save key</button>${st.ai_configured && !st.ai_from_env ? '<button class="btn sm danger" id="st-delkey">Remove key</button>' : ''}
      <a class="btn sm" href="https://console.anthropic.com/settings/keys" target="_blank" rel="noopener">Get a key</a></div>
    <p class="msg" style="font-size:12px">The key is stored only on this PC, in the Workshop's folder.</p></section>

  <section class="card setsec"><h3>Backups of your mod</h3>
    <p class="msg">The Workshop copies your mod's project file when you open it and then regularly while you work, and keeps the newest ones.</p>
    <div class="setrow"><span>Make a backup every</span><span><input class="inp num" id="st-bmin" type="number" min="1" max="240" value="${st.backup_minutes}" style="width:70px"> minutes while you work</span></div>
    <div class="setrow"><span>Keep the newest</span><span><input class="inp num" id="st-bkeep" type="number" min="1" max="500" value="${st.backup_keep}" style="width:70px"> backups of each mod</span></div>
    ${p ? `<h4 style="margin:14px 0 6px">Backups of ${esc(p.name)} (${bk.backups.length})</h4>
      <div class="bklist">${bk.backups.map(b => `<div class="setrow"><span>${esc(when(b.time))}${b.why ? ` <span class="chip">${esc(b.why)}</span>` : ''}</span>
        <span><span class="msg">${fmtN(Math.round(b.size / 1024))} KB</span> <button class="btn sm" data-restore="${esc(b.file)}">Restore</button></span></div>`).join('')
        || '<div class="msg">None yet.</div>'}</div>` : '<p class="msg">Open a mod to see its backups.</p>'}
    <div class="actions"><button class="btn sm" data-open="backups">Open the backups folder</button></div></section>

  <section class="card setsec"><h3>Starting up</h3>
    <label style="display:flex;gap:8px;align-items:center"><input type="checkbox" id="st-guide" ${st.guide_on_start ? 'checked' : ''}> Show the Getting started page every time the Workshop starts (it always opens the first time)</label></section>

  <section class="card setsec"><h3>Folders</h3>
    <div class="setrow"><span>Your projects</span><span class="msg">${esc(st.projects_folder)}</span></div>
    <div class="setrow"><span>The Workshop</span><span class="msg">${esc(st.app_folder)} · version ${esc(st.version)}</span></div>
    <div class="actions"><button class="btn sm" data-open="projects">Open the projects folder</button><button class="btn sm" data-open="app">Open the Workshop's folder</button></div></section>`;

  if (typeof thBind === 'function') thBind(w);
  const save = body => post('/api/settings', body).then(() => toast('Saved.')).catch(e => toast(e.message, true));
  $('#st-pick').onclick = async () => { try { toast('Choose OpenMW\'s folder in the window that opens…'); const r = await post('/api/openmw/pick', {}); if (r.ok){ toast('Using OpenMW in ' + r.install + '. Reading your game again…'); setTimeout(poll, 300); } } catch (e){ toast(e.message, true); } };
  const auto = $('#st-auto'); if (auto) auto.onclick = async () => { await post('/api/settings', {openmw_reset: true}); toast('Looking for OpenMW by itself. Reading your game again…'); setTimeout(poll, 300); };
  $('#st-savekey').onclick = async () => { const k = $('#st-key').value.trim(); if (!k) return; await post('/api/ai/key', {key: k}); AI.configured = true; toast('Key saved.'); renderSettings(); };
  const dk = $('#st-delkey'); if (dk) dk.onclick = async () => { if (!confirm('Remove the saved API key?')) return; await post('/api/ai/key', {key: ''}); AI.configured = false; renderSettings(); };
  $('#st-bmin').onchange = e => save({backup_minutes: +e.target.value});
  $('#st-bkeep').onchange = e => save({backup_keep: +e.target.value});
  $('#st-guide').onchange = e => save({guide_on_start: e.target.checked});
  w.querySelectorAll('[data-open]').forEach(b => b.onclick = () => post('/api/open_place', {what: b.dataset.open}).catch(e => toast(e.message, true)));
  w.querySelectorAll('[data-restore]').forEach(b => b.onclick = async () => {
    const f = b.dataset.restore;
    if (!confirm(`Put your mod back to how it was in this backup?\n\n${f}\n\nHow it is now is backed up first, so you can come back to it.`)) return;
    try { await post('/api/backups/restore', {file: f}); toast('Restored. Reading your mod again…'); setTimeout(poll, 300); }
    catch (e){ toast(e.message, true); }
  });
}

// ----- report a problem
function reportModal(){
  const bg = document.createElement('div'); bg.className = 'modal-bg';
  bg.innerHTML = `<div class="modal" style="width:min(640px,94vw)"><h2>Report a problem</h2>
    <div class="msg">This makes a report with what's needed to look into it: the Workshop and OpenMW versions, your setup, and the end of both logs.
      Your Windows user name is left out, and your API key is never included.</div>
    <label>What happened? What did you do just before?</label>
    <textarea class="inp" id="rp-what" style="min-height:90px" placeholder="e.g. I pressed Auto-furnish in a Dres house and nothing appeared."></textarea>
    <div id="rp-out"></div>
    <div class="foot"><button class="btn" id="rp-close">Close</button><button class="btn primary" id="rp-make">Make the report</button></div></div>`;
  document.body.appendChild(bg);
  $('#rp-close').onclick = () => bg.remove();
  $('#rp-make').onclick = async () => {
    try {
      const r = await post('/api/report', {what: $('#rp-what').value});
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
async function aboutModal(){
  let a;
  try { a = await api('/api/about'); } catch (e){ return toast(e.message, true); }
  const bg = document.createElement('div'); bg.className = 'modal-bg';
  bg.innerHTML = `<div class="modal" style="width:min(680px,94vw);max-height:86vh;overflow:auto"><h2>Morrowind Workshop</h2>
    <div class="msg">Version <b>${esc(a.version)}</b> · OpenMW ${esc(a.openmw)} · Python ${esc(a.python)}</div>
    <p class="msg" style="line-height:1.6">An editor for Morrowind mods with OpenMW. Not made by or affiliated with Bethesda Softworks or the OpenMW project.
      Morrowind is a trademark of Bethesda Softworks / ZeniMax Media; the Workshop includes none of its files, it reads the ones you own.</p>
    <h3 style="margin-top:12px">Built with</h3>
    <table class="t" style="font-size:12.5px">${a.components.map((c, n) => `<tr><td><b>${esc(c.name)}</b> ${esc(c.version)}${c.by ? `<div class="msg">${esc(c.by)}</div>` : ''}</td>
      <td>${esc(c.license)}${c.text ? ` · <span class="lnk" data-lic="${n}">read</span>` : ''}</td>
      <td>${c.url ? `<a href="${esc(c.url)}" target="_blank" rel="noopener">website</a>` : ''}</td></tr>`).join('')}</table>
    <pre id="ab-lic" class="code" style="display:none;white-space:pre-wrap;font-size:11.5px;max-height:260px;overflow:auto;background:var(--panel2);padding:10px;border-radius:8px"></pre>
    <div class="msg" style="margin-top:8px">The full notices are in THIRD_PARTY_NOTICES.txt in the Workshop's folder.</div>
    <div class="foot"><button class="btn primary" id="ab-close">Close</button></div></div>`;
  document.body.appendChild(bg);
  $('#ab-close').onclick = () => bg.remove();
  bg.querySelectorAll('[data-lic]').forEach(l => l.onclick = () => { const pre = $('#ab-lic'); pre.textContent = a.components[+l.dataset.lic].text; pre.style.display = 'block'; pre.scrollIntoView({block: 'nearest'}); });
}

// ----- the assistant, the first time it's opened: what it is, what it costs, what it sends
function aiNoticeHtml(){
  return `<div class="ai-msg bot"><b>Before you use the assistant</b>
The assistant is optional: everything else in the Workshop works without it.

• <b>It costs money.</b> It uses Claude, Anthropic's AI, through <b>your own Anthropic API account</b>. Each request is billed to that account: usually a few cents, a big job like furnishing a whole house up to about half a dollar. You set up the account and its spending limits on console.anthropic.com.
• <b>What is sent.</b> What you ask, plus details about the place, records and objects it works with, go to Anthropic to be answered. Nothing is sent until you ask something.
• <b>Check its work.</b> It can make mistakes. Everything it does goes into your mod like your own edits, and <b>Undo</b> takes it back.</div>
    <div class="actions"><button class="btn primary" id="ai-ack">Got it</button></div>`;
}
function bindAiNotice(){
  const b = $('#ai-ack'); if (!b) return;
  b.onclick = async () => { AI.ack = true; try { await post('/api/settings', {ai_ack: true}); } catch (e) {} renderAI(); };
}

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
      AI.ack = st.ai_ack;
      if (location.hash.length > 1) await openFromLink(location.hash);
      else if (!st.guide_seen || st.guide_on_start) showView('guide');
    } catch (e){ console.warn(e); }
  }, 700);
})();
window.addEventListener('hashchange', () => { if (S.summary && S.summary.state === 'ready') openFromLink(location.hash); });
