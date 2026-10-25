// Add a room through a wall: right-click an outer wall of a place built from pieces, and a see-through room
// appears beyond it, drawn as the kit's own pieces where they would stand; a small card sets its size, name
// and kind; Build lays only the new room and the doorway (the rest of the house stays as it is) and furnishes
// it (app/extend.py). The ghost is the planner's "fits here" / Fix here preview (v3GhostAt).
const EX = {card: null, cell: null, ref: null, at: null, w: 3, h: 3, shift: 0, name: '', kind: '', furnish: true, last: null, busy: false};

const EX_KINDS = ['Bedroom', 'Study', 'Library', 'Dining room', 'Kitchen', 'Hall', 'Storeroom', 'Shop', 'Bath', 'Shrine', 'Guard room', 'Workshop'];

async function extendStart(cell, ref, at){
  if (!await needProject()) return;
  extendClose();
  EX.cell = cell; EX.ref = ref || null; EX.at = at || null; EX.w = 3; EX.h = 3; EX.shift = 0; EX.name = 'Bedroom'; EX.furnish = true;
  const card = document.createElement('div'); card.className = 'modal'; card.id = 'ex-card';
  card.style.cssText = 'position:absolute;right:24px;bottom:72px;width:300px;z-index:30;box-shadow:0 6px 24px #0008';
  card.innerHTML = `<h2 style="margin:0 0 6px;font-size:16px">➕ Add a room through this wall</h2>
    <div class="msg" id="ex-where"><span class="spin"></span> Reading the wall…</div>
    <div style="display:flex;gap:6px;margin-top:8px;flex-wrap:wrap">
      <button class="btn sm" data-exp="3,3" title="A square room, three tiles each way">Room 3×3</button>
      <button class="btn sm" data-exp="4,4" title="A big room">Hall 4×4</button>
      <button class="btn sm" data-exp="1,4" title="A passage one tile wide, four deep">Corridor 1×4</button>
      <button class="btn sm" data-exp="2,2" title="A small room">Closet 2×2</button>
    </div>
    <div class="frow" style="display:grid;grid-template-columns:1fr 1fr;gap:6px 10px;margin-top:8px">
      <label>Kind<select class="inp" id="ex-kind">${EX_KINDS.map(k => `<option ${k === 'Bedroom' ? 'selected' : ''}>${k}</option>`).join('')}</select></label>
      <label>Name<input class="inp" id="ex-name" value="Bedroom" maxlength="40"></label>
      <label>Along the wall<input class="inp" id="ex-w" type="number" min="1" max="6" value="3"></label>
      <label>Deep<input class="inp" id="ex-h" type="number" min="1" max="6" value="3"></label>
      <label style="grid-column:1/3">Slide along the wall <input id="ex-shift" type="range" min="-3" max="3" value="0" style="width:100%"></label>
      <label class="msg" style="grid-column:1/3;display:flex;gap:6px;align-items:center"><input type="checkbox" id="ex-furnish" checked> Furnish it (the game's way, as this kind of room)</label>
      <div class="msg" id="ex-sketch" style="grid-column:1/3"></div>
    </div>
    <div class="msg err" id="ex-err" style="margin-top:6px"></div>
    <div class="foot" style="margin-top:8px"><button class="btn" id="ex-cancel">Cancel</button><button class="btn primary" id="ex-go" disabled>Build it</button></div>`;
  $('#v3wrap').appendChild(card);
  EX.card = card;
  if (typeof cfMovable === 'function') cfMovable(card, 'h2', 'extend');
  const q = s => card.querySelector(s);
  q('#ex-cancel').onclick = extendClose;
  q('#ex-kind').onchange = () => { EX.kind = q('#ex-kind').value; q('#ex-name').value = EX.kind; EX.name = EX.kind; extendPreview(); };
  q('#ex-name').oninput = () => { EX.name = q('#ex-name').value; };
  q('#ex-w').onchange = () => { EX.w = Math.max(1, Math.min(6, +q('#ex-w').value || 3)); extendPreview(); };
  q('#ex-h').onchange = () => { EX.h = Math.max(1, Math.min(6, +q('#ex-h').value || 3)); extendPreview(); };
  q('#ex-shift').oninput = () => { EX.shift = +q('#ex-shift').value; extendPreview(); };
  q('#ex-furnish').onchange = () => { EX.furnish = q('#ex-furnish').checked; if (EX.last){ if (typeof v3GhostAt === 'function' && V3.on) v3GhostAt(EX.last.ghost || []); extendSketch(EX.last); } };
  q('#ex-go').onclick = extendBuild;
  card.querySelectorAll('[data-exp]').forEach(b => b.onclick = () => {
    const [w, h] = b.dataset.exp.split(',').map(Number);
    EX.w = w; EX.h = h; q('#ex-w').value = w; q('#ex-h').value = h;
    if (w === 1){ EX.kind = 'Hall'; q('#ex-kind').value = 'Hall'; q('#ex-name').value = 'Passage'; EX.name = 'Passage'; }
    extendPreview();
  });
  await extendPreview();
}

