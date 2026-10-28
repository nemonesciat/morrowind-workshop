// The World map's tools as panels (see panels.js): Place, Selected, Objects and View as the sidebar
// had them, and more: Selected panels pinned to one object each (to compare or tweak several), more
// Objects lists with their own filters, Find gaps, your Library, prefabs, places you've been, recent
// changes and the 3D controls. Ready-made layouts for building, furnishing and a big view.
const WP = {places: (() => { try { return JSON.parse(localStorage.getItem('ws-places') || '[]'); } catch (e){ return []; } })()};

const WP_PRESETS = {
  'Building': {right: {size: 340, groups: [{tabs: ['place', 'sel', 'objs', 'view', 'sky', 'land', 'paths'], on: 'place', grow: 1}]},
               left: {size: 300, groups: []}, bottom: {size: 220, groups: []}, floats: []},
  'Furnishing': {right: {size: 360, groups: [{tabs: ['place', 'library', 'prefabs'], on: 'place', grow: 1.3}, {tabs: ['sel', 'objs'], on: 'sel', grow: 1}]},
                 left: {size: 300, groups: []}, bottom: {size: 220, groups: []}, floats: []},
  'Two sides': {left: {size: 300, groups: [{tabs: ['place', 'library'], on: 'place', grow: 1}, {tabs: ['places'], on: 'places', grow: 0.5}]},
                right: {size: 330, groups: [{tabs: ['sel', 'objs', 'view', 'sky', 'land', 'paths'], on: 'sel', grow: 1}]}, bottom: {size: 200, groups: []}, floats: []},
  'Big view': {left: {size: 300, groups: []}, right: {size: 340, groups: []}, bottom: {size: 220, groups: []},
               floats: [{tabs: ['place', 'objs'], on: 'place', x: 16, y: 56, w: 330, h: 420}, {tabs: ['sel'], on: 'sel', x: -16, y: 56, w: 320, h: 380}]},
};

