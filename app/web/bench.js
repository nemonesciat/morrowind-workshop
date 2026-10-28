// The prefab workbench (bench.py): an empty space with a floor grid and its own camera, where a building is put
// together from the game's own pieces of a style, snapped the way the game joins them, its doors and windows
// filled in the game's way, checked as it grows, and then set down in the world in one go as one ghost on the land
// (one Undo). What is on the bench is kept between sessions; it stays on the bench after it is placed.
//
// The user, on what a prefab tool should be (2026-10-27): "a builder view where you snap pieces together, and then
// can lift that built structure, which benefits from tools like snapping matching pieces together and filling in
// windows and doors, and previewing it whole on the land before you place it in one go".
//
// The scene is its own (renderer, camera, grid), drawn from the 3D view's models (V3.models, v3EnsureModels);
// snapping is the 3D view's: the game's joins first (bench.py snaps, as v3SnapGame), flush faces after (v3SnapFlush).
const BN = {open: false, style: null, pieces: [], objs: new Map(), sel: null, hist: [], fut: [], next: 1, shelf: null,
            check: null, marks: [], drag: null, yaw: -0.7, pitch: -0.5, dist: 2400, target: null, mode: 'translate', q: ''};
const BN_SNAP = 80;              // a game spot this near (units) takes the piece
const BN_GRID = 256;             // the floor grid's step: the building pieces' own

function benchCss(){
  if ($('#benchcss')) return;
  const c = document.createElement('style'); c.id = 'benchcss';
  c.textContent = `#bench{position:absolute;inset:0;z-index:30;display:grid;grid-template-columns:270px 1fr;background:var(--bg)}
  #bench .bnshelf{display:flex;flex-direction:column;min-height:0;border-right:1px solid var(--line);background:var(--panel)}
  #bench .bnshelf .bnhead{padding:8px 10px;border-bottom:1px solid var(--line)}
  #bench .bnshelf .bnlist{overflow:auto;flex:1;padding:4px 6px 10px}
  #bench details{margin:4px 0} #bench summary{cursor:pointer;font-weight:600;padding:3px 2px}
  #bench .bngrid{display:grid;grid-template-columns:repeat(3,1fr);gap:4px;margin:4px 0}
  #bench .bnpc{border:1px solid var(--line);border-radius:6px;background:var(--panel2);padding:3px;cursor:grab;text-align:center;font-size:10.5px;overflow:hidden}
  #bench .bnpc:hover{border-color:var(--gold)} #bench .bnpc img,#bench .bnpc .nothumb{width:64px;height:64px;display:block;margin:0 auto}
  #bench .bnpc span{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--muted)}
  #bench .bnview{position:relative;min-width:0;min-height:0;overflow:hidden}
  #bench .bnview canvas{display:block;outline:none}
  #bench .bntools{position:absolute;left:8px;right:8px;top:8px;display:flex;gap:5px;flex-wrap:wrap;align-items:center;z-index:2}
  #bench .bnnote{position:absolute;left:50%;bottom:12px;transform:translateX(-50%);background:var(--panel);color:var(--text);border:1px solid var(--line0);
    padding:4px 10px;border-radius:6px;font-size:12px;pointer-events:none;display:none;z-index:2}
  #bench .bncheck{position:absolute;right:8px;bottom:8px;width:330px;max-height:45%;overflow:auto;background:var(--panel);border:1px solid var(--line);
    border-radius:8px;padding:8px 10px;font-size:12px;z-index:2}
  #bench .bncheck .sev-error{color:var(--red)} #bench .bncheck .sev-warning{color:var(--amber)} #bench .bncheck .sev-ok{color:var(--green)}
  #bench .bnpop{position:absolute;left:8px;top:48px;width:380px;max-height:70%;overflow:auto;background:var(--panel);border:1px solid var(--line);
    border-radius:8px;padding:8px;z-index:3;box-shadow:0 6px 20px #0006}
  #bench .bnpop button.row{display:block;width:100%;text-align:left;margin:2px 0}
  #bench .bnhelp{position:absolute;left:8px;bottom:8px;max-width:420px;font-size:11.5px;color:var(--muted);background:var(--panel);border:1px solid var(--line0);
    border-radius:6px;padding:4px 8px;z-index:2}`;
  document.head.appendChild(c);
}

