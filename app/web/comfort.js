// Everyday comfort: a status bar under the World map, right-click menus for what's on the map,
// the command palette (Ctrl+K: every command and every place in one search box) and keyboard
// shortcuts you can change.
const CF = {user: (() => { try { return JSON.parse(localStorage.getItem('ws-keys') || '{}'); } catch (e){ return {}; } })(), status: ''};

function cfCss(){
  if ($('#cf-css')) return;
  const c = document.createElement('style'); c.id = 'cf-css';
  c.textContent = `
  #wstatus{flex:none;display:flex;align-items:center;gap:14px;padding:0 10px;height:24px;border-top:1px solid var(--line);background:var(--deep-d);font-size:11.5px;color:var(--faint);white-space:nowrap;overflow:hidden;min-width:0}
  #wstatus > span{overflow:hidden;text-overflow:ellipsis;min-width:0}
  #wstatus [data-copy]{cursor:copy}
  #wstatus [data-copy]:hover{color:var(--text)}
  #wstatus b{color:var(--muted);font-weight:600}
  #wstatus .grow{flex:1}
  #wstatus .lk{flex-shrink:12}#wstatus .hint{flex-shrink:40}
  #wstatus .on{color:#8fd18f}
  #wstatus .mode{color:var(--gold2)}
  .pmenu{max-height:calc(100vh - 16px);overflow:auto}
  .pmenu button[disabled]{cursor:default}
  .pmenu button:hover:not([disabled]){background:#ffffff12}.pmenu button[disabled]:hover{background:none}
  .pmenu .phd{opacity:1!important;font-size:11px;color:var(--faint);padding:4px 10px 2px;letter-spacing:.04em;max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  #cf-pal{align-items:flex-start}
  #cf-pal .modal{margin-top:12vh;padding:0;width:min(620px,94vw);overflow:hidden}
  #cf-pal input{width:100%;box-sizing:border-box;background:none;border:0;border-bottom:1px solid var(--line);color:var(--text);font:inherit;font-size:16px;padding:14px 16px;outline:none}
  #cf-pal .cf-l{max-height:min(420px,60vh);overflow:auto;padding:4px}
  #cf-pal .cf-i{display:flex;align-items:center;gap:10px;padding:7px 12px;border-radius:7px;cursor:pointer;font-size:13.5px}
  #cf-pal .cf-i.on{background:#ffffff12}
  #cf-pal .cf-i span{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  #cf-pal .cf-i small{color:var(--faint);font-size:11px;flex:none}
  #cf-pal .cf-g{font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--faint);padding:8px 12px 3px}
  #cf-pal .cf-foot{border-top:1px solid var(--line);padding:6px 12px;font-size:11px;color:var(--faint)}
  kbd.cf{display:inline-block;background:#ffffff10;border:1px solid var(--line2);border-bottom-width:2px;border-radius:5px;padding:0 6px;font:inherit;font-size:11px;color:var(--muted);margin-left:3px}
  .cf-keys td{padding:5px 8px;border-bottom:1px solid var(--line);font-size:13px;vertical-align:middle}
  .cf-keys td:last-child{text-align:right;white-space:nowrap}
  .cf-keys kbd button{background:none;border:0;color:var(--faint);cursor:pointer;padding:0 0 0 4px;font-size:10px}
  .cf-keys kbd button:hover{color:#ff9c8a}
  .cf-wait{color:var(--gold2)!important;border-color:var(--gold)!important}
  /* a calmer, more even look everywhere */
  *{scrollbar-width:thin;scrollbar-color:#463b2c transparent}
  ::-webkit-scrollbar{width:9px;height:9px}::-webkit-scrollbar-thumb{background:#463b2c;border-radius:6px;border:2px solid transparent;background-clip:padding-box}
  ::-webkit-scrollbar-thumb:hover{background-color:#5c4d39}::-webkit-scrollbar-track{background:transparent}
  :focus-visible{outline:2px solid var(--gold);outline-offset:1px}
  .btn,.ptab,.pmenu button{transition:background-color .12s,border-color .12s,color .12s}`;
  document.head.appendChild(c);
}