async function extendPreview(){
  const card = EX.card; if (!card) return;
  const q = s => card.querySelector(s);
  let r;
  try { r = await post('/api/extend/options', {cell: EX.cell, ref: EX.ref, at: EX.at, w: EX.w, h: EX.h, shift: EX.shift, name: EX.name}); }
  catch (e){ q('#ex-where').textContent = ''; q('#ex-err').textContent = e.message; q('#ex-go').disabled = true; if (typeof v3GhostClear === 'function') v3GhostClear(); return; }
  if (!EX.card) return;
  EX.last = r;
  const sides = {N: 'north', E: 'east', S: 'south', W: 'west'};
  q('#ex-where').innerHTML = `Through the <b>${sides[r.side]}</b> wall of <b>${esc(r.from)}</b>: a ${r.room.w} × ${r.room.h} tile room of ${esc(r.style)} pieces${r.fits ? '' : ''}.`;
  q('#ex-err').textContent = r.fits ? '' : (r.note || 'It does not fit there.');
  q('#ex-go').disabled = !r.fits;
  if (typeof v3GhostAt === 'function' && V3.on) v3GhostAt(r.ghost || []);
  extendSketch(r);
}

// The furniture sketch: with "Furnish it" ticked, the ghost room also shows the big pieces the furnish would
// lay for that kind of room (a bed there, a table, shelves, a rug), from a dry run on the ghost's tiles; drawn
// again when the size or the kind changes. A sketch, not a promise: the real furnish rolls its own draw.
async function extendSketch(r){
  const card = EX.card; if (!card) return;
  const q = s => card.querySelector(s);
  const my = (EX.sketchN = (EX.sketchN || 0) + 1);
  const note = q('#ex-sketch');
  if (!EX.furnish || !r.fits){ if (note) note.textContent = ''; return; }
  if (note) note.innerHTML = '<span class="spin"></span> Sketching the furniture…';
  let s;
  try { s = await post('/api/extend/sketch', {cell: EX.cell, ref: EX.ref, at: EX.at, w: EX.w, h: EX.h, shift: EX.shift, name: EX.name, kind: EX.kind || q('#ex-kind').value,
                                              level: (typeof furnishAsValue === 'function' && $('#fu-level')) ? furnishAsValue('fu') : null}); }
  catch (e){ if (note && my === EX.sketchN) note.textContent = ''; return; }
  if (!EX.card || my !== EX.sketchN) return;
  if (note) note.textContent = s.furniture.length ? `Sketch: ${s.furniture.length} big pieces a ${s.purpose} this size gets (the real furnish rolls its own draw).` : (s.note ? 'No sketch: ' + s.note : '');
  if (typeof v3GhostAt === 'function' && V3.on && EX.last === r) v3GhostAt((r.ghost || []).concat(s.furniture.map(f => ({id: f.id, p: f.p, s: f.s}))));
}

// ----- Remove this room: a room the plan knows comes out with its pieces and furniture, and the wall closes
// again where its doorway was (the joint survey's answer), as one Undo (app/extend.py remove)
async function extendRemoveRoom(cell, room, name){
  if (!await needProject()) return;
  let chk;
  try { chk = await post('/api/extend/removable', {cell, room}); } catch (e){ return toast(e.message, true); }
  if (!chk.ok) return toast(`The ${chk.name} can't be taken out: ${chk.why}.`, true);
  if (!confirm(`Take the ${chk.name} out of this place? Its pieces and everything in it go, and the wall closes again where its doorway was. One Undo brings it back.`)) return;
  try {
    const m = await post('/api/extend/remove', {cell, room});
    toast(`Removed the ${m.name} (${m.pieces} pieces, ${m.things} things; ${m.closed} wall${m.closed === 1 ? '' : 's'} closed again). Undo brings it back.`);
    if (typeof worldReloadCell === 'function') await worldReloadCell(cell);
    if (typeof afterChange === 'function') afterChange();
    if (typeof v3Refresh === 'function' && V3.on) v3Refresh();
    W.roomInfo = {}; W.dressable = {};
  } catch (e){ toast(e.message, true); }
}