// ----- opening and closing
async function benchOpen(){
  benchCss();
  if (typeof showView === 'function') showView('world');
  let box = $('#bench');
  if (!box){
    box = document.createElement('div'); box.id = 'bench';
    $('#v3wrap').parentElement.appendChild(box);
  }
  box.style.display = 'grid';
  BN.open = true;
  box.innerHTML = `<div class="bnshelf"><div class="bnhead"><b>🔨 Prefab workbench</b>
      <div class="pfrow" style="display:flex;gap:6px;align-items:center;margin-top:6px"><label>Style <select id="bn-style"></select></label></div>
      <input id="bn-q" placeholder="Find a piece…" style="width:100%;margin-top:6px" value="${esc(BN.q)}"></div>
      <div class="bnlist" id="bn-list"><div class="msg">Reading the pieces…</div></div></div>
    <div class="bnview" id="bn-view">
      <div class="bntools">
        <button class="btn sm" id="bn-start" title="Begin from one of the game's buildings of this style, then change it">🏠 Start from a game building…</button>
        <button class="btn sm" id="bn-fill" title="Put the style's own doors in doorways and windows in window holes, where the game puts them">🚪 Fill the openings</button>
        <button class="btn sm" id="bn-check" title="Gaps in the walls, an open roof, pieces touching nothing">🔍 Check</button>
        <button class="btn sm" id="bn-undo" title="Undo on the bench (Ctrl+Z)">↶</button><button class="btn sm" id="bn-redo" title="Redo (Ctrl+Y)">↷</button>
        <button class="btn sm" id="bn-clear" title="Take everything off the bench">Clear</button>
        <button class="btn sm" id="bn-save" title="Keep it in the Library's prefabs too">💾 Save as prefab…</button>
        <button class="btn primary sm" id="bn-place" title="Set the whole structure down in the world: it follows the mouse on the land, the wheel turns it, a click puts it down (one Undo)">⤓ Place in the world</button>
        <span style="flex:1"></span>
        <button class="btn sm" id="bn-close" title="Back to the World map (the bench is kept)">✕ Close</button>
      </div>
      <div class="bnnote" id="bn-note"></div>
      <div class="bncheck" id="bn-checkbox" style="display:none"></div>
      <div class="bnhelp" id="bn-help">Drag pieces in from the shelf (or click one). Click a piece to move it: it snaps where the game joins it, or flush.
        <b>R</b> turn handles, <b>T</b> move handles, <b>Q</b>/<b>E</b> turn 15°, <b>Del</b> remove, <b>D</b> copy. Drag the background to look round, right-drag to pan, wheel to zoom.</div>
    </div>`;
  $('#bn-close').onclick = benchClose;
  $('#bn-start').onclick = benchStartMenu;
  $('#bn-fill').onclick = benchFill;
  $('#bn-check').onclick = () => benchCheck(true);
  $('#bn-undo').onclick = benchUndo; $('#bn-redo').onclick = benchRedo;
  $('#bn-clear').onclick = () => { if (!BN.pieces.length || confirm('Take everything off the bench?')){ benchPush(); BN.pieces = []; benchSync(); benchChanged(); } };
  $('#bn-save').onclick = benchSavePrefab;
  $('#bn-place').onclick = benchPlace;
  $('#bn-q').oninput = e => { BN.q = e.target.value; benchShelfRender(); };
  await v3Script();
  benchScene();
  if (!BN.loaded){
    try { const d = await api('/api/bench'); BN.pieces = (d.pieces || []).map(p => Object.assign({}, p, {k: String(p.k || BN.next++)})); BN.style = d.style || BN.style; } catch (e) {}
    BN.next = 1 + Math.max(0, ...BN.pieces.map(p => +p.k || 0));
    BN.loaded = true;
  }
  await benchStyles();
  benchSync();
  benchLoop();
  if (BN.pieces.length) benchCheck(false);
}

function benchClose(){
  BN.open = false;
  const box = $('#bench'); if (box) box.style.display = 'none';
  benchSaveSoon(0);
}

// ----- the styles and the shelf
async function benchStyles(){
  const sel = $('#bn-style'); if (!sel) return;
  let st;
  try { st = (await api('/api/build/modules')).styles || {}; }
  catch (e){
    $('#bn-list').innerHTML = `<div class="msg">${/still learning/i.test(e.message) ? 'The Workshop is learning how the game puts its buildings together (a few minutes, once). The shelf fills in by itself when it is done.' : esc(e.message)}</div>
      ${typeof learnHtml === 'function' && typeof LEARN !== 'undefined' && LEARN.sv && LEARN.sv.left ? learnHtml(LEARN.sv, true) : ''}`;
    clearTimeout(BN.styleT); BN.styleT = setTimeout(() => { if (BN.open) benchStyles(); }, 5000);
    return;
  }
  const names = Object.keys(st).sort((a, b) => st[b] - st[a]);
  if (!BN.style || !names.includes(BN.style)) BN.style = names[0] || 'Hlaalu';
  sel.innerHTML = names.map(n => `<option ${n === BN.style ? 'selected' : ''}>${esc(n)}</option>`).join('');
  sel.onchange = () => { BN.style = sel.value; BN.shelf = null; benchShelf(); benchSaveSoon(); };
  benchShelf();
}

