// Plan a prefab (housemodules.py): a window over the 3D view where a house is stacked as a volume of tiles,
// storey by storey; the Workshop lays the game's own buildings of a style over that volume (the front one
// with its door on the front edge); the whole structure then follows the mouse in the 3D view as a ghost, a
// click pins it, the window's buttons turn it, and "Place here" sets it down (one Undo). "Build its interior"
// then builds the interior from the same volume: each tile of the plan is a tile inside.
const PF = {style: null, styles: {}, storey: 0, tiles: new Set(), fit: null, placed: null, paint: null, busy: false, tab: 'stack', homes: null, tol: 'usual'};
const PF_N = 12;                 // the grid: PF_N x PF_N tiles
const PF_PX = 22;                // a tile on screen
const PF_COL = ['#f0cd87', '#7fd1c7', '#c79bf0'];

function pfKey(x, y, k){ return x + ',' + y + ',' + k; }
function pfHas(x, y, k){ return PF.tiles.has(pfKey(x, y, k)); }

function pfRegister(){
  if (typeof VW_HOST === 'undefined' || VW_HOST.prefabv) return;
  VW_HOST.prefabv = {title: () => '🏗 Plan a prefab', render: () => pfRender(), w: 360};
  if (!$('#prefabv')){
    // (its home is a hidden box: closing the window puts the page back there, out of sight; it is never a page
    // of its own)
    const home = document.createElement('div'); home.id = 'prefabhome'; home.style.display = 'none';
    const d = document.createElement('div'); d.id = 'prefabv'; d.className = 'view';
    home.appendChild(d); document.body.appendChild(home);
  }
  const c = document.createElement('style');
  c.textContent = `.owin[data-vw=prefabv] .vwpage{display:none}
  #prefabv{padding:8px 10px;font-size:13px}
  #prefabv .pfrow{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:5px 0}
  #prefabv canvas{display:block;margin:4px auto;cursor:crosshair;touch-action:none;border:1px solid var(--line, #444)}
  #prefabv .pfst button.on{outline:2px solid var(--gold2, #f0cd87)}`;
  document.head.appendChild(c);
}

async function pfOpen(){
  pfRegister();
  if (!W.key || !W.ext) return toast('Open an outdoor place on the World map first: a prefab stands outdoors.', true);
  if (!V3.on && typeof v3Enable === 'function') await v3Enable(true);
  vwOpen('prefabv');
  vwTitle('prefabv');
  await pfStyles();
  pfRender();
}

// (the first time, the Workshop has to learn how the game puts its buildings together, about nine minutes: the
// window says so with the learning's own bar, and fills in by itself when it is done, instead of an error)
async function pfStyles(){
  if (Object.keys(PF.styles).length) return;
  try {
    const r = await api('/api/build/modules'); PF.styles = r.styles || {}; PF.learning = false;
    if (!PF.style) PF.style = Object.entries(PF.styles).sort((a, b) => b[1] - a[1]).map(x => x[0])[0] || 'Hlaalu';
  } catch (e){
    if (!/still learning/i.test(e.message)) return toast(e.message, true);
    PF.learning = true;
    clearTimeout(PF.learnT);
    PF.learnT = setTimeout(async () => { if (!$('#prefabv')) return; await pfStyles(); pfRender(); }, 5000);
  }
}