function worldPanelsInit(){
  if (PNL.spaces.world) return;
  PNL.space('world', $('#world'), $('#world .mapwrap'), {
    presets: WP_PRESETS, start: 'Building',
    onResize: () => { if ($('#world').classList.contains('on')){ sizeMap(); drawMap(); if (typeof V3 !== 'undefined' && V3.on) v3Resize(); } },
  });
  const scan = it => { if (typeof v3ThumbScan === 'function') v3ThumbScan(it.el); };
  PNL.define('world', 'place', {title: 'Place', cls: 'wside', onShow: scan});
  PNL.define('world', 'sel', {title: 'Selected', cls: 'wside', onShow: scan,
    menu: it => {
      const r = W.sel && findRef(W.sel.cell, W.sel.k);
      return r ? [{label: '📌 Pin this one in its own panel', act: () => wpPin(W.sel.cell, r)}] : [];
    }});
  PNL.define('world', 'objs', {title: 'Objects', cls: 'wside', onShow: scan, multi: true,
    cloneState: () => ({filter: ''}), titleFor: it => it.state && it.state.filter ? 'Objects: ' + it.state.filter : 'Objects'});
  PNL.define('world', 'view', {title: 'View', cls: 'wside'});
  PNL.define('world', 'paths', {title: 'Paths', icon: '🚶', cls: 'wside'});   // (drawn with the others, by renderWside)
  PNL.define('world', 'sky', {title: 'Sky', icon: '🌤', cls: 'wside'});
  PNL.define('world', 'land', {title: 'Land', icon: '⛰', cls: 'wside'});
  PNL.define('world', 'pin', {title: 'Pinned', hidden: true, multi: true, home: 'float', cls: 'wside', w: 330, h: 470,
    titleFor: it => '📌 ' + (it.state.name || 'Pinned'), render: wpRenderPin, onShow: scan});
  PNL.define('world', 'library', {title: 'Library', icon: '📦', cls: 'wside', render: wpRenderLibrary, onShow: it => wpRenderLibrary(it)});
  PNL.define('world', 'prefabs', {title: 'Prefabs', icon: '🧩', cls: 'wside', render: wpRenderPrefabs, onShow: it => wpRenderPrefabs(it)});
  PNL.define('world', 'places', {title: 'Places', icon: '🗺', cls: 'wside', render: wpRenderPlaces, onShow: it => wpRenderPlaces(it)});
  PNL.define('world', 'activity', {title: 'Recent changes', icon: '🕘', home: 'bottom', cls: 'wside', render: wpRenderActivity, onShow: it => wpRenderActivity(it)});
  PNL.define('world', 'fixit', {title: 'Find gaps', icon: '🔧', home: 'float', w: 390, h: 540, cls: 'wside',
    render: it => { if (typeof FX === 'undefined' || !FX.panel || !it.el.contains(FX.panel)){
      it.el.innerHTML = `<div class="msg" style="margin:4px 0 10px">Finds the spots in a place built from room pieces where you can see out into the void, and closes them.</div><button class="btn primary" id="fx-start">🔧 Look for gaps here</button>`;
      it.el.querySelector('#fx-start').onclick = () => { if (W.info && W.info.interior) fixitOpen(W.info.key); else toast('Open an interior first.'); };
    } },
    onShow: it => PNL.spaces.world.types.fixit.render(it),
    onClose: () => { if (typeof FX !== 'undefined'){ FX.issues = []; FX.panel = null; fixitMarks(); } }});
  PNL.define('world', 'check', {title: 'Check this place', icon: '🩺', home: 'float', w: 400, h: 560, cls: 'wside',
    render: it => { if (typeof PC === 'undefined' || !PC.panel || !it.el.contains(PC.panel)){
      it.el.innerHTML = `<div class="msg" style="margin:4px 0 10px">Finds what's wrong with a place (floating or clipping things, lights on nothing, gaps…) and marks each on the map.</div><button class="btn primary" id="pc-start">🩺 Check this place</button>`;
      it.el.querySelector('#pc-start').onclick = () => { if (W.info && W.info.interior) placecheckOpen(W.info.key); else toast('Open an interior first.'); };
    } },
    onShow: it => PNL.spaces.world.types.check.render(it),
    onClose: () => { if (typeof PC !== 'undefined'){ PC.issues = []; PC.panel = null; placecheckMarks(); if (!V3.on && typeof drawMap === 'function') drawMap(); } }});
  PNL.define('world', 'keys', {title: '3D controls', icon: '⌨', home: 'float', w: 420, h: 330, cls: 'wside',
    render: it => { it.el.innerHTML = `<div class="msg" style="line-height:1.9">${$('#v3help') ? $('#v3help').innerHTML : ''}</div>`; }});
  // (the extra Objects lists draw themselves; the first one is the sidebar's own)
  PNL.spaces.world.types.objs.render = it => { if (it.id !== 'objs') wpRenderObjList(it); };
  if (typeof qolPanels === 'function') qolPanels();
  PNL.start('world');
  wpAddPathsTab(); wpAddSkyLandTabs();
  for (const it of Object.values(PNL.spaces.world.inst)){ const t = PNL.spaces.world.types[it.type]; if (t.render && it.id !== 'objs') t.render(it); }
  // the button that lists every panel and the layouts
  const sw = $('#viewsw');
  if (sw && !$('#w-panels')){
    const b = document.createElement('button'); b.id = 'w-panels'; b.title = 'Panels: open, close and arrange the tools; layouts'; b.textContent = '▤ Panels';
    b.onclick = e => { e.stopPropagation(); PNL.windowsMenu('world', b); };
    sw.appendChild(b);
  }
}

// (2.1) a layout kept from before Paths had its own panel: put it once beside View, as a tab
function wpAddPathsTab(){
  try { if (localStorage.getItem('ws-paths-tab')) return; localStorage.setItem('ws-paths-tab', '1'); } catch (e){ return; }
  const sp = PNL.spaces.world, L = sp.layout;
  const groups = [...['left', 'right', 'bottom'].flatMap(s => (L[s] || {}).groups || []), ...(L.floats || [])];
  if (groups.some(g => g.tabs.includes('paths'))) return;
  const g = groups.find(g => g.tabs.includes('view')) || groups.find(g => g.tabs.includes('place'));
  if (!g) return;
  g.tabs.splice(g.tabs.indexOf('view') + 1 || g.tabs.length, 0, 'paths');
  PNL.useLayout('world', L);
}