// ---------------------------------------------------------------- shortcuts
const cfWorldOn = () => $('#world').classList.contains('on');
const cfSelRef = () => W.sel && findRef(W.sel.cell, W.sel.k);
function cfMode(m){ if (typeof V3 === 'undefined' || !V3.tc || W.mode === 'group') return false; V3.mode = m; v3ApplyMode(); v3Tools(); }

// world: only on the World map; v3: only in its 3D view; typing: also while typing in a box; any: also over an open window
const CF_ACT = [
  {id: 'palette', label: 'Command palette (every command and place)', keys: ['Ctrl+K'], typing: true, any: true, run: () => cfPalette()},
  {id: 'keys', label: 'Keyboard shortcuts', keys: ['Ctrl+/'], any: true, run: () => cfKeysModal()},
  {id: 'search', label: 'Search box at the top', keys: ['/'], run: () => { $('#q').focus(); $('#q').select(); }},
  {id: 'undo', label: 'Undo', keys: ['Ctrl+Z'], run: () => doUndo()},
  {id: 'delete', label: 'Delete what\'s selected', keys: ['Delete', 'Backspace'], world: true, run: () => W.multi.size > 1 ? groupDo('delete') : W.sel ? selAction('delete') : false},
  {id: 'copy', label: 'Copy what\'s selected', keys: ['Ctrl+C'], world: true, run: () => W.sel && !String(window.getSelection() || '') ? groupDo('copy') : false},
  {id: 'paste', label: 'Paste (then click where it goes)', keys: ['Ctrl+V'], world: true, run: () => W.clip ? startGroupPlace(W.clip.items, W.clip.label) : false},
  {id: 'dup', label: 'Duplicate what\'s selected', keys: ['Ctrl+D'], world: true, run: () => W.sel ? groupDo('dup') : false},
  {id: 'selall', label: 'Select everything you can see', keys: ['Ctrl+A'], world: true, run: () => cfSelectAll()},
  {id: 'samekind', label: 'Select all like the selected one', keys: [], world: true, run: () => { const r = cfSelRef(); if (!r) return false; cfSelectLike(r); }},
  {id: 'clearsel', label: 'Clear the selection', keys: [], world: true, run: () => { W.sel = null; W.multi.clear(); renderWside(); drawMap(); if (V3.on) v3Refresh(); }},
  {id: 'focus', label: 'Look at what\'s selected', keys: ['F'], world: true, run: () => {
    const r = cfSelRef(); if (!r) return false;
    if (V3.on){ const o = V3.objs.get(W.sel.cell + '|' + W.sel.k); if (o) v3FocusObj(o.g); } else centerOn(r);
  }},
  {id: 'turn90', label: 'Turn what\'s selected 90°', keys: [], world: true, run: () => W.sel ? groupDo('turn') : false},
  {id: 'move', label: '3D: move handles', keys: ['G', '1'], v3: true, run: () => cfMode('translate')},
  {id: 'rotate', label: '3D: turn handles', keys: ['R', '2'], v3: true, run: () => cfMode('rotate')},
  {id: 'drop', label: '3D: set it down on what\'s below', keys: ['End'], v3: true, run: () => v3DropToFloor()},
  {id: 'view3d', label: 'Switch between the flat map and 3D', keys: [], world: true, run: () => { const b = document.querySelector(`[data-view3d="${V3.on ? 0 : 1}"]`); if (b) b.click(); }},
  {id: 'panels', label: 'Panels and layouts menu', keys: [], world: true, run: () => PNL.windowsMenu('world', $('#w-panels'))},
  {id: 'fixit', label: 'Find gaps in this place', keys: [], world: true, run: () => W.info && W.info.interior ? fixitOpen(W.info.key) : toast('Open an interior first.', true)},
  {id: 'play', label: 'Play here (pick a spot)', keys: [], world: true, run: () => W.key ? setMode('play') : toast('Open a place first.', true)},
];
const CF_FIXED = [
  ['W A S D', '3D: fly (Q / E down and up, Shift faster)'], ['Esc', 'Stop: placing, flying, or clear the selection'],
  ['Right-drag', '3D: look around'], ['Middle-drag', '3D: slide the view'], ['Alt + drag', '3D: circle around what\'s selected'],
  ['Wheel', 'Zoom (3D: fly forward; turns what you place)'], ['Shift + click', 'Add to or take from the selection'],
  ['Drag on empty space', '3D: draw a box to select (Shift+drag on the flat map; Shift adds)'], ['Right-click', 'A menu for what\'s under the mouse'],
];
const cfKeysOf = a => CF.user[a.id] || a.keys;

