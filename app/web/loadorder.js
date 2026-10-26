// ---------- load order (OpenMW's content list in openmw.cfg), editable ----------
// Tick to switch plugins on or off, drag (or ↑ ↓) to change the order, then Save. Saving writes
// openmw.cfg (after a backup) and reads the game data again in the new order.
const LO = {info: null, order: [], off: [], dirty: false, problems: [], drag: null, checkT: null};

async function loadPlugins(){
  const box = $('#pluginwrap'); if (!box) return;
  if (!H){ try { H = await api('/api/health'); } catch (e){} }      // (for each plugin's record counts)
  try { LO.info = await api('/api/loadorder'); }
  catch (e){ box.innerHTML = `<h1>Load order</h1><div class="msg err">${esc(e.message)}</div>`; return; }
  LO.order = LO.info.enabled.map(r => r.name);
  LO.off = LO.info.available.map(r => r.name);
  LO.problems = LO.info.problems; LO.dirty = false;
  loRender();
}
function loRow(name){
  const all = LO.info.enabled.concat(LO.info.available);
  return all.find(r => r.name.toLowerCase() === name.toLowerCase()) || {name, found: false, masters: [], kind: ''};
}
function loStats(name){
  // records new / changed, from the loaded game data (only for plugins that are loaded)
  const P = (H && H.plugins) || [];
  return P.find(p => p.name.toLowerCase() === name.toLowerCase());
}
function loRender(){
  const box = $('#pluginwrap'); if (!box || !LO.info) return;
  const I = LO.info;
  const probs = {};
  for (const p of LO.problems) (probs[p.plugin.toLowerCase()] = probs[p.plugin.toLowerCase()] || []).push(p.text);
  const orderProblem = LO.problems.some(p => p.text.includes('loads after it'));
  let h = `<h1>Load order</h1>
    <p class="lead">Your OpenMW content list, top to bottom. Files lower in the list win when two of them change the same thing.
      Tick to switch a plugin on or off, drag it (or use ↑ ↓) to move it, then <b>Save</b>. Click a name to browse what it adds or changes.</p>
    ${!I.cfg_exists ? `<div class="card msg err" style="margin-bottom:12px">OpenMW's settings file wasn't found (${esc(I.cfg || '')}). Run the OpenMW Launcher once, so it sets up Morrowind, then press Reload.</div>` : ''}
    <div class="lobar">
      <button class="btn primary" id="lo-save" ${LO.dirty ? '' : 'disabled'}>Save load order</button>
      <button class="btn" id="lo-revert" ${LO.dirty ? '' : 'disabled'}>Undo my changes</button>
      ${orderProblem ? '<button class="btn" id="lo-fix" title="Move plugins only as far as needed so every master loads before what needs it">Fix master order</button>' : ''}
      <span class="msg">${LO.dirty ? 'Not saved yet.' : `Saved in OpenMW's <span title="${esc(I.cfg || 'openmw.cfg')}" style="cursor:help;border-bottom:1px dotted var(--faint)">openmw.cfg</span>. Each save makes a backup first.`}</span>
    </div>
    <table class="t lot"><tr><th style="width:26px"></th><th style="width:30px">On</th><th>#</th><th>Plugin</th><th>Author / description</th><th style="text-align:right">New</th><th style="text-align:right">Changes</th><th style="width:70px"></th></tr>`;
  LO.order.forEach((name, n) => {
    const r = loRow(name), st = loStats(name), hd = (st && st.header) || {};
    const desc = [hd.author, hd.description].filter(Boolean).join(' — ');
    const pi = (H && H.plugins || []).findIndex(p => p.name.toLowerCase() === name.toLowerCase());
    const lua = r.kind === 'omwscripts';
    h += `<tr class="lorow" draggable="true" data-lo="${n}">
      <td class="lohandle" title="Drag to move">⠿</td>
      <td><input type="checkbox" checked data-lotoggle="${esc(name)}" title="Switch off"></td>
      <td class="num">${n + 1}</td>
      <td>${pi >= 0 && !lua && !LO.dirty ? `<span class="lnk" data-plug="${pi}">${esc(r.name)}</span>` : esc(r.name)}
        ${lua ? ' <span class="chip">Lua scripts</span>' : ''}${r.mine ? ' <span class="chip" style="color:var(--gold2)">your mod</span>' : ''}
        ${(probs[name.toLowerCase()] || []).map(x => `<div class="prob">⚠ ${esc(x)}</div>`).join('')}
        ${r.masters && r.masters.length ? `<div style="font-size:11.5px;color:var(--faint)">needs: ${r.masters.map(esc).join(', ')}</div>` : ''}</td>
      <td style="color:var(--muted);font-size:12.5px;max-width:380px">${esc(desc).slice(0, 260)}</td>
      <td class="num">${st && !lua ? fmtN(st.new) : ''}</td><td class="num">${st && !lua ? fmtN(st.overrides) : ''}</td>
      <td style="white-space:nowrap"><button class="btn sm" data-lomove="${n},-1" ${n ? '' : 'disabled'} title="Load earlier">↑</button><button class="btn sm" data-lomove="${n},1" ${n < LO.order.length - 1 ? '' : 'disabled'} title="Load later">↓</button>${loMenuBtn(r, pi)}</td></tr>`;
  });
  h += `</table>`;
  if (LO.off.length){
    h += `<h3 style="margin-top:22px">Installed but switched off</h3><div class="msg" style="margin-bottom:6px">In your data folders, but not in the load order. Tick one to add it at the bottom.</div>
      <table class="t lot">${LO.off.map(name => {
        const r = loRow(name);
        return `<tr><td style="width:30px"><input type="checkbox" data-lotoggle="${esc(name)}" title="Switch on"></td><td>${esc(r.name)}${r.kind === 'omwscripts' ? ' <span class="chip">Lua scripts</span>' : ''}${r.mine ? ' <span class="chip" style="color:var(--gold2)">your mod</span>' : ''}
          ${r.masters && r.masters.length ? `<div style="font-size:11.5px;color:var(--faint)">needs: ${r.masters.map(esc).join(', ')}</div>` : ''}</td><td class="msg" style="font-size:12px">${esc(r.folder || '')}</td><td style="width:40px;text-align:right">${loMenuBtn(r, -1)}</td></tr>`;
      }).join('')}</table>`;
  }
  box.innerHTML = h;
  const save = $('#lo-save'); if (save) save.onclick = loSave;
  const rev = $('#lo-revert'); if (rev) rev.onclick = loadPlugins;
  const fix = $('#lo-fix'); if (fix) fix.onclick = async () => {
    let r;
    try { r = await post('/api/loadorder/check', {order: LO.order}); }
    catch (e){ toast(e.loading ? 'Still loading the game files: try again in a moment.' : e.message, !e.loading); return; }
    LO.order = r.sorted; loChanged();
  };
}
// the ⋯ menu of a plugin row: open the file as your mod (a .esp or .omwaddon that isn't your mod already;
// adopt.py), browse what it adds
function loMenuBtn(r, pi){
  if (!r.found || !['esp', 'omwaddon'].includes(r.kind) || r.mine) return '';
  const path = (r.folder || '') + '\\' + r.name;
  return `<span style="position:relative;display:inline-block"><button class="btn sm" data-lomenu="${esc(r.name)}" title="More…">⋯</button>
    <div class="omwmenu lomenu" data-lomenu-for="${esc(r.name)}">
      <button data-loadopt="${esc(path)}"><b>Set as active file (open this ${esc(r.kind === 'esp' ? '.esp' : '.omwaddon')} as your mod)…</b><small>As in the Construction Set: the file itself becomes the mod you work on, and every change is saved back into it.</small></button>
      ${pi >= 0 ? `<button data-plug="${pi}"><b>Browse what it adds or changes</b></button>` : ''}
    </div></span>`;
}
document.addEventListener('click', e => {
  const b = e.target.closest('[data-lomenu]');
  document.querySelectorAll('.lomenu').forEach(m => { if (!b || m.dataset.lomenuFor !== b.dataset.lomenu) m.style.display = 'none'; });
  if (b){
    const m = document.querySelector(`.lomenu[data-lomenu-for="${CSS.escape(b.dataset.lomenu)}"]`);
    if (m) m.style.display = m.style.display === 'block' ? 'none' : 'block';
    e.stopPropagation();
  }
});
function loChanged(){
  LO.dirty = true;
  loRender();
  clearTimeout(LO.checkT);
  LO.checkT = setTimeout(async () => {
    try { LO.problems = (await post('/api/loadorder/check', {order: LO.order})).problems; loRender(); } catch (e){}
  }, 250);
}
async function loSave(){
  if (LO.problems.length && !confirm('Some plugins have problems in this order:\n\n' +
      LO.problems.slice(0, 6).map(p => '• ' + p.plugin + ': ' + p.text).join('\n') + '\n\nSave anyway?')) return;
  try {
    const r = await post('/api/loadorder/save', {order: LO.order});
    const game = r.game_running ? ' The game that is running now keeps the old order until it restarts.' : '';
    LO.dirty = false;
    if (r.mode === 'added'){
      // only switched on at the end: read just those and add them, no loading screen
      toast(`Load order saved (${r.count} plugins). Adding ${r.added.join(', ')}…` + game);
      loWaitAdd();
    } else {
      toast(`Load order saved (${r.count} plugins). A backup of the old one was made. Reading your game data again…` + game);
      setTimeout(poll, 300);
    }
  } catch (e){ toast(e.message, true); }
}
// Plugins are being added to what is loaded (the end of the load order changed): wait for it, say
// what was added, and refresh the counts, the Health check and this page.
async function loWaitAdd(){
  let s;
  try { s = await api('/api/status'); } catch (e){ setTimeout(loWaitAdd, 800); return; }
  if (s.state !== 'ready'){ poll(); return; }            // (it fell back to reading everything again)
  if (s.adding){
    const p = s.progress || {};
    $('#stat').textContent = p.step && p.step !== 'Done' ? p.step : 'Adding ' + s.adding.join(', ') + '…';
    setTimeout(loWaitAdd, 300); return;
  }
  S.summary = s;
  $('#stat').textContent = fmtN(s.records) + ' records';
  const a = s.last_add;
  if (a) toast(`Added ${a.names.join(', ')} (${fmtN(a.records)} record${a.records === 1 ? '' : 's'}, ${a.seconds} s).`);
  s.types.forEach(g => g.types.forEach(t => S.typeLabels[t.tag] = t.label));
  loadProblemsNote(s);
  H = null;
  buildSide(); runSearch(); loadHealth(); loadPlugins(); renderProjectPill();
}
// clicks: browse a plugin, switch on/off, move
$('#pluginwrap').addEventListener('click', e => {
  const ad = e.target.closest('[data-loadopt]');
  if (ad){ document.querySelectorAll('.lomenu').forEach(m => m.style.display = 'none'); adoptModal(ad.dataset.loadopt); return; }
  const p = e.target.closest('[data-plug]');
  if (p){ S.plugin = p.dataset.plug; S.types = []; buildSide(); showView('browse'); runSearch(); return; }
  const m = e.target.closest('[data-lomove]');
  if (m){
    const [n, d] = m.dataset.lomove.split(',').map(Number), to = n + d;
    if (to < 0 || to >= LO.order.length) return;
    LO.order.splice(to, 0, LO.order.splice(n, 1)[0]); loChanged();
  }
});
$('#pluginwrap').addEventListener('change', e => {
  const t = e.target.closest('[data-lotoggle]'); if (!t) return;
  const name = t.dataset.lotoggle;
  if (t.checked){ LO.off = LO.off.filter(x => x !== name); LO.order.push(name); }
  else { LO.order = LO.order.filter(x => x !== name); LO.off.push(name); LO.off.sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase())); }
  loChanged();
});
// dragging rows
$('#pluginwrap').addEventListener('dragstart', e => {
  const r = e.target.closest('[data-lo]'); if (!r) return;
  LO.drag = +r.dataset.lo; e.dataTransfer.effectAllowed = 'move'; r.classList.add('dragging');
});
$('#pluginwrap').addEventListener('dragover', e => {
  const r = e.target.closest('[data-lo]'); if (!r || LO.drag === null) return;
  e.preventDefault();
  document.querySelectorAll('.lorow.over').forEach(x => x.classList.remove('over'));
  r.classList.add('over');
});
$('#pluginwrap').addEventListener('drop', e => {
  const r = e.target.closest('[data-lo]'); if (!r || LO.drag === null) return;
  e.preventDefault();
  const to = +r.dataset.lo, from = LO.drag; LO.drag = null;
  if (to !== from){ LO.order.splice(to, 0, LO.order.splice(from, 1)[0]); loChanged(); } else loRender();
});
$('#pluginwrap').addEventListener('dragend', () => { LO.drag = null; document.querySelectorAll('.lorow').forEach(x => x.classList.remove('over', 'dragging')); });