async function benchShelf(){
  const list = $('#bn-list'); if (!list) return;
  if (!BN.shelf || BN.shelf.style !== BN.style){
    list.innerHTML = '<div class="msg">Reading the pieces…</div>';
    try { BN.shelf = await api('/api/bench/shelf?style=' + encodeURIComponent(BN.style)); } catch (e){ list.innerHTML = `<div class="msg">${esc(e.message)}</div>`; return; }
  }
  benchShelfRender();
}

function benchShelfRender(){
  const list = $('#bn-list'); if (!list || !BN.shelf) return;
  const q = BN.q.trim().toLowerCase();
  BN.openKinds = BN.openKinds || new Set(['wall', 'door']);
  list.innerHTML = BN.shelf.kinds.map(k => {
    const ps = k.pieces.filter(p => !q || p.id.toLowerCase().includes(q));
    if (!ps.length) return '';
    return `<details data-kind="${k.kind}" ${q || BN.openKinds.has(k.kind) ? 'open' : ''}><summary>${esc(k.label)} <span class="msg">${ps.length}</span></summary>
      <div class="bngrid">${ps.map(p => `<div class="bnpc" draggable="true" data-id="${esc(p.id)}" data-type="${p.tag}" title="${esc(p.id)}: the game uses it ${p.n}×. Drag it onto the bench, or click it.">
        <img data-tid="${esc(p.id)}" data-ts="64" data-tt="${p.tag}" alt=""><span>${esc(p.id)}</span></div>`).join('')}</div></details>`;
  }).join('') || '<div class="msg">No piece by that name.</div>';
  list.querySelectorAll('details').forEach(d => d.ontoggle = () => { if (d.open){ BN.openKinds.add(d.dataset.kind); v3ThumbScan(d); } else BN.openKinds.delete(d.dataset.kind); });
  list.querySelectorAll('details[open]').forEach(d => v3ThumbScan(d));
  list.querySelectorAll('.bnpc').forEach(el => {
    el.ondragstart = e => { e.dataTransfer.setData('text/x-bench', el.dataset.id); e.dataTransfer.effectAllowed = 'copy'; BN.dragIn = {id: el.dataset.id, type: el.dataset.type}; };
    el.ondragend = () => { BN.dragIn = null; };
    el.onclick = () => benchAddAt(el.dataset.id, el.dataset.type, null);
  });
}

// ----- the scene
function benchScene(){
  const T = THREE, view = $('#bn-view');
  if (!BN.renderer){
    const r = new T.WebGLRenderer({antialias: true});
    r.setPixelRatio(window.devicePixelRatio || 1);
    r.domElement.tabIndex = 0;
    BN.renderer = r;
    BN.scene = new T.Scene();
    BN.camera = new T.PerspectiveCamera(55, 1, 4, 60000); BN.camera.up.set(0, 0, 1);
    BN.scene.add(new T.HemisphereLight(0xfff4e0, 0x50453a, 0.85));
    const sun = new T.DirectionalLight(0xfff0d8, 0.7); sun.position.set(0.6, -0.8, 1.5); BN.scene.add(sun);
    BN.scene.add(new T.AmbientLight(0xffffff, 0.25));
    BN.root = new T.Group(); BN.scene.add(BN.root);
    // (the floor: a grid on the building pieces' own step, and a plane under it to point at)
    const grid = new T.GridHelper(BN_GRID * 60, 60, 0xb8902f, 0x6a5f4d);
    grid.rotation.x = Math.PI / 2; grid.position.z = 0.5; grid.material.transparent = true; grid.material.opacity = 0.55;
    BN.scene.add(grid);
    BN.floor = new T.Mesh(new T.PlaneGeometry(BN_GRID * 200, BN_GRID * 200), new T.MeshLambertMaterial({color: 0x3a352d}));
    BN.scene.add(BN.floor);
    BN.ray = new T.Raycaster();
    const tc = new T.TransformControls(BN.camera, r.domElement);
    tc.setSpace('world'); tc.size = 0.9; tc.showX = tc.showY = true;
    tc.addEventListener('dragging-changed', e => { BN.tcBusy = e.value; e.value ? benchDragStart() : benchDragEnd(); });
    tc.addEventListener('objectChange', benchSnap);
    BN.scene.add(tc); BN.tc = tc;
    BN.selBox = new T.BoxHelper(undefined, 0xf0cd87); BN.selBox.visible = false; BN.scene.add(BN.selBox);
    benchBind(r.domElement);
    BN.target = new T.Vector3(0, 0, 150);
  }
  BN.scene.background = new T.Color(0x8a9aa8);
  view.insertBefore(BN.renderer.domElement, view.firstChild);
  benchResize();
}
function benchResize(){
  if (!BN.renderer || !BN.open) return;
  const b = $('#bn-view').getBoundingClientRect();
  BN.renderer.setSize(Math.max(1, b.width), Math.max(1, b.height));
  BN.camera.aspect = Math.max(1, b.width) / Math.max(1, b.height); BN.camera.updateProjectionMatrix();
}
window.addEventListener('resize', () => { if (BN.open) benchResize(); });