// ===================================================================================================
// Extend mode: building piece by piece. Every open face of every building piece glows as a strip on its
// floor line (gold; red where a ray out through it finds nothing). Click a strip and a column of candidates
// slides in beside the view: what the game joins to that face of that piece, most often first, each with
// its thumbnail and the game's share as a bar (the adjacency survey, app/adjacency.py). Hover one and its
// ghost snaps on, with the faces it would leave open lit; click or Enter lays it as one undo step; Tab
// cycles; Backspace takes the last piece off; Esc leaves and folds the steps into one named change. Above
// the candidates, the patterns the game repeats from here (a run with a handle for how many, a piece with
// its ring). "Close it" previews and lays the closing pieces on the new pieces only. The same on the map.
const EXM = {on: false, cell: null, edges: [], sel: null, cands: null, hover: -1, laid: [], steps: 0, panel: null, group: null, leaveGroup: null,
             hoverEdge: null, busy: false, closing: null, name: ''};
const EXM_GOLD = 0xf0cd87, EXM_RED = 0xe25a4a, EXM_LIT = 0xfff0b0;

async function extendMode(on, cell, edge){
  if (on === EXM.on && !edge) return;
  if (!on){ await extendModeLeave(); return; }
  if (!await needProject()) return;
  if (typeof extendClose === 'function') extendClose();
  EXM.on = true; EXM.cell = cell || W.key; EXM.laid = []; EXM.steps = 0; EXM.sel = null; EXM.cands = null; EXM.hover = -1; EXM.closing = null;
  EXM.name = (W.info && (W.info.name || W.info.key)) || 'the place';
  if (W.sel){ W.sel = null; if (typeof renderWside === 'function') renderWside(); }
  extendPanel();
  await extendEdges();
  extendBanner();
  if (edge){ const e = EXM.edges.find(x => x.ref === edge.ref && x.side === edge.side) || EXM.edges.find(x => x.ref === edge.ref); if (e) extendSelect(e); }
  if (V3.on && typeof v3Tools === 'function') v3Tools();
}

async function extendModeLeave(){
  if (!EXM.on) return;
  const n = EXM.steps, laid = EXM.laid.length;
  EXM.on = false;
  extendStripsClear(); extendLeavesClear();
  if (typeof v3GhostClear === 'function') v3GhostClear();
  if (EXM.panel){ EXM.panel.remove(); EXM.panel = null; }
  setBanner('');
  if (n > 1){
    try {
      const f = await post('/api/extend/fold', {n, note: `Extended ${EXM.name} by ${laid} piece${laid === 1 ? '' : 's'}`});
      toast(`${f.note}. One Undo takes it all back.`);
      if (typeof afterChange === 'function') afterChange();
    } catch (e){ toast(e.message, true); }
  } else if (n === 1) toast(`Extended ${EXM.name} by ${laid} piece${laid === 1 ? '' : 's'}. Undo takes it back.`);
  if (V3.on && typeof v3Tools === 'function') v3Tools();
  if (!V3.on) drawMap();
}

function extendBanner(){
  if (!EXM.on) return;
  const open = EXM.edges.length;
  setBanner(`<b>Extend</b>: click a gold strip (an open face of a piece) to see what the game joins there. <b>Tab</b> cycles the candidates, <b>Enter</b> lays, <b>Backspace</b> takes the last piece off, <b>Esc</b> leaves. ${open} open edge${open === 1 ? '' : 's'}.`);
}

async function extendEdges(){
  let r;
  try { r = await post('/api/extend/edges', {cell: EXM.cell}); } catch (e){ toast(e.message, true); return; }
  if (!EXM.on) return;
  EXM.edges = r.edges || [];
  EXM.style = r.style;
  if (r.note) toast(r.note);
  extendStrips();
  extendCounter();
  if (!V3.on) drawMap();
}