function pfRender(){
  const P = $('#prefabv'); if (!P) return;
  P.style.display = 'block';
  const sts = Object.keys(PF.styles).sort();
  const f = PF.fit;
  const tabs = `<div class="pfrow pfst"><button class="btn sm ${PF.tab === 'stack' ? 'on' : ''}" data-tab="stack" title="Stack a house as tiles; the game's buildings are fitted over it">Stack a volume</button>
    <button class="btn sm ${PF.tab === 'ready' ? 'on' : ''}" data-tab="ready" title="The game's one-piece homes: a shack, a hut, a tent, a Nordic house; inside, the piece the game puts in each">Ready-made homes</button></div>`;
  if (PF.tab === 'ready'){
    const H = PF.homes;
    P.innerHTML = tabs + (H == null ? '<div class="msg">Reading the game\'s one-piece homes…</div>' :
      !H.ready ? '<div class="msg">The Workshop is still learning which ready-made interiors the game puts in its small houses (a minute and a half, once). Try again shortly.</div>' :
      `<div class="msg">The game's one-piece homes. Inside, the piece the game puts behind each, fitted out as one of its own.</div>
       <div style="max-height:240px;overflow:auto;margin:4px 0">${H.homes.map((h, n) => `<div class="pfrow"><button class="btn sm" data-home="${n}" style="flex:1;text-align:left">${esc(h.key)} <span class="msg">→ ${esc(h.twin)} · ${h.uses}×${h.style ? ' · ' + esc(h.style) : ''}</span></button></div>`).join('')}</div>`) +
      `<div id="pf-res">${f ? pfResHtml(f) : ''}</div>`;
    P.querySelectorAll('[data-tab]').forEach(b => b.onclick = () => { PF.tab = b.dataset.tab; pfDrop(); pfRender(); });
    P.querySelectorAll('[data-home]').forEach(b => b.onclick = () => {
      const h = PF.homes.homes[+b.dataset.home];
      PF.fit = {items: h.items, modules: [{key: h.key, name: `${h.key}: inside, ${h.twin} as the game has it (${h.example})`}], covered: 1, notes: [], missing: [], ready: true};
      PF.placed = null; pfRender(); pfGhost();
    });
    pfBindRes(P);
    if (H == null) api('/api/build/modules/ready').then(r => { PF.homes = r; pfRender(); }).catch(e => toast(e.message, true));
    // (still learning: asked again every few seconds, so it fills in by itself; it asked once and then sat on
    // "try again shortly", the user: "never populates", 2026-10-27)
    else if (!H.ready){ clearTimeout(PF.homesT); PF.homesT = setTimeout(() => { if ($('#prefabv') && PF.tab === 'ready'){ PF.homes = null; pfRender(); } }, 5000); }
    return;
  }
  if (PF.learning){
    P.innerHTML = tabs + `<div class="msg" style="margin:6px 0"><b>Learning how the game puts its buildings together</b>: every building
      in your load order, once (about nine minutes), so the buildings fitted here are the game's own. This window fills in by itself
      when it is done; the rest of the Workshop works meanwhile.</div>${typeof learnHtml === 'function' && LEARN.sv && LEARN.sv.left ? learnHtml(LEARN.sv, true) : '<div class="msg"><span class="spin"></span>Starting…</div>'}`;
    P.querySelectorAll('[data-tab]').forEach(b => b.onclick = () => { PF.tab = b.dataset.tab; pfDrop(); pfRender(); });
    return;
  }
  P.innerHTML = tabs + `
    <div class="pfrow"><label>Style <select id="pf-style">${sts.map(s => `<option ${s === PF.style ? 'selected' : ''}>${esc(s)}</option>`).join('')}</select></label>
      <span class="msg">${PF.styles[PF.style] || 0} of the game's buildings</span></div>
    <div class="pfrow"><label title="How closely the game's buildings must match your volume, and how far the interior may stand out of them: Close as Tamriel Rebuilt's, Usual as the game's for that building, Loose as Bethesda's own">Match <select id="pf-tol">${[['close', 'Close'], ['usual', 'Usual'], ['loose', 'Loose']].map(([v, t]) => `<option value="${v}" ${PF.tol === v ? 'selected' : ''}>${t}</option>`).join('')}</select></label></div>
    <div class="pfrow pfst">Storey ${[0, 1, 2].map(k => `<button class="btn sm ${PF.storey === k ? 'on' : ''}" data-st="${k}"><span style="color:${PF_COL[k]}">■</span> ${k === 0 ? 'Ground' : k + 1}</button>`).join('')}
      <button class="btn sm" id="pf-clear" title="Start again">Clear</button></div>
    <div class="msg">Click or drag on the grid to stack tiles (a tile is the inside's tile). An upper storey stands on the one below. The door goes on the front, at the bottom.</div>
    <canvas id="pf-grid" width="${PF_N * PF_PX}" height="${PF_N * PF_PX + 14}"></canvas>
    <div class="pfrow"><button class="btn" id="pf-fit" ${PF.tiles.size ? '' : 'disabled'}>Fit the game's buildings</button><span class="msg">${PF.tiles.size} tile${PF.tiles.size === 1 ? '' : 's'}</span></div>
    <div id="pf-res">${f ? pfResHtml(f) : ''}</div>`;
  P.querySelectorAll('[data-tab]').forEach(b => b.onclick = () => { PF.tab = b.dataset.tab; pfDrop(); pfRender(); });
  P.querySelector('#pf-style').onchange = e => { PF.style = e.target.value; pfDrop(); pfRender(); };
  P.querySelector('#pf-tol').onchange = e => { PF.tol = e.target.value; pfDrop(); pfRender(); };
  P.querySelectorAll('[data-st]').forEach(b => b.onclick = () => { PF.storey = +b.dataset.st; pfRender(); });
  P.querySelector('#pf-clear').onclick = () => { PF.tiles.clear(); pfDrop(); pfRender(); };
  P.querySelector('#pf-fit').onclick = pfFit;
  const cv_ = P.querySelector('#pf-grid');
  pfDraw(cv_);
  const at = e => { const r = cv_.getBoundingClientRect(); return [Math.floor((e.clientX - r.left) / PF_PX), PF_N - 1 - Math.floor((e.clientY - r.top) / PF_PX)]; };
  cv_.onpointerdown = e => {
    const [x, y] = at(e); if (x < 0 || y < 0 || x >= PF_N || y >= PF_N) return;
    PF.paint = !pfHas(x, y, PF.storey); PF.last = [x, y];
    cv_.setPointerCapture(e.pointerId); pfPaint(x, y); pfDraw(cv_);
  };
  cv_.onpointermove = e => {
    if (PF.paint == null) return;
    const [x, y] = at(e), [lx, ly] = PF.last || [x, y];
    // (every tile on the way from the last one: a quick drag skips tiles between pointer events)
    const n = Math.max(Math.abs(x - lx), Math.abs(y - ly));
    for (let i = 1; i <= n; i++){
      const tx = Math.round(lx + (x - lx) * i / n), ty = Math.round(ly + (y - ly) * i / n);
      if (tx >= 0 && ty >= 0 && tx < PF_N && ty < PF_N) pfPaint(tx, ty);
    }
    PF.last = [x, y]; pfDraw(cv_);
  };
  cv_.onpointerup = () => { if (PF.paint != null){ PF.paint = null; PF.last = null; pfDrop(); pfRender(); } };
  pfBindRes(P);
}