function cfKeyName(e){
  if (['Control', 'Shift', 'Alt', 'Meta', 'OS', 'AltGraph', 'CapsLock'].includes(e.key)) return null;
  let base;
  if (/^Key[A-Z]$/.test(e.code)) base = e.code.slice(3);
  else if (/^Digit\d$/.test(e.code)) base = e.code.slice(5);
  else if (e.key === ' ') base = 'Space';
  else base = e.key.length === 1 ? e.key.toUpperCase() : e.key;
  // (for a sign like / Shift is part of typing it on some keyboards, so it isn't counted)
  const sign = base.length === 1 && !/[A-Z0-9]/.test(base);
  return (e.ctrlKey || e.metaKey ? 'Ctrl+' : '') + (e.altKey ? 'Alt+' : '') + (e.shiftKey && !sign ? 'Shift+' : '') + base;
}
function cfTyping(e){
  const t = e.target; if (!t) return false;
  if (t.tagName === 'INPUT') return !['checkbox', 'radio', 'button', 'range', 'color', 'submit'].includes(t.type);
  return t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable;
}
window.addEventListener('keydown', e => {
  if (CF.capture){ CF.capture(e); return; }
  if (typeof peKey === 'function' && peKey(e)) return;       // editing walking paths: Delete, Ctrl+Z, Esc are its own
  // (a tool with keys of its own, like the room planner: Ctrl+Z there undoes the plan, not your mod)
  if (e.target && e.target.closest && e.target.closest('[data-ownkeys]')) return;
  const name = cfKeyName(e); if (!name) return;
  const typing = cfTyping(e), world = cfWorldOn(), modal = document.querySelector('.modal-bg');
  for (const a of CF_ACT){
    if (!cfKeysOf(a).includes(name)) continue;
    if (typing && !a.typing) continue;
    if (modal && !a.any) continue;
    if ((a.world || a.v3) && !world) continue;
    if (a.v3 && !(typeof V3 !== 'undefined' && V3.on)) continue;
    if (a.run(e) === false) continue;
    e.preventDefault(); e.stopPropagation();
    return;
  }
}, true);

function cfSaveKeys(){ try { localStorage.setItem('ws-keys', JSON.stringify(CF.user)); } catch (e){} }

function cfKeysModal(){
  cfCss();
  document.querySelectorAll('#cf-keys').forEach(x => x.remove());
  const bg = document.createElement('div'); bg.className = 'modal-bg'; bg.id = 'cf-keys';
  const draw = () => {
    bg.innerHTML = `<div class="modal" style="width:min(640px,94vw);max-height:88vh;overflow:auto"><h2>Keyboard shortcuts</h2>
      <div class="msg">Click <b>+</b> and press the keys you want. A key can only do one thing, so giving it to something else takes it from where it was.</div>
      <table class="cf-keys" style="width:100%;border-collapse:collapse;margin-top:10px">${CF_ACT.map(a => `<tr><td>${esc(a.label)}${a.world ? ' <span class="msg">(World map)</span>' : ''}</td>
        <td>${cfKeysOf(a).map(k => `<kbd class="cf">${esc(k)}<button data-kdel="${a.id}|${esc(k)}" title="Remove">✕</button></kbd>`).join('')}<button class="btn sm" data-kadd="${a.id}" style="margin-left:6px" title="Add a key">+</button></td></tr>`).join('')}</table>
      <h3 style="margin-top:18px">Always the same</h3>
      <table class="cf-keys" style="width:100%;border-collapse:collapse">${CF_FIXED.map(([k, t]) => `<tr><td>${esc(t)}</td><td><kbd class="cf">${esc(k)}</kbd></td></tr>`).join('')}</table>
      <div class="foot"><button class="btn" id="cf-kreset">Back to the usual keys</button><button class="btn primary" id="cf-kclose">Done</button></div></div>`;
    bg.querySelector('#cf-kclose').onclick = close;
    bg.querySelector('#cf-kreset').onclick = () => { CF.user = {}; cfSaveKeys(); draw(); toast('Shortcuts are back to the usual keys.'); };
    bg.querySelectorAll('[data-kdel]').forEach(b => b.onclick = () => {
      const [id, k] = b.dataset.kdel.split('|'), a = CF_ACT.find(x => x.id === id);
      CF.user[id] = cfKeysOf(a).filter(x => x !== k); cfSaveKeys(); draw();
    });
    bg.querySelectorAll('[data-kadd]').forEach(b => b.onclick = () => {
      b.textContent = 'Press keys…'; b.classList.add('cf-wait');
      CF.capture = e => {
        e.preventDefault(); e.stopPropagation();
        if (e.key === 'Escape'){ CF.capture = null; draw(); return; }
        const name = cfKeyName(e); if (!name) return;
        CF.capture = null;
        const a = CF_ACT.find(x => x.id === b.dataset.kadd);
        for (const o of CF_ACT) if (o !== a && cfKeysOf(o).includes(name)){ CF.user[o.id] = cfKeysOf(o).filter(x => x !== name); toast(`${name} no longer does "${o.label}".`); }
        if (!cfKeysOf(a).includes(name)) CF.user[a.id] = [...cfKeysOf(a), name];
        cfSaveKeys(); draw();
      };
    });
  };
  const close = () => { CF.capture = null; bg.remove(); };
  bg.onclick = e => { if (e.target === bg) close(); };
  document.body.appendChild(bg);
  draw();
}