// ----- the strips in the 3D view: flat quads 8 units wide along each open face's floor line
function extendStripsClear(){
  if (EXM.group && V3.scene){ V3.scene.remove(EXM.group); }
  EXM.group = null;
  if (V3.on && typeof v3Refresh === 'function') v3Refresh();
}
function extendStripMesh(a, b, color, width, lift){
  const T = THREE, dx = b[0] - a[0], dy = b[1] - a[1], L = Math.hypot(dx, dy) || 1;
  const g = new T.PlaneGeometry(L, width);
  // (seen through walls and ceilings, like the grid: an open edge is visible all the time, from above too)
  const m = new T.MeshBasicMaterial({color, transparent: true, opacity: 0.9, depthWrite: false, depthTest: false, side: T.DoubleSide});
  const mesh = new T.Mesh(g, m);
  mesh.position.set((a[0] + b[0]) / 2 - V3.origin[0], (a[1] + b[1]) / 2 - V3.origin[1], a[2] - V3.origin[2] + (lift || 3));
  mesh.rotation.z = Math.atan2(dy, dx);
  mesh.renderOrder = 7;
  // (and a low ribbon standing on the line, so the strip reads from the side and from far above alike)
  const rib = new T.Mesh(new T.PlaneGeometry(L, width * 2.5), m);
  rib.rotation.x = Math.PI / 2;
  rib.position.set(0, 0, width * 1.25);
  mesh.add(rib);
  return mesh;
}
function extendStrips(){
  extendStripsClear();
  if (!V3.on || !V3.scene) return;
  const T = THREE, g = new T.Group();
  for (const e of EXM.edges){
    const color = e.void ? EXM_RED : EXM_GOLD;
    const segs = e.rim ? [[e.rim[0], e.rim[1]], [e.rim[1], e.rim[2]], [e.rim[2], e.rim[3]], [e.rim[3], e.rim[0]]] : [[e.a, e.b]];
    for (const [a, b] of segs){
      const mesh = extendStripMesh(a, b, color, e.rim ? 6 : 8, 3);
      if (!e.rim){ mesh.position.x += e.out[0] * 2; mesh.position.y += e.out[1] * 2; }
      mesh.userData.edge = e; mesh.userData.base = color;
      g.add(mesh);
    }
  }
  EXM.group = g; V3.scene.add(g);
  v3Refresh();
}
function extendLeavesClear(){
  if (EXM.leaveGroup && V3.scene) V3.scene.remove(EXM.leaveGroup);
  EXM.leaveGroup = null;
}
function extendLeaves(leaves){
  extendLeavesClear();
  if (!V3.on || !V3.scene || !leaves || !leaves.length) return;
  const g = new THREE.Group();
  for (const e of leaves){
    const segs = e.rim ? [[e.rim[0], e.rim[1]], [e.rim[1], e.rim[2]], [e.rim[2], e.rim[3]], [e.rim[3], e.rim[0]]] : [[e.a, e.b]];
    for (const [a, b] of segs) g.add(extendStripMesh(a, b, e.void ? EXM_RED : EXM_LIT, 6, 5));
  }
  EXM.leaveGroup = g; V3.scene.add(g); v3Refresh();
}
function extendStripLight(edge, lit){
  if (!EXM.group) return;
  for (const m of EXM.group.children){
    const mine = m.userData.edge === edge;
    m.material.color.setHex(mine && lit ? EXM_LIT : m.userData.base);
    m.material.opacity = mine && lit ? 1 : (EXM.sel && m.userData.edge === EXM.sel ? 1 : 0.9);
  }
}
// a strip under the mouse in the 3D view (called from world3d's click and hover); true when one was handled
function extendPick3D(e, click){
  if (!EXM.on || !EXM.group || !V3.on) return false;
  V3.ray.setFromCamera(v3Mouse(e), V3.camera);
  const hits = V3.ray.intersectObjects(EXM.group.children, true);
  const pick = o => { while (o && !o.userData.edge) o = o.parent; return o ? o.userData.edge : null; };
  const hit = hits.length ? pick(hits[0].object) : null;
  const tip = $('#maptip');
  if (click){
    if (!hit) return false;
    extendSelect(hit);
    return true;
  }
  if (hit !== EXM.hoverEdge){
    if (EXM.hoverEdge && EXM.hoverEdge !== EXM.sel) extendStripLight(EXM.hoverEdge, false);
    EXM.hoverEdge = hit;
    if (hit) extendStripLight(hit, true);
    v3Refresh();
  }
  if (hit){
    const b = $('#v3wrap').getBoundingClientRect();
    tip.style.display = 'block'; tip.style.left = (e.clientX - b.left + 14) + 'px'; tip.style.top = (e.clientY - b.top + 10) + 'px';
    tip.innerHTML = `<b>Open edge</b> ${esc(hit.words)}`;
    return true;
  }
  return false;
}