// ---------- the OpenMW button at the top ----------
let OMW = null;
async function omwRefresh(){ try { OMW = await api('/api/openmw'); } catch (e){ OMW = null; } omwRender(); }
function omwRender(){
  const m = $('#omwmenu'); if (!m) return;
  const found = OMW && OMW.found;
  m.innerHTML = found
    ? `<button data-omw="menu"><b>▶ Start the game</b><small>To the main menu, with your load order${S.summary && S.summary.project ? ' and your mod' : ''}. The live link connects too.</small></button>
       <button data-omw="here"><b>Start in a place…</b><small>Pick a spot on the World map ("Play here").</small></button>
       ${OMW.launcher ? '<button data-omw="launcher"><b>OpenMW Launcher</b><small>OpenMW\'s own settings, mods and data files.</small></button>' : ''}
       <button data-omw="order"><b>Load order…</b><small>Switch plugins on or off and change their order.</small></button>
       <button data-omw="opts"><b>Game start options…</b><small>Controller in the background, your own options, or choose each time.</small></button>
       <button data-omw="settings"><b>OpenMW settings…</b><small>Graphics, shadows, the game's options: every setting, with what it does.</small></button>
       <button data-omw="settingscfg"><b>Open settings.cfg</b><small>OpenMW's settings file, in your text editor.</small></button>
       <div class="omwfoot">OpenMW: ${esc(OMW.install)} · <span class="lnk" data-omw="pick">change</span></div>`
    : `<div class="omwfoot" style="border:0">OpenMW wasn't found on this computer.</div>
       <button data-omw="pick"><b>Choose OpenMW's folder…</b><small>The folder with openmw.exe in it.</small></button>
       <button data-omw="get"><b>Get OpenMW</b><small>openmw.org (free). Install it, run its Launcher once, then come back.</small></button>`;
  const b = $('#omwbtn'); if (b) b.classList.toggle('warn', !found);
}
$('#omwbtn').onclick = e => { e.stopPropagation(); if (typeof topMenusClose === 'function') topMenusClose('omwmenu'); const m = $('#omwmenu'); const show = m.style.display !== 'block'; m.style.display = show ? 'block' : 'none'; if (show) omwRefresh(); };
document.addEventListener('click', e => { if (!e.target.closest('#omwmenu')) $('#omwmenu').style.display = 'none'; });
$('#omwmenu').addEventListener('click', async e => {
  const b = e.target.closest('[data-omw]'); if (!b) return;
  const a = b.dataset.omw; $('#omwmenu').style.display = 'none';
  try {
    if (a === 'menu'){ if (await gameStart('/api/openmw/start', {mode: 'menu'})) toast('Starting OpenMW…'); }
    else if (a === 'opts') launchModal();
    else if (a === 'settings') omsShow();
    else if (a === 'settingscfg'){ const r = await post('/api/openmw/settings/open', {}); toast('Opening ' + r.path + '…'); }
    else if (a === 'launcher'){ await post('/api/openmw/start', {mode: 'launcher'}); toast('Opening OpenMW\'s Launcher…'); }
    else if (a === 'here'){ showView('world'); toast('Open a place on the map, then press "Play here" (or "Pick a spot") in the Place panel.'); }
    else if (a === 'order') showView('plugins');
    else if (a === 'get') window.open('https://openmw.org/downloads/', '_blank');
    else if (a === 'pick'){
      toast('Choose OpenMW\'s folder in the window that opens…');
      const r = await post('/api/openmw/pick', {});
      if (r.ok){ toast('Using OpenMW in ' + r.install + '. Reading your game data…'); setTimeout(poll, 300); }
    }
  } catch (err){ toast(err.message, true); }
});
omwRefresh();