// ---------------------------------------------------------------- selecting more
function cfPickMany(list){
  W.multi.clear();
  for (const [ck, r] of list) W.multi.set(mkey(ck, r.k), {cell: ck, k: r.k});
  if (!list.length){ W.sel = null; toast('Nothing to select.'); }
  else if (list.length === 1){ W.multi.clear(); selectRef(list[0][0], list[0][1].k); return; }
  else { const l = list[list.length - 1]; W.sel = {cell: l[0], k: l[1].k}; W.tab = 'sel'; toast(`Selected ${list.length} objects.`); }
  renderWside(); drawMap(); if (V3.on) v3Refresh();
}
function cfSelectAll(){ cfPickMany(visibleRefs().filter(([ck, r]) => !(r.arch && W.lockArch) && (W.ext || ck === W.key))); }
function cfSelectLike(r){ cfPickMany(visibleRefs().filter(([ck, x]) => x.id.toLowerCase() === r.id.toLowerCase() && (W.ext || ck === W.key))); }

// ---------------------------------------------------------------- right-click menus
// hit: [cell, ref] under the mouse (or null); at: the world spot [x, y, z] under it (or null)
function cfMenuAt(e, hit, at){
  if (!cfWorldOn() || !W.key) return;
  if (W.mode === 'paths'){ peMenu(e); return; }
  const items = [], pt = {x: e.clientX, y: e.clientY};
  const sep = () => { if (items.length && items[items.length - 1] !== '-') items.push('-'); };
  const head = t => items.push({label: t, disabled: true, head: true});
  if (hit && W.multi.size > 1 && inMulti(hit[0], hit[1].k)){
    head(`${W.multi.size} objects`);
    items.push({label: '⧉ Copy', act: () => groupDo('copy')}, {label: 'Duplicate', act: () => groupDo('dup')},
      {label: '⟳ Turn 90°', act: () => groupDo('turn')}, {label: '⟲ Turn 90° the other way', act: () => groupDo('turnback')},
      {label: '⤢ Scale them…', act: () => cfRun('scale')}, {label: '⇄ Replace them with…', act: () => cfRun('replace')},
      {label: '🧩 Save as a prefab…', act: () => { const f = $('#g-prefabname'); if (f) f.value = ''; groupDo('prefab'); }});
    sep(); items.push({label: '◌ Hide them (H)', act: () => cfRun('hide')}, {label: 'Hide everything else (Shift+H)', act: () => cfRun('isolate')},
      {label: 'Clear the selection', act: () => cfRun('clearsel')}, {label: 'Delete all of them', act: () => groupDo('delete')});
  } else if (hit){
    const [ck, r] = hit;
    if (!(W.sel && W.sel.cell === ck && W.sel.k === r.k)) selectRef(ck, r.k);
    head(r.name || r.id);
    items.push({label: '⌖ Look at it', act: () => cfRun('focus')}, {label: '📌 Pin it in its own panel', act: () => wpPin(ck, r)});
    if (r.ri != null) items.push({label: '📄 Open its record', act: () => { showView('browse'); openRecord(r.ri, true); }});
    items.push({label: '🔎 Where it\'s used (F1)', act: () => qolUses(r.id)});
    sep();
    items.push({label: '⧉ Copy', act: () => groupDo('copy')}, {label: 'Duplicate', act: () => selAction('dup')}, {label: '⟳ Turn 90°', act: () => groupDo('turn')}, {label: '⤢ Scale…', act: () => cfRun('scale')});
    if (V3.on) items.push({label: '⤓ Set it down on what\'s below', act: () => v3DropToFloor()});
    items.push({label: '⇄ Swap for something else…', act: () => { PNL.show('world', 'sel'); setTimeout(() => { const s = $('#w-swap'); if (s) s.focus(); }, 50); }});
    items.push({label: `⇄ Replace every ${r.name || r.id} here…`, act: () => qolReplace(r.id)});
    items.push({label: `Select all the ${r.name || r.id} here`, act: () => cfSelectLike(r)}, {label: '◌ Hide it (H)', act: () => cfRun('hide')}, {label: 'Hide everything else (Shift+H)', act: () => cfRun('isolate')});
    if (r.type === 'DOOR'){
      sep();
      if (r.to) items.push({label: '→ Go where it leads', act: () => selAction('gotodest')}, {label: '📍 Pick where you arrive…', act: () => selAction('arrive')});
      else items.push({label: 'Make it lead somewhere…', act: () => { PNL.show('world', 'sel'); setTimeout(() => { const s = $('#w-relink'); if (s) s.focus(); }, 50); }});
    }
    if (r.type === 'NPC_' || r.type === 'CREA'){ sep(); items.push({label: '💬 Dialogue', act: () => selAction('talk')}, {label: r.type === 'CREA' ? '🐾 Edit creature' : '👤 Edit character', act: () => selAction('char')}); }
    sep();
    if (r.arch) items.push({label: '↻ Other pieces that fit here', act: () => selAction('variants')});
    if (['STAT', 'ACTI', 'CONT', 'MISC', 'DOOR', 'LIGH', 'WEAP', 'ARMO', 'CLOT'].includes(r.type)) items.push({label: '🎨 Retexture…', act: () => selAction('retex')});
    items.push({label: '🔊 Add a sound…', act: () => selAction('sound')});
    sep();
    if (r.mine) items.push({label: '↶ Undo my changes to it', act: () => selAction('restore')});
    items.push({label: 'Delete', act: () => selAction('delete')});
  } else {
    head(W.info ? (W.info.name || W.info.region || 'Here') : 'Here');
    // a red cross: something your mod took out, to bring back
    if (at && W.marks && typeof qolChanges === 'function'){
      const reach = V3.on ? 70 : 14 / W.cam.z;
      const near = qolChanges().filter(x => x.kind === 'gone').map(x => [Math.hypot(x.r.p[0] - at[0], x.r.p[1] - at[1]), x]).sort((a, b) => a[0] - b[0])[0];
      if (near && near[0] < reach) items.push({label: `↶ Bring back ${near[1].r.name || near[1].r.id}`, act: () => qolRestore([near[1]])}, '-');
    }
    if (typeof QOL !== 'undefined' && QOL.back.length) items.push({label: `← Back to ${QOL.back[QOL.back.length - 1].name} (Alt+←)`, act: () => qolBack()});
    if (W.hide.size) items.push({label: `Show the ${W.hide.size} hidden again (Alt+H)`, act: () => cfRun('unhide')});
    if (W.clip && at) items.push({label: `📋 Paste ${W.clip.label} here`, act: () => { W.groupPlace = {items: W.clip.items, label: W.clip.label, yaw: 0}; placeGroupAt(at[0], at[1], V3.on ? at[2] : null); }});
    if (at) items.push({label: '▶ Play here', act: () => playHere({cell: cellKeyAt(at[0], at[1]), x: at[0], y: at[1], z: V3.on && at[2] != null ? at[2] + 60 : groundZ(at[0], at[1]) + (W.ext ? 60 : 40), rz: 0})});
    if (W.info && W.info.interior) items.push({label: '🔧 Find gaps here', act: () => fixitOpen(W.info.key)});
    items.push({label: 'Select everything you can see', act: () => cfSelectAll()});
    if (W.sel || W.multi.size) items.push({label: 'Clear the selection', act: () => cfRun('clearsel')});
    sep(); items.push({label: '▤ Panels and layouts…', act: () => PNL.windowsMenu('world', pt)}, {label: '⌘ All commands… (Ctrl+K)', act: () => cfPalette()});
  }
  while (items[items.length - 1] === '-') items.pop();
  const m = pnlMenu(pt, items);
  m.querySelectorAll('button').forEach((b, n) => { const it = items.filter(x => x !== '-')[n]; if (it && it.head){ b.className = 'phd'; } });
}
function cfRun(id){ const a = CF_ACT.find(x => x.id === id); if (a) a.run(); }