// (the result's buttons: turn, move, place, build, open; the same on both tabs)
function pfBindRes(P){
  const bind = (id, fn) => { const b = P.querySelector(id); if (b) b.onclick = fn; };
  bind('#pf-left', () => pfTurn(-Math.PI / 2)); bind('#pf-right', () => pfTurn(Math.PI / 2));
  bind('#pf-move', () => { if (V3.ghost){ V3.ghost.pinned = false; } pfRender(); });
  bind('#pf-place', pfPlace);
  bind('#pf-again', pfFit);
  bind('#pf-build', pfBuild);
  bind('#pf-ghost', pfGhost);
  bind('#pf-ground', () => { const p = PF.placed; if (p && p.door && typeof gfFit === 'function') gfFit(p.door.cell, p.door.ref); });
  bind('#pf-open', () => { const k = P.querySelector('#pf-open').dataset.key; vwClose('prefabv'); worldOpen(k); });
}

function pfPaint(x, y){
  const k = PF.storey;
  if (PF.paint){
    if (k > 0 && !pfHas(x, y, k - 1)) return;              // (nothing to stand on)
    PF.tiles.add(pfKey(x, y, k));
  } else {
    for (let s = k; s < 3; s++) PF.tiles.delete(pfKey(x, y, s));   // (what stood on it goes too)
  }
}

function pfDraw(cv_){
  const g = cv_.getContext('2d'), N = PF_N, P_ = PF_PX;
  g.clearRect(0, 0, cv_.width, cv_.height);
  const covered = new Set(), missing = new Set();
  if (PF.fit){ for (const m of PF.fit.modules) for (const t of m.tiles) covered.add(pfKey(t[0] - PF.fit.ox, t[1] - PF.fit.oy, t[2])); for (const t of PF.fit.missing) missing.add(pfKey(t[0] - PF.fit.ox, t[1] - PF.fit.oy, t[2])); }
  for (let x = 0; x < N; x++) for (let y = 0; y < N; y++){
    const sx = x * P_, sy = (N - 1 - y) * P_;
    g.strokeStyle = '#ffffff18'; g.strokeRect(sx + 0.5, sy + 0.5, P_ - 1, P_ - 1);
    let top = -1; for (let k = 2; k >= 0; k--) if (pfHas(x, y, k)){ top = k; break; }
    if (top < 0) continue;
    const k = Math.min(top, PF.storey);
    const here = pfHas(x, y, PF.storey);
    g.fillStyle = PF_COL[top] + (here ? 'cc' : '55');
    g.fillRect(sx + 2, sy + 2, P_ - 4, P_ - 4);
    if (top > 0){ g.fillStyle = '#000a'; g.font = '11px sans-serif'; g.fillText(String(top + 1), sx + 7, sy + 15); }
    if (missing.has(pfKey(x, y, PF.storey))){ g.strokeStyle = '#e25a4a'; g.lineWidth = 2; g.strokeRect(sx + 2, sy + 2, P_ - 4, P_ - 4); g.lineWidth = 1; }
  }
  // the front, where the door goes
  g.fillStyle = '#f0cd87'; g.font = '11px sans-serif'; g.fillText('▼ front (the door)', 4, N * P_ + 11);
}