// ---------- OpenMW's own settings (settings.cfg): the popular ones first, every one searchable ----------
const OMS = {d: null, tab: 'popular', q: '', edits: {}};
async function omsShow(){
  let d;
  try { d = await api('/api/openmw/settings'); } catch (e){ return toast(e.message, true); }
  OMS.d = d; OMS.edits = {};
  const bg = document.createElement('div'); bg.className = 'modal-bg'; OMS.bg = bg;
  bg.innerHTML = `<div class="modal" style="width:min(820px,96vw);max-height:90vh;display:flex;flex-direction:column"><h2>OpenMW settings</h2>
    <div class="msg">In ${esc(d.path)}${d.exists ? '' : ' (not made yet: OpenMW makes it the first time you change a setting)'}. Only what you change from OpenMW's own defaults is written there.</div>
    ${d.running ? '<div class="msg err" style="margin-top:4px">The game is running: close it first, as OpenMW writes this file again when it quits.</div>' : ''}
    ${d.defaults_found ? '' : '<div class="msg err" style="margin-top:4px">OpenMW\'s list of settings (defaults.bin) wasn\'t found in its folder. Open settings.cfg to change it by hand.</div>'}
    <div style="display:flex;gap:6px;align-items:center;margin:8px 0">
      <button class="btn sm" data-omst="popular">Popular</button><button class="btn sm" data-omst="all">All settings</button><button class="btn sm" data-omst="changed">Changed</button>
      <input class="inp" id="oms-q" placeholder="Search settings and what they do…" style="flex:1" autocomplete="off"></div>
    <div id="oms-list" style="flex:1;overflow:auto;min-height:200px;border:1px solid var(--line);border-radius:8px;padding:4px 8px"></div>
    <div class="foot"><button class="btn" id="oms-file" title="settings.cfg in your text editor">Open settings.cfg</button><span class="msg" id="oms-msg" style="flex:1"></span>
      <button class="btn" id="oms-close">Close</button><button class="btn primary" id="oms-save" disabled>Save changes</button></div></div>`;
  document.body.appendChild(bg);
  const q = s => bg.querySelector(s);
  bg.querySelectorAll('[data-omst]').forEach(b => b.onclick = () => { OMS.tab = b.dataset.omst; omsDraw(); });
  q('#oms-q').oninput = e => { OMS.q = e.target.value; if (OMS.q && OMS.tab === 'popular') OMS.tab = 'all'; omsDraw(); };
  q('#oms-close').onclick = () => { if (Object.keys(OMS.edits).length && !confirm('Close without saving your changes?')) return; bg.remove(); };
  q('#oms-file').onclick = async () => { try { const r = await post('/api/openmw/settings/open', {}); toast('Opening ' + r.path + '…'); } catch (e){ toast(e.message, true); } };
  q('#oms-save').onclick = omsSave;
  omsDraw();
}
function omsKey(r){ return r.section + '|' + r.key; }
function omsDraw(){
  const d = OMS.d, box = OMS.bg && OMS.bg.querySelector('#oms-list'); if (!box) return;
  OMS.bg.querySelectorAll('[data-omst]').forEach(b => b.classList.toggle('primary', b.dataset.omst === OMS.tab));
  const by = {}; d.settings.forEach(r => { by[omsKey(r).toLowerCase()] = r; });
  let rows;
  if (OMS.tab === 'popular') rows = d.popular.map(([s, k]) => by[(s + '|' + k).toLowerCase()]).filter(Boolean);
  else if (OMS.tab === 'changed') rows = d.settings.filter(r => r.changed || OMS.edits[omsKey(r)] != null);
  else rows = d.settings;
  const ql = OMS.q.trim().toLowerCase();
  if (ql) rows = rows.filter(r => (r.section + ' ' + r.key + ' ' + r.help).toLowerCase().includes(ql));
  const val = r => OMS.edits[omsKey(r)] != null ? OMS.edits[omsKey(r)] : r.value;
  const cap = s => s.charAt(0).toUpperCase() + s.slice(1);
  const ctl = (r, n) => {
    const v = val(r);
    if (r.kind === 'bool') return `<input type="checkbox" data-oms="${n}" ${v === 'true' ? 'checked' : ''}>`;
    if (r.choices) return `<select class="inp" data-oms="${n}" style="width:auto">${r.choices.map(([c, l]) => `<option value="${esc(c)}" ${c === v ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select>`;
    const num = r.kind === 'int' || r.kind === 'float';
    return `<input class="inp ${num ? 'num' : ''}" data-oms="${n}" value="${esc(v)}" style="width:${num ? '110px' : '220px'}">`;
  };
  let sec = null, h = '';
  OMS.rows = rows;
  rows.forEach((r, n) => {
    if (OMS.tab !== 'popular' && r.section !== sec){ sec = r.section; h += `<div class="an-h" style="font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--faint);margin:10px 0 2px">${esc(sec)}</div>`; }
    const mine = r.changed || OMS.edits[omsKey(r)] != null;
    h += `<div style="display:grid;grid-template-columns:minmax(0,1fr) auto;gap:4px 12px;align-items:center;padding:5px 0;border-bottom:1px solid var(--line)">
      <div><b>${esc(cap(r.key))}</b>${OMS.tab === 'popular' ? ` <span class="msg">${esc(r.section)}</span>` : ''}${mine ? ' <span class="mine">changed</span>' : ''}
        ${r.help ? `<div class="msg" style="font-size:11.5px;white-space:pre-line">${esc(r.help)}</div>` : ''}</div>
      <div style="display:flex;gap:6px;align-items:center">${ctl(r, n)}${val(r) !== r.default ? `<button class="btn sm" data-omsd="${n}" title="Back to OpenMW's default (${esc(r.default)})">↺</button>` : ''}</div></div>`;
  });
  box.innerHTML = h || '<div class="msg" style="padding:10px">No settings match.</div>';
  const set = (n, v) => { const r = OMS.rows[n]; if (v === r.value) delete OMS.edits[omsKey(r)]; else OMS.edits[omsKey(r)] = v; omsCount(); };
  box.querySelectorAll('[data-oms]').forEach(el => {
    const n = +el.dataset.oms;
    el.onchange = () => { set(n, el.type === 'checkbox' ? (el.checked ? 'true' : 'false') : el.value.trim()); if (el.type !== 'text') omsDraw(); };
  });
  box.querySelectorAll('[data-omsd]').forEach(b => b.onclick = () => { const r = OMS.rows[+b.dataset.omsd]; set(+b.dataset.omsd, r.default); omsDraw(); });
  omsCount();
}
function omsCount(){
  const n = Object.keys(OMS.edits).length, b = OMS.bg && OMS.bg.querySelector('#oms-save');
  if (b){ b.disabled = !n; b.textContent = n ? `Save ${n} change${n === 1 ? '' : 's'}` : 'Save changes'; }
}
async function omsSave(){
  const changes = Object.entries(OMS.edits).map(([k, value]) => { const [section, key] = k.split('|'); return {section, key, value}; });
  try {
    const r = await post('/api/openmw/settings', {changes});
    OMS.d = await api('/api/openmw/settings'); OMS.edits = {}; omsDraw();
    const m = OMS.bg.querySelector('#oms-msg'); if (m) m.textContent = `Saved ${r.changed} setting${r.changed === 1 ? '' : 's'}${r.backup ? '; the old file is kept beside it' : ''}. They take effect the next time the game starts.`;
  } catch (e){ toast(e.message, true); }
}

// ---------- how the game is started: options, saved or picked for one start ----------
function launchForm(L){
  return `${L.presets.map(p => `<label style="display:flex;gap:8px;align-items:flex-start;margin:6px 0"><input type="checkbox" data-lp="${esc(p.key)}" ${L.on.includes(p.key) ? 'checked' : ''} style="margin-top:3px">
      <span><b>${esc(p.label)}</b><br><span class="msg">${esc(p.help)}</span></span></label>`).join('')}
    <details ${L.args || L.env ? 'open' : ''} style="margin-top:8px"><summary>Your own options</summary>
      <label>Extra OpenMW options</label><input class="inp" id="lp-args" value="${esc(L.args)}" placeholder="e.g. --script-console">
      <div class="msg">Added to the command that starts openmw.exe, as you'd type them after it.</div>
      <label>Settings (environment variables), one per line</label><textarea class="inp" id="lp-env" rows="3" placeholder="NAME=value">${esc(L.env)}</textarea>
      <div class="msg">Like the "set NAME=value" in a shortcut that starts OpenMW through cmd.</div></details>`;
}
function launchRead(bg){
  return {on: [...bg.querySelectorAll('[data-lp]')].filter(c => c.checked).map(c => c.dataset.lp),
    args: bg.querySelector('#lp-args').value, env: bg.querySelector('#lp-env').value};
}
async function launchModal(){
  const L = await api('/api/launch');
  const bg = document.createElement('div'); bg.className = 'modal-bg';
  bg.innerHTML = `<div class="modal" style="width:min(560px,94vw)"><h2>Game start options</h2>
    <div class="msg">Used whenever the Workshop starts OpenMW (Start the game, Play here, the clean test).</div>
    ${launchForm(L)}
    <label style="display:flex;gap:8px;margin-top:10px"><input type="checkbox" id="lp-ask" ${L.ask ? 'checked' : ''}> Ask me each time I start the game</label>
    <div class="actions"><button class="btn primary" id="lp-save">Save</button><button class="btn" id="lp-no">Cancel</button><span class="msg" id="lp-msg"></span></div></div>`;
  document.body.appendChild(bg);
  bg.querySelector('#lp-no').onclick = () => bg.remove();
  bg.querySelector('#lp-save').onclick = async () => {
    try { await post('/api/launch', Object.assign(launchRead(bg), {ask: bg.querySelector('#lp-ask').checked})); bg.remove(); toast('Saved. The next start of the game uses these options.'); }
    catch (e){ const m = bg.querySelector('#lp-msg'); m.className = 'msg err'; m.textContent = e.message; }
  };
}
// Start the game through the Workshop: when "ask me each time" is on, the options come up first.
// Returns the server's answer, or null when cancelled.
async function gameStart(url, body){
  let L = null;
  try { L = await api('/api/launch'); } catch (e){}
  if (!L || !L.ask) return await post(url, body);
  return await new Promise((resolve, reject) => {
    const bg = document.createElement('div'); bg.className = 'modal-bg';
    bg.innerHTML = `<div class="modal" style="width:min(560px,94vw)"><h2>▶ Start the game</h2>${launchForm(L)}
      <label style="display:flex;gap:8px;margin-top:10px"><input type="checkbox" id="lp-keep"> Use these next time too</label>
      <div class="actions"><button class="btn primary" id="lp-go">Start</button><button class="btn" id="lp-no">Cancel</button></div></div>`;
    document.body.appendChild(bg);
    bg.querySelector('#lp-no').onclick = () => { bg.remove(); resolve(null); };
    bg.querySelector('#lp-go').onclick = async () => {
      const launch = launchRead(bg);
      try {
        if (bg.querySelector('#lp-keep').checked) await post('/api/launch', Object.assign({}, launch, {ask: true}));
        bg.remove();
        resolve(await post(url, Object.assign({}, body, {launch})));
      } catch (e){ bg.remove(); reject(e); }
    };
  });
}