// the flat map, and the object lists in the panels
cv.addEventListener('contextmenu', e => {
  e.preventDefault();
  if (W.mode === 'paths'){ peMenu(e); return; }
  if (W.mode){ setMode(null); return; }
  const hit = hitTest(e.offsetX, e.offsetY);
  cfMenuAt(e, hit, toWorld(e.offsetX, e.offsetY));
});
$('#world').addEventListener('contextmenu', e => {
  const ok = e.target.closest('[data-ok]'); if (!ok) return;
  const r = findRef(W.key, ok.dataset.ok); if (!r) return;
  e.preventDefault();
  cfMenuAt(e, [W.key, r], null);
});
// no browser menu (Back, Reload, Print…) anywhere in the Workshop. The 3D view opens its menu as the button comes up,
// so the browser's right-click lands on that new menu, not the view. Text boxes and selected text keep it, for Copy and Paste.
document.addEventListener('contextmenu', e => {
  const t = e.target;
  if (t.closest && t.closest('input, textarea, select, [contenteditable=""], [contenteditable="true"]')) return;
  const s = getSelection();
  if (s && !s.isCollapsed && String(s).trim()) return;
  e.preventDefault();
});

// the menus at the top (Help, OpenMW…) stay inside the window, however narrow it is
function cfKeepInside(m){
  if (getComputedStyle(m).display === 'none') return;
  // (where it would be without the shift; only a changed shift is written, so this doesn't set itself off again)
  const now = parseFloat((m.style.transform.match(/-?[\d.]+/) || [0])[0]) || 0, r = m.getBoundingClientRect();
  const left = r.left - now, right = r.right - now;
  const dx = left < 8 ? Math.round(8 - left) : right > innerWidth - 8 ? Math.round(innerWidth - 8 - right) : 0;
  const want = dx ? `translateX(${dx}px)` : '';
  if (m.style.transform !== want) m.style.transform = want;
}
document.querySelectorAll('.omwmenu').forEach(m => new MutationObserver(() => cfKeepInside(m)).observe(m, {attributes: true, attributeFilter: ['style', 'class']}));