// ----- the map (2D): the strips drawn on the floor lines, a click on one selects it
function extendDraw(g){
  if (!EXM.on || V3.on) return;
  const z = W.cam.z;
  for (const e of EXM.edges){
    const segs = e.rim ? [[e.rim[0], e.rim[1]], [e.rim[1], e.rim[2]], [e.rim[2], e.rim[3]], [e.rim[3], e.rim[0]]] : [[e.a, e.b]];
    const sel = e === EXM.sel, hov = e === EXM.hoverEdge;
    g.save(); g.strokeStyle = e.void ? '#e25a4a' : (sel || hov ? '#fff0b0' : '#f0cd87'); g.lineWidth = sel ? 5 : 3; g.globalAlpha = e.rim ? 0.5 : 0.95;
    for (const [a, b] of segs){ const [x0, y0] = toScreen(a[0], a[1]), [x1, y1] = toScreen(b[0], b[1]); g.beginPath(); g.moveTo(x0, y0); g.lineTo(x1, y1); g.stroke(); }
    g.restore();
  }
  // the hovered candidate: its footprint, from the ghost items (the model box is not known here: a mark and the name)
  if (EXM.ghost){
    for (const it of EXM.ghost){
      const [sx, sy] = toScreen(it.p[0], it.p[1]);
      g.save(); g.strokeStyle = '#f0cd87'; g.fillStyle = '#f0cd8733'; g.lineWidth = 1.5;
      const a = Math.max(6, 120 * z);
      g.translate(sx, sy); g.rotate(it.p[5]); g.fillRect(-a, -a, a * 2, a * 2); g.strokeRect(-a, -a, a * 2, a * 2); g.restore();
    }
  }
}
function extendMapClick(e){
  if (!EXM.on || V3.on) return false;
  let best = null, bd = 10;
  for (const ed of EXM.edges){
    const segs = ed.rim ? [[ed.rim[0], ed.rim[1]], [ed.rim[1], ed.rim[2]], [ed.rim[2], ed.rim[3]], [ed.rim[3], ed.rim[0]]] : [[ed.a, ed.b]];
    for (const [a, b] of segs){
      const [x0, y0] = toScreen(a[0], a[1]), [x1, y1] = toScreen(b[0], b[1]);
      const dx = x1 - x0, dy = y1 - y0, L2 = dx * dx + dy * dy || 1;
      const t = Math.max(0, Math.min(1, ((e.offsetX - x0) * dx + (e.offsetY - y0) * dy) / L2));
      const d = Math.hypot(e.offsetX - (x0 + t * dx), e.offsetY - (y0 + t * dy));
      if (d < bd){ bd = d; best = ed; }
    }
  }
  if (!best) return false;
  extendSelect(best);
  return true;
}

// ----- the panel beside the view: the patterns, the candidates, the counter and Close it
function extendPanel(){
  if (EXM.panel) EXM.panel.remove();
  const p = document.createElement('div'); p.className = 'modal'; p.id = 'exm-panel';
  // (beside the view, inside it: over the map or the 3D view, never over the Place panel)
  p.style.cssText = 'position:absolute;right:8px;top:44px;width:270px;max-height:calc(100% - 56px);overflow:auto;z-index:30;box-shadow:0 6px 24px #0008;padding:10px';
  p.innerHTML = `<h2 style="margin:0 0 4px;font-size:15px;display:flex;align-items:center;gap:6px">⬚ Extend <span class="msg" id="exm-count" style="font-weight:normal;flex:1"></span><button class="btn sm" id="exm-leave" title="Leave (Esc): the pieces laid become one change">Done</button></h2>
    <div class="msg" id="exm-where">Click a gold strip: an open face of a piece.</div>
    <div id="exm-patterns"></div>
    <div id="exm-cands"></div>
    <div style="margin-top:8px;display:flex;gap:6px;align-items:center;flex-wrap:wrap"><button class="btn sm" id="exm-close" disabled title="The game's closers on the new pieces only: loose walls, caps, posts, railings. Shows them first.">Close it</button>
      <button class="btn sm" id="exm-back" disabled title="Take the last piece off (Backspace)">⌫ Last off</button><span class="msg" id="exm-closenote"></span></div>`;
  const host = (V3.on && $('#v3wrap')) || (typeof cv !== 'undefined' && cv.parentElement) || document.body;
  if (host !== document.body && getComputedStyle(host).position === 'static') host.style.position = 'relative';
  host.appendChild(p);
  EXM.panel = p;
  p.querySelector('#exm-leave').onclick = () => extendModeLeave();
  p.querySelector('#exm-back').onclick = () => extendBack();
  p.querySelector('#exm-close').onclick = () => extendCloseIt();
}
function extendCounter(){
  const c = EXM.panel && EXM.panel.querySelector('#exm-count'); if (!c) return;
  const n = EXM.edges.length, v = EXM.edges.filter(e => e.void).length;
  c.textContent = `${n} open edge${n === 1 ? '' : 's'}${v ? ` (${v} showing the void)` : ''}`;
  const b = EXM.panel.querySelector('#exm-back'); if (b) b.disabled = !EXM.steps;
  const cl = EXM.panel.querySelector('#exm-close'); if (cl) cl.disabled = !EXM.laid.length;
}