// (2.5.4) a layout kept from before View was split: Sky and Land go once beside View, as tabs
function wpAddSkyLandTabs(){
  try { if (localStorage.getItem('ws-skyland-tabs')) return; localStorage.setItem('ws-skyland-tabs', '1'); } catch (e){ return; }
  const L = PNL.spaces.world.layout;
  const groups = [...['left', 'right', 'bottom'].flatMap(s => (L[s] || {}).groups || []), ...(L.floats || [])];
  if (groups.some(g => g.tabs.includes('sky') || g.tabs.includes('land'))) return;
  const g = groups.find(g => g.tabs.includes('view')) || groups.find(g => g.tabs.includes('place'));
  if (!g) return;
  g.tabs.splice(g.tabs.indexOf('view') + 1 || g.tabs.length, 0, 'sky', 'land');
  PNL.useLayout('world', L);
}

// after the sidebar's panels were drawn: the others that show something about this place
function wpAfterRender(){
  const sp = PNL.spaces.world; if (!sp) return;
  for (const it of Object.values(sp.inst)){
    if (it.type === 'pin') wpRenderPin(it);
    else if (it.type === 'objs' && it.id !== 'objs') wpRenderObjList(it);
    else if (it.type === 'places' && PNL.isOpen('world', it.id)) wpRenderPlaces(it);
  }
  if (W.info){
    const i = W.info, name = i.name || i.region || (i.interior ? i.key : 'Wilderness ' + i.gx + ', ' + i.gy);
    if (!WP.places.length || WP.places[0].i !== i.i){
      WP.places = [{i: i.i, name, interior: !!i.interior}, ...WP.places.filter(p => p.i !== i.i)].slice(0, 24);
      try { localStorage.setItem('ws-places', JSON.stringify(WP.places)); } catch (e){}
    }
  }
}

// ----- Selected, pinned to one object: stays on it whatever else you click
function wpPin(cell, r){
  const ex = PNL.all('world', 'pin').find(it => it.state.cell === cell && it.state.k === r.k);
  if (ex) return PNL.show('world', ex.id);
  PNL.open('world', 'pin', {cell, k: r.k, name: r.name || r.id});
}

function wpRenderPin(it){
  const b = it.el, st = it.state, r = findRef(st.cell, st.k);
  if (!r){ b.innerHTML = `<div class="msg" style="padding:10px 0">${W.cells[st.cell] ? 'This object isn\'t there any more.' : 'Open its place to see it: ' + esc(st.cell)}</div>`; return; }
  const deg = v => ((v * 180 / Math.PI) % 360 + 360) % 360;
  const tilt = v => (Math.round((((v || 0) * 180 / Math.PI + 540) % 360 - 180) * 10) / 10).toString();      // (−180 to 180: level is 0)
  b.innerHTML = `<div class="selcard"><div>${thumbImg(r.id, r.type, 120)}</div><div style="min-width:0"><div style="font-weight:600">${esc(r.name || r.id)}</div>
      <div class="msg" style="word-break:break-all">${esc(r.id)}</div><div class="msg">${esc(S.typeLabels[r.type] || '')} · ${r.mine ? '<span class="mine">your mod</span>' : 'from ' + esc(r.src || '')}</div></div></div>
    <div class="xyz"><div><label>X</label><input class="inp" data-pp="0" value="${r.p[0].toFixed(1)}"></div><div><label>Y</label><input class="inp" data-pp="1" value="${r.p[1].toFixed(1)}"></div><div><label>Height</label><input class="inp" data-pp="2" value="${r.p[2].toFixed(1)}"></div></div>
    <div class="xyz"><div><label>Turn (°)</label><input class="inp" data-pp="5" value="${deg(r.p[5]).toFixed(0)}"></div><div><label title="Leaning forwards (about X)">Tilt fwd (°)</label><input class="inp" data-pp="3" value="${tilt(r.p[3])}"></div><div><label title="Leaning sideways (about Y)">Tilt side (°)</label><input class="inp" data-pp="4" value="${tilt(r.p[4])}"></div></div>
    <div class="two"><div><label>Scale</label><input class="inp" data-pp="s" value="${r.s}"></div><div></div></div>
    <div class="actions"><button class="btn sm primary" data-pa="apply">Apply</button><button class="btn sm" data-pa="select">Select it</button><button class="btn sm" data-pa="look">Look at it</button></div>`;
  if (typeof v3ThumbScan === 'function') v3ThumbScan(b);
  b.querySelector('[data-pa=apply]').onclick = async () => {
    if (!await needProject()) return;
    const p = r.p.slice(); let s = r.s;
    b.querySelectorAll('[data-pp]').forEach(inp => {
      const v = parseFloat(inp.value); if (isNaN(v)) return;
      if (inp.dataset.pp === 's') s = v; else if (['3', '4', '5'].includes(inp.dataset.pp)) p[+inp.dataset.pp] = v * Math.PI / 180; else p[+inp.dataset.pp] = v;
    });
    try { await refAction('/api/ref/move', {cell: st.cell, ref: r.k, p, s}, st.cell, null, 'Moved ' + (r.name || r.id)); }
    catch (e){ toast(e.message, true); }
  };
  b.querySelector('[data-pa=select]').onclick = () => { if (W.key === st.cell){ selectRef(st.cell, r.k); centerOn(r); } };
  b.querySelector('[data-pa=look]').onclick = () => { if (W.key === st.cell){ selectRef(st.cell, r.k, true); centerOn(r); if (V3.on && typeof v3Focus === 'function') v3Focus(r); } };
}