function pfVolume(){
  return [...PF.tiles].map(k => k.split(',').map(Number));
}

function pfDrop(){
  PF.fit = null; PF.placed = null;
  if (W.mode === 'group' && W.groupPlace && W.groupPlace.prefab) setMode(null);
}

// (each Fit, and each Another, draws afresh among the game's buildings that fit nearly as well as the best, by
// how often the game builds them: the same volume gives a different house, not a cookie-cutter one)
async function pfFit(){
  const tiles = pfVolume(); if (!tiles.length) return;
  const b = $('#pf-fit'); if (b){ b.disabled = true; b.textContent = 'Fitting…'; }
  const a = $('#pf-again'); if (a){ a.disabled = true; }
  let r;
  try { r = await post('/api/build/modules/fit', {style: PF.style, tiles, front: 'S', tolerance: PF.tol, seed: Math.floor(Math.random() * 1e9)}); }
  catch (e){ toast(e.message, true); pfRender(); return; }
  r.ox = 0; r.oy = 0;
  PF.fit = r; PF.placed = null;
  pfRender();
  pfGhost();
  pfShowRes();
}
// (the result and its buttons sit below the grid: brought into sight, or they went unseen)
function pfShowRes(){ const el = $('#pf-res'); if (el && el.firstElementChild) el.scrollIntoView({block: 'nearest'}); }

function pfResHtml(f){
  let h = f.ready ? '<div style="margin-top:6px"><b>A ready-made home of the game\'s</b></div>' : `<div style="margin-top:6px"><b>${f.modules.length} of the game's building${f.modules.length === 1 ? '' : 's'}</b>, ${Math.round(f.covered * 100)}% of the tiles under them</div>`;
  h += `<div class="msg">${f.modules.map(m => esc(m.name)).join('<br>')}</div>`;
  if (!f.ready && !PF.placed) h += `<div class="pfrow"><button class="btn sm" id="pf-again" title="Other buildings of the game's that fit as well, drawn by how often the game builds each">↻ Another</button></div>`;
  for (const n of f.notes || []) h += `<div class="msg" style="margin:3px 0">${esc(n)}</div>`;
  if (!PF.placed){
    const pinned = V3.ghost && V3.ghost.pinned;
    h += `<div class="pfrow" style="margin-top:8px">
      ${W.mode === 'group' && W.groupPlace && W.groupPlace.prefab ? '' : '<button class="btn sm" id="pf-ghost">Show it in the view</button>'}
      <button class="btn sm" id="pf-left" title="Turn it a quarter left">⟲</button><button class="btn sm" id="pf-right" title="Turn it a quarter right">⟳</button>
      ${pinned ? '<button class="btn sm" id="pf-move" title="Let it follow the mouse again">Move</button>' : ''}
      <button class="btn" id="pf-place" ${pinned ? '' : 'disabled'} title="${pinned ? 'Set the whole structure down here' : 'Point in the 3D view and click to pin it first'}">Place here</button></div>
      <div class="msg">${pinned ? 'Pinned. Turn it, Move it, or Place here.' : 'Point in the 3D view where it goes (the wheel turns it) and click to put it down. It is set on the lowest ground under it, so on a slope it sinks into the hill rather than standing in the air.'}</div>`;
  } else {
    const p = PF.placed;
    h += `<div style="margin-top:8px;padding-top:6px;border-top:1px solid #fff2">Placed (${p.n} objects). <button class="btn sm" id="pf-ground" title="Raise the ground round its foot where it stands over it, and a landing at its door, the way the game's buildings meet the ground (the building stays put; Undo takes it back)">⛰ Fit the ground</button> ${p.built ? '' : `
      <div class="pfrow"><input id="pf-name" style="flex:1" maxlength="63" value="${esc(p.name || '')}" title="The interior's name"><button class="btn" id="pf-build">Build its interior</button></div>`}
      ${p.built || ''}</div>`;
  }
  return h;
}

function pfGhost(){
  const f = PF.fit; if (!f) return;
  if (!V3.on) return toast('Open the 3D view to place it.', true);
  startGroupPlace(f.items, 'prefab: ' + f.modules.map(m => m.key).join(' + '));
  W.groupPlace.prefab = true;
  pfRender();
}