async function extendSelect(edge){
  if (!EXM.on || EXM.busy) return;
  if (EXM.sel) extendStripLight(EXM.sel, false);
  EXM.sel = edge; EXM.hover = -1; EXM.cands = null;
  extendStripLight(edge, true);
  if (!V3.on) drawMap();
  const P = EXM.panel, q = s => P.querySelector(s);
  q('#exm-where').innerHTML = `<span class="spin"></span> ${esc(edge.words)}`;
  q('#exm-patterns').innerHTML = ''; q('#exm-cands').innerHTML = '';
  let r;
  try { r = await post('/api/extend/candidates', {cell: EXM.cell, ref: edge.ref, side: edge.side}); }
  catch (e){ q('#exm-where').textContent = e.message; return; }
  if (!EXM.on || EXM.sel !== edge) return;
  EXM.cands = r;
  const sides = {E: 'east', W: 'west', N: 'north', S: 'south', U: 'top', D: 'underside'};
  q('#exm-where').innerHTML = `The <b>${sides[r.side]}</b> face of a <b>${esc(r.label)}</b>: the game joins something here in ${r.n} of its places.${r.note ? ' ' + esc(r.note) : ''}`;
  // patterns: thumbnails of the whole assembly (the root piece's picture with a count), a handle on a run
  if (r.patterns && r.patterns.length){
    q('#exm-patterns').innerHTML = `<div class="msg" style="margin-top:6px">Patterns the game repeats here</div>` + r.patterns.map((pt, n) => `
      <div class="exm-pat" data-pat="${n}" style="display:flex;gap:8px;align-items:center;padding:4px;border:1px solid var(--line,#444);border-radius:6px;margin-top:4px;cursor:pointer">
        <img data-tid="${esc(pt.id)}" data-ts="56" width="56" height="56" style="border-radius:4px;background:#0006">
        <div style="flex:1;min-width:0"><div style="font-size:12.5px"><b>${esc(pt.label)}</b></div><div class="msg">${esc(pt.words || '')}</div>
          ${pt.kind === 'run' ? `<input type="range" min="${pt.min}" max="${pt.max}" value="${pt.n}" data-run="${n}" style="width:100%" title="How many"> <span class="msg" data-runn="${n}">${pt.n} pieces</span>` : `<div class="exm-bar"><i style="width:${Math.round(100 * Math.min(1, pt.share))}%"></i></div>`}
        </div></div>`).join('');
    P.querySelectorAll('.exm-pat').forEach(el => {
      const pt = r.patterns[+el.dataset.pat];
      el.onmouseenter = () => extendGhost(pt.ghost, null);
      el.onmouseleave = () => { if (EXM.hover < 0) extendGhost(null); };
      el.onclick = ev => { if (ev.target.tagName === 'INPUT') return; extendLay(pt.ghost, `Laid ${pt.label} (${pt.ghost.length} pieces)`); };
    });
    P.querySelectorAll('[data-run]').forEach(inp => {
      const pt = r.patterns[+inp.dataset.run];
      inp.oninput = async () => {
        const n = +inp.value; P.querySelector(`[data-runn="${inp.dataset.run}"]`).textContent = n + ' pieces';
        try { const g = await post('/api/extend/run', {cell: EXM.cell, ref: edge.ref, rel: pt.rel, n}); if (EXM.cands === r){ pt.ghost = g.ghost; pt.n = n; extendGhost(pt.ghost, null); } } catch (e){}
      };
    });
  }
  // the candidates: thumbnail, name, the game's share as a bar
  if (!r.candidates.length) q('#exm-cands').innerHTML = `<div class="msg" style="margin-top:6px">${esc(r.note || 'Nothing the game joins here.')}</div>`;
  else q('#exm-cands').innerHTML = `<div class="msg" style="margin-top:6px">What the game joins here, most often first</div>` + r.candidates.map((c, n) => `
      <div class="exm-cand" data-cand="${n}" style="display:flex;gap:8px;align-items:center;padding:4px;border-radius:6px;margin-top:2px;cursor:${c.blocked ? 'not-allowed' : 'pointer'};opacity:${c.blocked ? 0.5 : 1}">
        <img data-tid="${esc(c.id)}" data-ts="48" width="48" height="48" style="border-radius:4px;background:#0006">
        <div style="flex:1;min-width:0"><div style="font-size:12.5px"><b>${esc(c.label)}</b>${c.turn ? ` <span class="msg">turned ${c.turn}°</span>` : ''}${c.blocked ? ' <span class="msg">(runs into the house)</span>' : ''}</div>
          <div class="exm-bar" title="${Math.round(100 * c.share)}% of ${r.n}"><i style="width:${Math.round(100 * c.share)}%"></i></div>
          <div class="msg">${c.n} time${c.n === 1 ? '' : 's'} in ${r.n} · leaves ${c.leaves.length} open</div></div></div>`).join('');
  P.querySelectorAll('.exm-cand').forEach(el => {
    const n = +el.dataset.cand, c = r.candidates[n];
    el.onmouseenter = () => extendHover(n);
    el.onmouseleave = () => { if (EXM.hover === n && !EXM.keyHover) extendHover(-1); };
    el.onclick = () => { if (!c.blocked) extendLay(c.ghost, `Laid ${c.label}`); };
  });
  if (typeof v3ThumbScan === 'function') v3ThumbScan(P);
  if (!document.getElementById('exm-style')){
    const st = document.createElement('style'); st.id = 'exm-style';
    st.textContent = '.exm-bar{height:5px;background:#0006;border-radius:3px;margin:3px 0}.exm-bar i{display:block;height:100%;background:var(--gold,#f0cd87);border-radius:3px}.exm-cand.on,.exm-pat:hover{background:#f0cd8722}';
    document.head.appendChild(st);
  }
}

