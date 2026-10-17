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
      <span class="msg">${LO.dirty ? 'Not saved yet.' : `Saved in ${esc(I.cfg || 'openmw.cfg')}. Each save makes a backup first.`}</span>
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
      <td style="white-space:nowrap"><button class="btn sm" data-lomove="${n},-1" ${n ? '' : 'disabled'} title="Load earlier">↑</button><button class="btn sm" data-lomove="${n},1" ${n < LO.order.length - 1 ? '' : 'disabled'} title="Load later">↓</button></td></tr>`;
  });
  h += `</table>`;
  if (LO.off.length){
    h += `<h3 style="margin-top:22px">Installed but switched off</h3><div class="msg" style="margin-bottom:6px">In your data folders, but not in the load order. Tick one to add it at the bottom.</div>
      <table class="t lot">${LO.off.map(name => {
        const r = loRow(name);
        return `<tr><td style="width:30px"><input type="checkbox" data-lotoggle="${esc(name)}" title="Switch on"></td><td>${esc(r.name)}${r.kind === 'omwscripts' ? ' <span class="chip">Lua scripts</span>' : ''}
          ${r.masters && r.masters.length ? `<div style="font-size:11.5px;color:var(--faint)">needs: ${r.masters.map(esc).join(', ')}</div>` : ''}</td><td class="msg" style="font-size:12px">${esc(r.folder || '')}</td></tr>`;
      }).join('')}</table>`;
  }
  box.innerHTML = h;
  const save = $('#lo-save'); if (save) save.onclick = loSave;
  const rev = $('#lo-revert'); if (rev) rev.onclick = loadPlugins;
  const fix = $('#lo-fix'); if (fix) fix.onclick = async () => {
    const r = await post('/api/loadorder/check', {order: LO.order});
    LO.order = r.sorted; loChanged();
  };
}
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
    toast(`Load order saved (${r.count} plugins). A backup of the old one was made. Reading your game data again…` +
          (r.game_running ? ' The game that is running now keeps the old order until it restarts.' : ''));
    LO.dirty = false;
    setTimeout(poll, 300);
  } catch (e){ toast(e.message, true); }
}
// clicks: browse a plugin, switch on/off, move
$('#pluginwrap').addEventListener('click', e => {
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
       <div class="omwfoot">OpenMW: ${esc(OMW.install)} · <span class="lnk" data-omw="pick">change</span></div>`
    : `<div class="omwfoot" style="border:0">OpenMW wasn't found on this computer.</div>
       <button data-omw="pick"><b>Choose OpenMW's folder…</b><small>The folder with openmw.exe in it.</small></button>
       <button data-omw="get"><b>Get OpenMW</b><small>openmw.org (free). Install it, run its Launcher once, then come back.</small></button>`;
  const b = $('#omwbtn'); if (b) b.classList.toggle('warn', !found);
}
$('#omwbtn').onclick = e => { e.stopPropagation(); const m = $('#omwmenu'); const show = m.style.display !== 'block'; m.style.display = show ? 'block' : 'none'; if (show) omwRefresh(); };
document.addEventListener('click', e => { if (!e.target.closest('#omwmenu')) $('#omwmenu').style.display = 'none'; });
$('#omwmenu').addEventListener('click', async e => {
  const b = e.target.closest('[data-omw]'); if (!b) return;
  const a = b.dataset.omw; $('#omwmenu').style.display = 'none';
  try {
    if (a === 'menu'){ await post('/api/openmw/start', {mode: 'menu'}); toast('Starting OpenMW…'); }
    else if (a === 'launcher'){ await post('/api/openmw/start', {mode: 'launcher'}); toast('Opening OpenMW\'s Launcher…'); }
    else if (a === 'here'){ showView('world'); toast('Open a place on the map, then press "Play here" (or "Pick a spot") on the right.'); }
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