// ----- another Objects list, with a filter of its own
function wpRenderObjList(it){
  const b = it.el, refs = (W.cells[W.key] || {refs: []}).refs;
  if (!b.querySelector('.wp-of')){
    b.innerHTML = `<input class="inp wp-of" placeholder="Filter… (e.g. chair, light, your mod)" style="margin-bottom:6px"><div class="olist wp-ol"></div>`;
    const inp = b.querySelector('.wp-of');
    inp.value = it.state.filter || '';
    inp.oninput = () => { it.state.filter = inp.value; PNL.retitle('world', it.id); draw(); };
    b.querySelector('.wp-ol').onclick = e => { const ok = e.target.closest('[data-ok]'); if (!ok) return; const r = findRef(W.key, ok.dataset.ok); if (r){ selectRef(W.key, r.k); centerOn(r); } };
  }
  const draw = () => {
    const f = (it.state.filter || '').toLowerCase(), mine = f === 'your mod' || f === 'mine';
    const list = refs.filter(r => !f || (mine ? r.mine : (r.id + ' ' + (r.name || '') + ' ' + (S.typeLabels[r.type] || '')).toLowerCase().includes(f))).slice(0, 400);
    b.querySelector('.wp-ol').innerHTML = list.map(r => `<div data-ok="${esc(r.k)}" data-hid="${esc(r.id)}" class="${W.sel && W.sel.k === r.k ? 'sel' : ''}"><span>${thumbImg(r.id, r.type, 48, 'sm')}${r.mine ? '✎ ' : ''}${esc(r.name || r.id)}</span><small>${esc(S.typeLabels[r.type] || '')}</small></div>`).join('') || '<div class="msg">Nothing matches.</div>';
    PNL.badge('world', it.id, fmtN(list.length));
    if (typeof v3ThumbScan === 'function') v3ThumbScan(b);
  };
  draw();
}