function extendGhost(items, leaves){
  EXM.ghost = items;
  if (V3.on && typeof v3GhostAt === 'function'){ if (items) v3GhostAt(items); else v3GhostClear(); }
  extendLeaves(leaves);
  if (!V3.on) drawMap();
}
function extendHover(n, byKey){
  const r = EXM.cands; if (!r) return;
  EXM.hover = n; EXM.keyHover = !!byKey;
  EXM.panel.querySelectorAll('.exm-cand').forEach(el => el.classList.toggle('on', +el.dataset.cand === n));
  const c = n >= 0 ? r.candidates[n] : null;
  extendGhost(c ? c.ghost : null, c ? c.leaves : null);
  if (c && byKey){ const el = EXM.panel.querySelector(`.exm-cand[data-cand="${n}"]`); if (el) el.scrollIntoView({block: 'nearest'}); }
}

async function extendLay(items, label){
  if (!EXM.on || EXM.busy || !items || !items.length) return;
  EXM.busy = true;
  const sel = EXM.sel;
  try {
    const m = await post('/api/extend/lay', {cell: EXM.cell, items, label});
    EXM.laid.push(...m.changed); EXM.steps++;
    extendGhost(null);
    if (typeof worldReloadCell === 'function') await worldReloadCell(EXM.cell);
    if (typeof afterChange === 'function') afterChange();
    if (V3.on) v3Refresh();
    await extendEdges();
    // the piece just laid is the current one: its open face on the same side, else its first
    const last = m.changed[m.changed.length - 1];
    const mine = EXM.edges.filter(e => e.ref === last);
    const next = mine.find(e => sel && e.side === sel.side) || mine[0];
    EXM.sel = null;
    if (next){ EXM.busy = false; await extendSelect(next); }
    else { EXM.panel.querySelector('#exm-where').textContent = 'Laid. The new piece has no open face the game fills: click another strip.'; EXM.panel.querySelector('#exm-patterns').innerHTML = ''; EXM.panel.querySelector('#exm-cands').innerHTML = ''; }
    extendBanner();
  } catch (e){ toast(e.message, true); }
  finally { EXM.busy = false; }
}

async function extendBack(){
  if (!EXM.on || EXM.busy || !EXM.steps) return;
  EXM.busy = true;
  try {
    const r = await post('/api/undo', {});
    EXM.steps--;
    // (a step may have laid several pieces: a pattern; the refs it made are no longer here)
    extendGhost(null);
    if (typeof worldReloadCell === 'function') await worldReloadCell(EXM.cell);
    const have = new Set((W.cells[EXM.cell] || {refs: []}).refs.map(x => x.k));
    EXM.laid = EXM.laid.filter(k => have.has(k));
    if (typeof afterChange === 'function') afterChange();
    if (V3.on) v3Refresh();
    await extendEdges();
    toast('Took the last piece off (' + (r.undone || []).join('; ') + ').');
    const sel = EXM.sel; EXM.sel = null;
    const again = sel && EXM.edges.find(e => e.ref === sel.ref && e.side === sel.side);
    EXM.busy = false;
    if (again) await extendSelect(again); else { EXM.panel.querySelector('#exm-where').textContent = 'Click a strip.'; EXM.panel.querySelector('#exm-patterns').innerHTML = ''; EXM.panel.querySelector('#exm-cands').innerHTML = ''; }
    extendBanner();
  } catch (e){ toast(e.message, true); }
  finally { EXM.busy = false; }
}