// ---------------------------------------------------------------- the status bar
function cfStatus(){
  if (!cfWorldOn() || typeof PNL === 'undefined' || !PNL.spaces.world) return;
  cfCss();
  let bar = $('#wstatus');
  if (!bar){
    bar = document.createElement('div'); bar.id = 'wstatus';
    PNL.spaces.world.els.center.appendChild(bar);
    bar.onclick = e => { const c = e.target.closest('[data-copy]'); if (!c) return; navigator.clipboard.writeText(c.dataset.copy).then(() => toast('Copied ' + c.dataset.copy)).catch(() => {}); };
  }
  const n1 = v => Math.round(v), deg = v => Math.round(((v * 180 / Math.PI) % 360 + 360) % 360);
  const parts = [];
  if (W.info){
    const i = W.info;
    parts.push(`<span><b>${esc(i.name || i.region || (i.interior ? i.key : 'Wilderness'))}</b>${i.interior ? '' : ` <span title="The cell">(${i.gx}, ${i.gy})</span>`}</span>`);
  } else parts.push('<span>No place open</span>');
  if (W.mode){
    const what = {place: 'Placing ' + (W.placeName || ''), group: 'Placing ' + ((W.groupPlace || {}).label || 'a group'), play: 'Pick where to play', arrive: 'Pick the arrival spot', region: 'Painting regions'}[W.mode] || W.mode;
    parts.push(`<span class="mode">${esc(what)} · Esc stops</span>`);
  }
  if (V3.on && V3.pos){
    const [x, y, z] = v3CamWorld(), dirs = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
    const f = dirs[((Math.round(V3.yaw / (Math.PI / 4)) % 8) + 8) % 8];
    parts.push(`<span data-copy="${n1(x)}, ${n1(y)}, ${n1(z)}" title="Where the camera is (click to copy)">👁 ${n1(x)}, ${n1(y)}, ${n1(z)} · facing ${f}</span>`);
  } else if (W.mouse && W.key && typeof toWorld === 'function'){
    const [x, y] = toWorld(W.mouse[0], W.mouse[1]);
    parts.push(`<span data-copy="${n1(x)}, ${n1(y)}" title="Under the mouse (click to copy)">✛ ${n1(x)}, ${n1(y)}</span>`);
  }
  const r = cfSelRef();
  if (W.multi.size > 1) parts.push(`<span><b>${W.multi.size} selected</b></span>`);
  else if (r) parts.push(`<span data-copy="${n1(r.p[0])}, ${n1(r.p[1])}, ${n1(r.p[2])}" title="What's selected (click to copy where it is)"><b>${esc(r.name || r.id)}</b> · ${n1(r.p[0])}, ${n1(r.p[1])}, ${n1(r.p[2])} · ${deg(r.p[5])}°${r.s && r.s !== 1 ? ' · ×' + r.s : ''}${r.mine ? ' · <span class="on">changed</span>' : ''}</span>`);
  if (W.onlyMine) parts.push('<span class="mode" title="Only what your mod changed is shown (View panel)">Only my changes</span>');
  if (W.hide.size) parts.push(`<span title="Hidden for now: Alt+H shows them again">◌ ${W.hide.size} hidden</span>`);
  parts.push('<span class="grow"></span>');
  parts.push(typeof LINK !== 'undefined' && LINK.connected ? '<span class="on lk" title="The game is running and linked: changes show up in it">● In game</span>' : '<span class="lk" title="Start the game from the Workshop to see changes in it live">○ Game not linked</span>');
  parts.push('<span class="hint" title="Every command, place and record in one search box">Ctrl+K commands</span>');
  const h = parts.join('');
  if (h !== CF.status){ CF.status = h; bar.innerHTML = h; }
}
setInterval(cfStatus, 250);