// ----- your Library: click to place (it becomes part of your mod the first time)
async function wpRenderLibrary(it){
  const b = it.el;
  let items = [];
  try { items = (await api('/api/library')).items.filter(x => x.ok && (x.type === 'model' || x.type === 'sound')); } catch (e){}
  b.innerHTML = items.length ? `<div class="msg" style="margin-bottom:6px">Click one, then click where it goes. The Library page has the rest.</div>
    <div class="olist">${items.map(x => `<div data-lib="${esc(x.id)}" title="${esc(x.name)}">${x.records && Object.values(x.records)[0] ? thumbImg(Object.values(x.records)[0], Object.keys(x.records)[0], 48, 'sm') : '<span style="width:32px;display:inline-block;text-align:center">' + (x.type === 'sound' ? '🔊' : '📦') + '</span>'}<span>${esc(x.name)}</span><small>${esc(x.type === 'sound' ? 'sound' : x.kind || 'model')}</small></div>`).join('')}</div>`
    : '<div class="msg" style="padding:10px 0">Your Library is empty. Bring in your own models, pictures and sounds on the Library page.</div>';
  b.querySelectorAll('[data-lib]').forEach(d => d.onclick = async () => {
    if (!await needProject()) return;
    const x = items.find(i => i.id === d.dataset.lib);
    try {
      const r = await post('/api/library/record', {id: x.id, kind: x.kind});
      setMode('place', {id: r.id, name: x.name, type: r.type});
    } catch (e){ toast(e.message, true); }
  });
  if (typeof v3ThumbScan === 'function') v3ThumbScan(b);
}

// ----- prefabs, as tiles to place
async function wpRenderPrefabs(it){
  const b = it.el;
  if (!W.prefabs){ try { W.prefabs = await api('/api/prefabs'); } catch (e){ W.prefabs = []; } }
  b.innerHTML = W.prefabs.length ? `<div class="msg" style="margin-bottom:6px">Click one, then click where it goes.</div><div class="tiles">${W.prefabs.map((p, n) => `<div class="tile" data-wpf="${n}" title="${esc(p.name)}: ${p.items.length} objects">${prefabPlan(p.items)}<span>${esc(p.name)}</span></div>`).join('')}</div>`
    : '<div class="msg" style="padding:10px 0">No prefabs yet: select a few objects (Shift+click) and use "Save as a prefab" in Selected.</div>';
  b.querySelectorAll('[data-wpf]').forEach(t => t.onclick = () => { const p = W.prefabs[+t.dataset.wpf]; startGroupPlace(p.items, p.name); });
}

// ----- places you've been (newest first) and a search
function wpRenderPlaces(it){
  const b = it.el;
  if (!b.querySelector('.wp-goto')){
    b.innerHTML = `<div class="dd"><input class="inp wp-goto" id="wp-goto-${esc(it.id)}" placeholder="Go to a place…" autocomplete="off"><div class="ddlist" id="wp-goto-${esc(it.id)}-l"></div></div><h3>Been there lately</h3><div class="olist wp-pl"></div>`;
    ddSearch('wp-goto-' + it.id, 'CELL', r => worldOpenIndex(r.i));
    b.querySelector('.wp-pl').onclick = e => { const d = e.target.closest('[data-wpi]'); if (d) worldOpenIndex(+d.dataset.wpi); };
  }
  b.querySelector('.wp-pl').innerHTML = WP.places.map(p => `<div data-wpi="${p.i}" class="${W.info && W.info.i === p.i ? 'sel' : ''}"><span>${p.interior ? '🏠' : '🌄'} ${esc(p.name)}</span></div>`).join('') || '<div class="msg">None yet: the places you open show up here, to go back to.</div>';
}

// ----- the last changes to your mod (undo any of them from here)
async function wpRenderActivity(it){
  const b = it.el;
  let r = null;
  try { r = await api('/api/project'); } catch (e){}
  const log = r && r.log ? r.log.slice(-40).reverse() : [];
  b.innerHTML = log.length ? `<div class="olist">${log.map(e => `<div style="${e.undone ? 'opacity:.5;text-decoration:line-through' : ''}"><span>${esc(e.text || '')}</span><small>${esc((e.t || '').slice(11))}${e.can_undo ? ` <button class="btn sm" data-wpu="${e.id}" title="Take back this change">↶</button>` : ''}</small></div>`).join('')}</div>`
    : '<div class="msg" style="padding:10px 0">No changes yet.</div>';
  b.querySelectorAll('[data-wpu]').forEach(x => x.onclick = async () => {
    // (everything again, as the Undo button does: reloading the open cell alone left undone ground in the 3D view)
    try { await post('/api/undo_entry', {id: +x.dataset.wpu, only: true}); toast('Taken back.'); await refreshAfterEdits(); wpRenderActivity(it); }
    catch (e){ toast(e.message, true); }
  });
}