// "Close it": the closing pieces on the new pieces only, shown first (a ghost of each), laid on the second click
async function extendCloseIt(){
  if (!EXM.on || EXM.busy || !EXM.laid.length) return;
  const P = EXM.panel, b = P.querySelector('#exm-close'), note = P.querySelector('#exm-closenote');
  if (EXM.closing){
    EXM.busy = true; b.disabled = true;
    try {
      const m = await post('/api/extend/close', {cell: EXM.cell, refs: EXM.laid, preview: false});
      EXM.laid.push(...(m.changed || [])); EXM.steps++; EXM.closing = null;
      extendGhost(null);
      if (typeof worldReloadCell === 'function') await worldReloadCell(EXM.cell);
      if (typeof afterChange === 'function') afterChange();
      if (V3.on) v3Refresh();
      await extendEdges();
      note.textContent = `Laid ${m.count} closing piece${m.count === 1 ? '' : 's'}.`; b.textContent = 'Close it';
      extendBanner();
    } catch (e){ toast(e.message, true); }
    finally { EXM.busy = false; extendCounter(); }
    return;
  }
  b.disabled = true; note.innerHTML = '<span class="spin"></span> Looking…';
  try {
    const m = await post('/api/extend/close', {cell: EXM.cell, refs: EXM.laid, preview: true});
    if (!m.count){ note.textContent = 'Nothing to close on the new pieces.'; b.disabled = false; return; }
    EXM.closing = m;
    extendGhost(m.ghost, null);
    note.textContent = `${m.count} piece${m.count === 1 ? '' : 's'} would close them (shown). Click again to lay them.`;
    b.textContent = `Lay ${m.count}`; b.disabled = false;
  } catch (e){ note.textContent = e.message; b.disabled = false; }
}

// keys: Tab cycles, Enter lays, Backspace takes off, Esc leaves (heard before the view's own keys)
window.addEventListener('keydown', e => {
  if (!EXM.on) return;
  const t = e.target; if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable)) return;
  if (e.key === 'Escape'){ e.preventDefault(); e.stopImmediatePropagation(); extendModeLeave(); return; }
  if (e.key === 'Tab'){
    e.preventDefault(); e.stopImmediatePropagation();
    const r = EXM.cands; if (!r || !r.candidates.length) return;
    const ok = r.candidates.map((c, n) => n).filter(n => !r.candidates[n].blocked); if (!ok.length) return;
    const i = ok.indexOf(EXM.hover), next = ok[(i + (e.shiftKey ? -1 : 1) + ok.length) % ok.length];
    extendHover(next, true); return;
  }
  if (e.key === 'Enter'){
    const r = EXM.cands; if (!r || EXM.hover < 0) return;
    e.preventDefault(); e.stopImmediatePropagation();
    const c = r.candidates[EXM.hover]; if (c && !c.blocked) extendLay(c.ghost, `Laid ${c.label}`); return;
  }
  if (e.key === 'Backspace'){ e.preventDefault(); e.stopImmediatePropagation(); extendBack(); }
}, true);

async function extendBuild(){
  const card = EX.card; if (!card || EX.busy) return;
  const q = s => card.querySelector(s);
  EX.busy = true; q('#ex-go').disabled = true; q('#ex-go').innerHTML = '<span class="spin"></span> Building…';
  try {
    const m = await post('/api/extend/apply', {cell: EX.cell, ref: EX.ref, at: EX.at, w: EX.w, h: EX.h, shift: EX.shift, name: EX.name,
                                               furnish: EX.furnish, level: (typeof furnishAsValue === 'function' && $('#fu-level')) ? furnishAsValue('fu') : null});
    const cell = EX.cell;
    extendClose();
    toast(`Added the ${m.room} (${m.pieces} pieces${m.furnished ? ', ' + m.placed + ' things' : ''}). Undo takes it back.` + (m.note ? ' ' + m.note : ''), !!m.note);
    if (typeof worldReloadCell === 'function') await worldReloadCell(cell);
    if (typeof afterChange === 'function') afterChange();
    if (typeof v3Refresh === 'function' && V3.on) v3Refresh();
    W.roomInfo = {}; W.dressable = {};
  } catch (e){
    EX.busy = false;
    if (EX.card){ q('#ex-err').textContent = e.message; q('#ex-go').disabled = false; q('#ex-go').textContent = 'Build it'; }
  }
}

function extendClose(){
  if (EX.card){ EX.card.remove(); EX.card = null; }
  EX.busy = false; EX.sketchN = (EX.sketchN || 0) + 1;
  if (typeof v3GhostClear === 'function') v3GhostClear();
}