// ---------------------------------------------------------------- the command palette
function cfCommands(){
  const out = [], world = fn => () => { if (!cfWorldOn()) showView('world'); setTimeout(fn, 30); };
  for (const a of CF_ACT){
    if (a.id === 'palette') continue;
    out.push({g: a.world || a.v3 ? 'World map' : 'Commands', label: a.label, keys: cfKeysOf(a)[0], run: a.world || a.v3 ? world(a.run) : a.run});
  }
  document.querySelectorAll('nav button[data-view]').forEach(b => out.push({g: 'Pages', label: 'Go to ' + b.textContent.replace(/\d+$/, '').trim(), run: () => showView(b.dataset.view)}));
  if (typeof PNL !== 'undefined' && PNL.spaces.world){
    const sp = PNL.spaces.world;
    for (const [k, t] of Object.entries(sp.types)) if (!t.hidden) out.push({g: 'Panels', label: (PNL.isOpen('world', k) ? 'Show the ' : 'Open the ') + t.title + ' panel', run: world(() => PNL.show('world', k))});
    for (const n of Object.keys(sp.opts.presets)) out.push({g: 'Panels', label: 'Layout: ' + n, run: world(() => PNL.useLayout('world', sp.opts.presets[n]))});
    for (const [n, L] of Object.entries(PNL.layouts('world'))) out.push({g: 'Panels', label: 'My layout: ' + n, run: world(() => PNL.useLayout('world', L))});
  }
  const fn = (name, label) => { if (typeof window[name] === 'function') out.push({g: 'Commands', label, run: () => window[name]()}); };
  fn('projectModal', 'Start or open a mod…'); fn('togOpen', '👥 Build together…'); fn('packBrowse', '🗂 Browse packs…');
  fn('launchModal', 'Game start options…'); fn('reportModal', 'Report a problem…'); fn('aboutModal', 'About the Workshop');
  return out;
}