function benchLoop(){
  if (!BN.open){ BN.looping = false; return; }
  if (BN.looping) return;
  BN.looping = true;
  const tick = () => {
    if (!BN.open){ BN.looping = false; return; }
    const c = BN.camera, t = BN.target;
    c.position.set(t.x + BN.dist * Math.cos(BN.pitch) * Math.sin(BN.yaw), t.y - BN.dist * Math.cos(BN.pitch) * Math.cos(BN.yaw), t.z - BN.dist * Math.sin(BN.pitch));
    c.lookAt(t);
    if (BN.sel) BN.selBox.update();
    BN.renderer.render(BN.scene, c);
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

// the bench's pieces drawn: one object a piece, from the 3D view's models
async function benchSync(){
  const ids = [...new Set(BN.pieces.map(p => p.id))];
  if (ids.length) await v3EnsureModels(ids);
  const want = new Set(BN.pieces.map(p => p.k));
  for (const [k, o] of BN.objs) if (!want.has(k)){ BN.root.remove(o.g); BN.objs.delete(k); }
  for (const p of BN.pieces){
    let o = BN.objs.get(p.k);
    const look = p.id.toLowerCase() + '|' + (p.id.toLowerCase() in V3.models ? 1 : 0);
    if (!o || o.look !== look){
      if (o) BN.root.remove(o.g);
      o = {g: v3Build({id: p.id, type: p.type || 'STAT', b: null}), look, k: p.k, r: {id: p.id}};
      o.g.userData.bench = p.k;
      BN.root.add(o.g); BN.objs.set(p.k, o);
    }
    o.r = {id: p.id};
    if (!(BN.drag && BN.drag.o === o)) benchPose(o.g, p);
  }
  if (BN.sel && !BN.objs.has(BN.sel)) BN.sel = null;
  const so = BN.sel && BN.objs.get(BN.sel);
  if (so){ if (BN.tc.object !== so.g) BN.tc.attach(so.g); BN.tc.setMode(BN.mode); BN.tc.showX = BN.tc.showY = BN.mode !== 'rotate'; BN.selBox.setFromObject(so.g); BN.selBox.visible = true; }
  else { BN.tc.detach(); BN.selBox.visible = false; }
  if (!BN.framed && BN.pieces.length){ BN.framed = true; benchFrame(); }
}
function benchPose(g, p){
  g.position.set(p.p[0], p.p[1], p.p[2]);
  g.rotation.set(-(p.p[3] || 0), -(p.p[4] || 0), -(p.p[5] || 0), 'XYZ');
  g.scale.setScalar(p.s || 1);
  g.updateMatrixWorld(true);
}
// a piece's pose back from its object: the game's [x, y, z, rx, ry, rz]
function benchPoseOf(g){
  const e = new THREE.Euler().setFromQuaternion(g.quaternion, 'XYZ'), tw = 2 * Math.PI, r = a => +(((a % tw) + tw) % tw).toFixed(5);
  return [+g.position.x.toFixed(2), +g.position.y.toFixed(2), +g.position.z.toFixed(2), r(-e.x), r(-e.y), r(-e.z)];
}
function benchFrame(){
  if (!BN.pieces.length){ BN.target.set(0, 0, 150); BN.dist = 2400; return; }
  const b = new THREE.Box3(); for (const o of BN.objs.values()) b.expandByObject(o.g);
  if (b.isEmpty()) return;
  const c = b.getCenter(new THREE.Vector3()), s = b.getSize(new THREE.Vector3());
  BN.target.copy(c); BN.dist = Math.max(900, Math.max(s.x, s.y, s.z) * 1.6);
}

// ----- the mouse and the keys
function benchMouse(e){
  const r = BN.renderer.domElement.getBoundingClientRect();
  return new THREE.Vector2((e.clientX - r.left) / r.width * 2 - 1, -(e.clientY - r.top) / r.height * 2 + 1);
}
// what is under the mouse: a piece (its key), and the point on it or on the floor
function benchHit(e, skip){
  BN.ray.setFromCamera(benchMouse(e), BN.camera);
  const hits = BN.ray.intersectObjects([BN.root, BN.floor], true);
  for (const h of hits){
    let o = h.object; while (o && o.userData.bench == null && o !== BN.floor) o = o.parent;
    if (!o) continue;
    if (o === BN.floor) return {key: null, point: h.point};
    if (o.userData.bench === skip) continue;
    return {key: o.userData.bench, point: h.point};
  }
  return null;
}
function benchBind(el){
  let drag = null;
  el.addEventListener('contextmenu', e => e.preventDefault());
  el.addEventListener('mousedown', e => {
    el.focus();
    if (e.button === 0 && (BN.tc.dragging || BN.tc.axis)) return;
    drag = {b: e.button, x: e.clientX, y: e.clientY, yaw: BN.yaw, pitch: BN.pitch, t: BN.target.clone(), moved: false};
  });
  window.addEventListener('mousemove', e => {
    if (!drag || !BN.open) return;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
    if (!drag.moved) return;
    if (drag.b === 0){ BN.yaw = drag.yaw - dx * 0.006; BN.pitch = Math.max(-1.5, Math.min(-0.05, drag.pitch - dy * 0.005)); }
    else {
      // (pan along the floor, the floor following the mouse: right is (cos, sin) of the camera's turn, ahead is
      // (-sin, cos); faster the further the camera stands off)
      const k = BN.dist / 900, c = Math.cos(BN.yaw), s = Math.sin(BN.yaw);
      BN.target.set(drag.t.x - (c * dx + s * dy) * k, drag.t.y - (s * dx - c * dy) * k, drag.t.z);
    }
  });
  window.addEventListener('mouseup', e => {
    const d = drag; drag = null;
    if (!d || !BN.open || d.moved || e.target !== el) return;
    if (d.b !== 0) return;
    const h = benchHit(e);
    BN.sel = h && h.key ? h.key : null;
    benchSync();
  });
  el.addEventListener('wheel', e => { e.preventDefault(); BN.dist = Math.max(200, Math.min(30000, BN.dist * (e.deltaY > 0 ? 1.12 : 0.89))); }, {passive: false});
  el.addEventListener('dragover', e => { if (BN.dragIn){ e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; } });
  el.addEventListener('drop', e => {
    const id = e.dataTransfer.getData('text/x-bench'); if (!id) return;
    e.preventDefault();
    const h = benchHit(e);
    benchAddAt(id, (BN.dragIn && BN.dragIn.type) || 'STAT', h ? h.point : null);
  });
  el.addEventListener('keydown', e => {
    if (!BN.open) return;
    const k = e.key.toLowerCase();
    if ((e.ctrlKey || e.metaKey) && k === 'z'){ e.preventDefault(); benchUndo(); return; }
    if ((e.ctrlKey || e.metaKey) && k === 'y'){ e.preventDefault(); benchRedo(); return; }
    if (k === 'escape'){ BN.sel = null; benchSync(); return; }
    if (k === 'r'){ BN.mode = 'rotate'; benchSync(); return; }
    if (k === 't' || k === 'g'){ BN.mode = 'translate'; benchSync(); return; }
    const p = BN.sel && BN.pieces.find(q => q.k === BN.sel);
    if (!p) return;
    if (k === 'delete' || k === 'backspace'){ e.preventDefault(); benchPush(); BN.pieces = BN.pieces.filter(q => q !== p); BN.sel = null; benchSync(); benchChanged(); }
    else if (k === 'q' || k === 'e'){ benchPush(); p.p[5] = ((p.p[5] || 0) + (k === 'e' ? 1 : -1) * Math.PI / 12 + 2 * Math.PI) % (2 * Math.PI); benchSync(); benchChanged(); }
    else if (k === 'd'){ benchPush(); const c = {k: String(BN.next++), id: p.id, type: p.type, s: p.s, p: p.p.slice()}; c.p[0] += BN_GRID; BN.pieces.push(c); BN.sel = c.k; benchSync(); benchChanged(); }
  });
}

// ----- adding a piece: where it was dropped (on the floor or on a piece), else in front of the camera; then snapped
async function benchAddAt(id, type, point){
  benchPush();
  await v3EnsureModels([id]);
  const g = v3Build({id, type, b: null}), box = new THREE.Box3().setFromObject(g);
  const at = point ? point.clone() : BN.target.clone().setZ(0);
  const z = at.z - (box.isEmpty() ? 0 : box.min.z);
  const p = {k: String(BN.next++), id, type, s: 1, p: [Math.round(at.x), Math.round(at.y), Math.round(z), 0, 0, 0]};
  BN.pieces.push(p); BN.sel = p.k; BN.mode = 'translate';
  await benchSync();
  // (snapped at once where the game joins it to a piece beside it, else flush)
  const o = BN.objs.get(p.k);
  if (o && BN.pieces.length > 1){
    benchDragStart(o); await BN.drag.fetching; benchSnap(); benchDragEnd();
  } else benchChanged();
}

// ----- moving with the handles: the game's joins first, flush faces after (as the 3D view outdoors)
function benchDragStart(o){
  o = o || (BN.sel && BN.objs.get(BN.sel)); if (!o) return;
  const D = {o, startQ: o.g.quaternion.clone(), nearObjs: [...BN.objs.values()].filter(x => x !== o && x.g.position.distanceTo(o.g.position) < 4000), snaps: []};
  BN.drag = D;
  D.fetching = benchSnapsFetch(D);
}
async function benchSnapsFetch(D){
  const g = D.o.g, p = BN.pieces.find(q => q.k === D.o.k); if (!p) return;
  D.at = g.position.clone();
  try {
    const r = await post('/api/bench/snaps', {pieces: BN.pieces.filter(q => q !== p), id: p.id, x: g.position.x, y: g.position.y, z: g.position.z});
    if (BN.drag === D) D.snaps = r.snaps || [];
  } catch (e) {}
}
function benchSnap(){
  const D = BN.drag; if (!D) return;
  const g = D.o.g;
  if (BN.mode !== 'translate'){ BN.selBox.setFromObject(g); return; }
  if (D.at && g.position.distanceTo(D.at) > 800) D.fetching = benchSnapsFetch(D);
  let best = null;
  for (const s of D.snaps || []){
    const dx = s.p[0] - g.position.x, dy = s.p[1] - g.position.y, dz = s.p[2] - g.position.z;
    if (Math.hypot(dx, dy) >= BN_SNAP || Math.abs(dz) >= BN_SNAP) continue;
    const d = Math.hypot(dx, dy) + Math.abs(dz) * 0.5 - 30 * ((s.k || 1) - 1) - 6 * Math.log2(1 + s.n);
    if (!best || d < best.d) best = {s, d};
  }
  if (best){
    const s = best.s;
    g.position.set(s.p[0], s.p[1], s.p[2]); g.rotation.set(-s.p[3], -s.p[4], -s.p[5], 'XYZ');
    D.snapped = s;
    benchNote(`Joined to ${s.to} the way the game does it (${s.n}×)`);
  } else {
    D.snapped = null;
    g.quaternion.copy(D.startQ);
    const n = v3SnapFlush(D, g);
    benchNote(n ? `Flush with ${n.r.id}` : '');
  }
  g.updateMatrixWorld(true);
  BN.selBox.setFromObject(g);
}
function benchDragEnd(){
  const D = BN.drag; BN.drag = null;
  benchNote('');
  if (!D) return;
  const p = BN.pieces.find(q => q.k === D.o.k); if (!p) return;
  const np = benchPoseOf(D.o.g);
  if (np.some((v, i) => Math.abs(v - (p.p[i] || 0)) > 0.01)){ if (!BN.pushed) benchPush(); p.p = np; benchChanged(); }
  BN.pushed = false;
}
function benchNote(t){ const n = $('#bn-note'); if (n){ n.textContent = t; n.style.display = t ? 'block' : 'none'; } }

// ----- undo on the bench, and keeping it
function benchPush(){ BN.hist.push(JSON.stringify(BN.pieces)); if (BN.hist.length > 80) BN.hist.shift(); BN.fut = []; BN.pushed = true; }
function benchUndo(){ if (!BN.hist.length) return; BN.fut.push(JSON.stringify(BN.pieces)); BN.pieces = JSON.parse(BN.hist.pop()); benchSync(); benchChanged(true); }
function benchRedo(){ if (!BN.fut.length) return; BN.hist.push(JSON.stringify(BN.pieces)); BN.pieces = JSON.parse(BN.fut.pop()); benchSync(); benchChanged(true); }
function benchChanged(){
  BN.pushed = false;
  benchSaveSoon();
  clearTimeout(BN.checkT); BN.checkT = setTimeout(() => benchCheck(false), 900);
}
function benchSaveSoon(ms){
  clearTimeout(BN.saveT);
  BN.saveT = setTimeout(() => post('/api/bench/save', {name: 'bench', style: BN.style, pieces: BN.pieces}).catch(() => {}), ms == null ? 600 : ms);
}

// ----- the check, as it grows: its lines, and the spots marked on the bench
async function benchCheck(asked){
  const box = $('#bn-checkbox'); if (!box) return;
  for (const m of BN.marks) BN.scene.remove(m); BN.marks = [];
  if (!BN.pieces.length){ box.style.display = 'none'; return; }
  let r;
  try { r = await post('/api/bench/check', {pieces: BN.pieces}); }
  catch (e){ if (asked) toast(e.message, true); box.style.display = 'none'; return; }
  const T = THREE;
  box.innerHTML = `<b>🔍 The check</b> <span class="msg">${r.style ? esc(r.style) + ', ' : ''}by the game's own buildings</span>
    ${r.lines.map((l, n) => `<div class="sev-${l.sev}" style="margin:3px 0">${l.sev === 'ok' ? '✓' : l.sev === 'warning' ? '⚠' : '✗'} ${esc(l.text)}${l.at ? ` <button class="btn sm" data-at="${n}" title="Look at it">⌖</button>` : ''}</div>`).join('')}`;
  box.style.display = 'block';
  box.querySelectorAll('[data-at]').forEach(b => b.onclick = () => { const a = r.lines[+b.dataset.at].at[0]; BN.target.set(a[0], a[1], a[2]); BN.dist = Math.min(BN.dist, 1400); });
  for (const l of r.lines){
    if (!l.at || l.sev === 'ok') continue;
    for (const a of l.at){
      const m = new T.Mesh(new T.SphereGeometry(18, 12, 8), new T.MeshBasicMaterial({color: l.sev === 'error' ? 0xe25a4a : 0xe8b85a, depthTest: false, transparent: true, opacity: 0.85}));
      m.position.set(a[0], a[1], a[2]); m.renderOrder = 20; BN.scene.add(m); BN.marks.push(m);
    }
  }
}

// ----- filling the openings
async function benchFill(){
  if (!BN.pieces.length) return toast('Put some pieces on the bench first.');
  let r;
  try { r = await post('/api/bench/fill', {pieces: BN.pieces}); } catch (e){ return toast(e.message, true); }
  if (!r.add.length) return toast('Every doorway and window the game fills in these pieces is filled already.');
  benchPush();
  for (const a of r.add) BN.pieces.push({k: String(BN.next++), id: a.id, type: a.type, s: a.s || 1, p: a.p});
  await benchSync(); benchChanged();
  const doors = r.add.filter(a => a.type === 'DOOR').length;
  toast(`Filled ${r.add.length} opening${r.add.length === 1 ? '' : 's'}: ${doors} door${doors === 1 ? '' : 's'}, ${r.add.length - doors} window${r.add.length - doors === 1 ? '' : 's'}, as the game fills them (↶ takes them out).`);
}

// ----- starting from one of the game's buildings
async function benchStartMenu(){
  const view = $('#bn-view'); let pop = $('#bn-pop');
  if (pop){ pop.remove(); return; }
  pop = document.createElement('div'); pop.className = 'bnpop'; pop.id = 'bn-pop';
  pop.innerHTML = '<div class="msg">Reading the game\'s buildings…</div>';
  view.appendChild(pop);
  let list;
  try { list = await api('/api/bench/buildings?style=' + encodeURIComponent(BN.style)); } catch (e){ pop.innerHTML = `<div class="msg">${esc(e.message)}</div>`; return; }
  const draw = q => {
    const ls = list.filter(b => !q || b.key.toLowerCase().includes(q) || b.name.toLowerCase().includes(q));
    pop.querySelector('.bnrows').innerHTML = ls.slice(0, 120).map((b, n) => `<button class="btn sm row" data-k="${esc(b.key)}">${esc(b.name)} <span class="msg">· ${b.pieces} pieces · ${b.uses}× in the game${b.home ? '' : ' · not a home'}</span></button>`).join('') || '<div class="msg">None by that name.</div>';
    pop.querySelectorAll('[data-k]').forEach(btn => btn.onclick = () => benchStartFrom(btn.dataset.k));
  };
  pop.innerHTML = `<div style="display:flex;gap:6px;align-items:center;margin-bottom:6px"><b>Start from a game building</b><span style="flex:1"></span><button class="btn sm" id="bn-popx">✕</button></div>
    <div class="msg">The game's ${esc(BN.style)} buildings, the most built first. One is put on the bench to change as you like${BN.pieces.length ? ', beside what is there' : ''}.</div>
    <input id="bn-popq" placeholder="Find…" style="width:100%;margin:6px 0"><div class="bnrows"></div>`;
  pop.querySelector('#bn-popx').onclick = () => pop.remove();
  pop.querySelector('#bn-popq').oninput = e => draw(e.target.value.trim().toLowerCase());
  draw('');
}
async function benchStartFrom(key){
  let r;
  try { r = await api('/api/bench/building?key=' + encodeURIComponent(key)); } catch (e){ return toast(e.message, true); }
  const pop = $('#bn-pop'); if (pop) pop.remove();
  benchPush();
  // (beside what is on the bench already, not in it)
  let ox = 0;
  if (BN.pieces.length){ const b = new THREE.Box3(); for (const o of BN.objs.values()) b.expandByObject(o.g); ox = b.max.x + 600 - Math.min(...r.pieces.map(p => p.p[0])); }
  for (const p of r.pieces) BN.pieces.push({k: String(BN.next++), id: p.id, type: p.type, s: p.s, p: [p.p[0] + ox, p.p[1], p.p[2], p.p[3], p.p[4], p.p[5]]});
  BN.framed = false; await benchSync(); benchChanged();
  toast(`${r.name} is on the bench: change it as you like.`);
}

// ----- out of the bench: as a prefab, or into the world
// (the pieces as a group: offsets from the middle and from the lowest point, as groups.place and the ghost take them)
// (foot: the piece stands on the bench's floor; footUp: how far that floor is over the group's lowest point. On the
// land the ground under the foot pieces sets the height: by the lowest pieces, steps going down a slope set it, and
// a house stood 378 over the ground, 2026-10-27)
function benchItems(){
  const b = new THREE.Box3(); for (const o of BN.objs.values()) b.expandByObject(o.g);
  const cx = BN.pieces.reduce((a, p) => a + p.p[0], 0) / BN.pieces.length, cy = BN.pieces.reduce((a, p) => a + p.p[1], 0) / BN.pieces.length;
  const minZ = b.isEmpty() ? 0 : b.min.z;
  return BN.pieces.map(p => {
    const o = BN.objs.get(p.k), ob = o ? new THREE.Box3().setFromObject(o.g) : null;
    return {id: p.id, type: p.type, dx: +(p.p[0] - cx).toFixed(2), dy: +(p.p[1] - cy).toFixed(2), dz: +(p.p[2] - minZ).toFixed(2),
            rx: p.p[3] || 0, ry: p.p[4] || 0, rz: p.p[5] || 0, s: p.s || 1,
            foot: !!(ob && !ob.isEmpty() && ob.min.z <= 40 && ob.max.z > 0), footUp: +(-minZ).toFixed(2)};
  });
}
async function benchSavePrefab(){
  if (!BN.pieces.length) return toast('Put some pieces on the bench first.');
  const name = prompt('Save the bench as a prefab, in the Library. Its name:', ''); if (!name || !name.trim()) return;
  try { await post('/api/prefabs/save', {name: name.trim(), items: benchItems(), source: 'the prefab workbench'}); W.prefabs = null; toast('Saved as the prefab "' + name.trim() + '" (Library > Prefabs).'); }
  catch (e){ toast(e.message, true); }
}
async function benchPlace(){
  if (!BN.pieces.length) return toast('Put some pieces on the bench first.');
  if (!W.key || !W.ext) return toast('Open an outdoor place on the World map first (Go to a place…), then Place in the world.', true);
  const items = benchItems();
  benchClose();
  if (!V3.on && typeof v3Enable === 'function') await v3Enable(true);
  startGroupPlace(items, 'the bench\'s building (' + items.length + ' pieces)');
  W.groupPlace.bench = true;
  toast('It follows the mouse, set on the land under it; the wheel turns it, a click puts it down. Esc: not now. The bench keeps its copy.');
}
// (world3d.js: the click in the view while the bench's building is being placed; the ghost stands where
// v3GhostMove set it, on the lowest ground under its ground floor)
async function benchPlaceClick(){
  const G = V3.ghost, P = W.groupPlace; if (!G || !G.hit || !P) return toast('Point at the ground first.', true);
  if (!await needProject()) return;
  const [x, y, z] = G.hit;
  const r = await groupAction('/api/group/place', {cell: cellKeyAt(x, y), items: P.items, x, y, z, yaw: G.yaw, label: P.label}, `Placed ${P.label}`);
  if (!r) return;
  setMode(null);
  W.multi.clear(); r.placed.forEach(p => W.multi.set(mkey(p.cell, p.ref), {cell: p.cell, k: p.ref}));
  if (r.placed.length){ const l = r.placed[r.placed.length - 1]; W.sel = {cell: l.cell, k: l.ref}; }
  renderWside(); drawMap(); if (V3.on) v3Refresh();
}