function pfTurn(a){
  const G = V3.ghost; if (!G) return;
  G.yaw = ((G.yaw + a) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI);
  G.g.rotation.set(0, 0, -G.yaw);
  if (W.groupPlace) W.groupPlace.yaw = G.yaw;
  if (typeof groupHint === 'function') groupHint();
  v3Refresh();
}

// (world3d.js: a click in the view while a prefab is being placed puts it down there, as the banner says; it
// only pinned it once, and the Place here that followed sat below the grid, out of sight: the user found no way
// to make the building, 2026-10-27)
function pfPin(){
  const G = V3.ghost; if (!G || !G.hit) return toast('Point at the ground first.', true);
  G.pinned = true;
  pfPlace();
}

// The height to set it at: the lowest ground under its ground-floor pieces, so on a slope the uphill side sinks
// into the hill as the game's own buildings do, rather than the downhill side standing in the air (the user saw
// buildings floating where the foundation could go into the ground). Set at the point under the mouse, it floated
// wherever the ground fell away.
function pfGroundZ(items, x, y, yaw, z0){
  const c = Math.cos(yaw), s = Math.sin(yaw);
  // (the prefab workbench marks the pieces standing on its floor, and how far its floor is over the lowest point:
  // those set it, bench.js)
  const foot = items.filter(i => i.foot);
  if (foot.length){
    let z = null;
    for (const i of foot){
      const g = groundZ(x + i.dx * c + i.dy * s, y - i.dx * s + i.dy * c);
      if (g != null && isFinite(g)) z = z == null ? g : Math.min(z, g);
    }
    return z == null ? z0 : z - (foot[0].footUp || 0);
  }
  const low = Math.min(...items.map(i => i.dz || 0));
  let z = null;
  for (const i of items){
    if ((i.dz || 0) > low + 100) continue;
    const g = groundZ(x + i.dx * c + i.dy * s, y - i.dx * s + i.dy * c);
    if (g != null && isFinite(g)) z = z == null ? g : Math.min(z, g);
  }
  return z == null ? z0 : z;
}

async function pfPlace(){
  const G = V3.ghost, f = PF.fit; if (!G || !G.pinned || !G.hit || !f) return;
  const [x, y] = G.hit;
  const z = W.ext ? pfGroundZ(f.items, x, y, G.yaw, G.hit[2]) : G.hit[2];
  const label = 'prefab: ' + f.modules.map(m => m.key).join(' + ');
  const r = await groupAction('/api/group/place', {cell: cellKeyAt(x, y), items: f.items, x, y, z, yaw: G.yaw, label}, `Placed ${label}`);
  if (!r) return;
  setMode(null);
  // the front building's door: the first door among the placed (the fitter lays the front one first)
  let door = null;
  for (const p of r.placed){
    const c = W.cells[p.cell] || await api('/api/cellmap?key=' + encodeURIComponent(p.cell));
    const ref = (c.refs || []).find(q => q.k === p.ref);
    if (ref && ref.type === 'DOOR'){ door = p; break; }
  }
  PF.placed = {n: r.placed.length, door, name: ''};
  try { const pv = await api('/api/build/from_building?cell=' + encodeURIComponent(door.cell) + '&ref=' + encodeURIComponent(door.ref)); PF.placed.name = pv.name || ''; } catch (e){}
  pfRender(); pfShowRes();
  drawMap(); if (V3.on) v3Refresh();
}

async function pfBuild(){
  const p = PF.placed, f = PF.fit; if (!p || !p.door || !f) return toast('The prefab has no door to build from.', true);
  const name = ($('#pf-name').value || '').trim(); if (!name) return toast('Give the interior a name.', true);
  const b = $('#pf-build'); b.disabled = true; b.textContent = 'Building…';
  let o;
  try { o = await post('/api/build/from_building', {cell: p.door.cell, ref: p.door.ref, door: p.door.ref, name, style: f.kit, tiles: f.frame_tiles, tolerance: PF.tol}); }
  catch (e){ b.disabled = false; b.textContent = 'Build its interior'; return toast(e.message, true); }
  const ft = o.fits;
  p.built = `<div><b>Built ${esc(o.name)}</b>${o.northmarker ? ', northmarker in' : ''}; its door and the prefab's lead to each other.</div>
    ${ft ? `<div class="msg" style="color:${ft.ok ? '#8fc98f' : '#e8b85a'}">${esc(ft.text)}</div>` : ''}
    <button class="btn sm" id="pf-open" data-key="${esc(o.key)}">Open it</button>`;
  pfRender();
  toast('Built ' + o.name);
}