function cfPalette(){
  cfCss();
  const old = $('#cf-pal'); if (old){ old.remove(); return; }
  const bg = document.createElement('div'); bg.className = 'modal-bg'; bg.id = 'cf-pal';
  bg.innerHTML = `<div class="modal"><input id="cf-q" placeholder="Type a command, a place or a record…" autocomplete="off" spellcheck="false"><div class="cf-l"></div>
    <div class="cf-foot">↑ ↓ to choose · Enter to do it · Esc to close · places and records show up as you type</div></div>`;
  document.body.appendChild(bg);
  const inp = bg.querySelector('#cf-q'), list = bg.querySelector('.cf-l'), cmds = cfCommands();
  let shown = [], on = 0, seq = 0, found = [];
  const close = () => bg.remove();
  const draw = () => {
    const q = inp.value.trim().toLowerCase(), words = q.split(/\s+/).filter(Boolean);
    const hit = c => words.every(w => (c.g + ' ' + c.label).toLowerCase().includes(w));
    shown = (q ? cmds.filter(hit) : cmds.filter(c => c.g !== 'Pages')).slice(0, 40).concat(found);
    on = Math.min(on, Math.max(0, shown.length - 1));
    let g = null;
    list.innerHTML = shown.map((c, n) => (c.g !== g ? `<div class="cf-g">${esc(g = c.g)}</div>` : '') + `<div class="cf-i ${n === on ? 'on' : ''}" data-n="${n}"><span>${esc(c.label)}</span>${c.sub ? `<small>${esc(c.sub)}</small>` : ''}${c.keys ? `<kbd class="cf">${esc(c.keys)}</kbd>` : ''}</div>`).join('')
      || '<div class="msg" style="padding:12px">Nothing matches.</div>';
    const cur = list.querySelector('.cf-i.on'); if (cur) cur.scrollIntoView({block: 'nearest'});
  };
  const pick = n => { const c = shown[n]; if (!c) return; close(); try { const r = c.run(); if (r && r.catch) r.catch(e => toast(e.message, true)); } catch (e){ toast(e.message, true); } };
  let t;
  inp.oninput = () => {
    on = 0; found = []; draw();
    clearTimeout(t);
    const q = inp.value.trim(); if (q.length < 2) return;
    const my = ++seq;
    t = setTimeout(async () => {
      try {
        const [cells, recs] = await Promise.all([api('/api/search?' + new URLSearchParams({q, types: 'CELL', limit: 8})), api('/api/search?' + new URLSearchParams({q, limit: 8}))]);
        if (my !== seq || !bg.isConnected) return;
        found = cells.rows.map(x => ({g: 'Places', label: x.name || x.id, run: () => { showView('world'); worldOpenIndex(x.i); }}))
          .concat(recs.rows.filter(x => !['CELL', 'PGRD', 'LAND', 'LTEX'].includes(x.type)).map(x => ({g: 'Records', label: x.name || x.id, sub: (S.typeLabels[x.type] || x.type) + (x.name ? ' · ' + x.id : ''), run: () => { showView('browse'); openRecord(x.i, true); }})));
        draw();
      } catch (e){}
    }, 160);
  };
  inp.onkeydown = e => {
    if (e.key === 'ArrowDown'){ e.preventDefault(); on = Math.min(shown.length - 1, on + 1); draw(); }
    else if (e.key === 'ArrowUp'){ e.preventDefault(); on = Math.max(0, on - 1); draw(); }
    else if (e.key === 'Enter'){ e.preventDefault(); pick(on); }
    else if (e.key === 'Escape'){ e.preventDefault(); e.stopPropagation(); close(); }
  };
  list.onclick = e => { const i = e.target.closest('[data-n]'); if (i) pick(+i.dataset.n); };
  list.onmousemove = e => { const i = e.target.closest('[data-n]'); if (i && +i.dataset.n !== on){ on = +i.dataset.n; list.querySelectorAll('.cf-i').forEach(x => x.classList.toggle('on', +x.dataset.n === on)); } };
  bg.onclick = e => { if (e.target === bg) close(); };
  draw(); inp.focus();
}
