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
const BN_RSNAP = [0, 1, 5, 15, 90];   // the turn ring's steps, in degrees (0: it turns freely), as the 3D view's Snap ▾
try { BN.rsnap = +(localStorage.getItem('ws-bench-rsnap') || 0); } catch (e) { BN.rsnap = 0; }
if (!BN_RSNAP.includes(BN.rsnap)) BN.rsnap = 0;

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
  #bench .bnpc{position:relative} #bench .bneye{position:absolute;right:2px;top:2px;padding:0 3px;font-size:11px;line-height:16px;border:1px solid var(--line);
    border-radius:4px;background:var(--panel);color:var(--text);cursor:pointer;display:none} #bench .bnpc:hover .bneye{display:block}
  #bench .bnex{position:absolute;left:50%;top:44px;transform:translateX(-50%);display:flex;gap:6px;align-items:center;background:var(--panel);
    border:1px solid var(--gold);border-radius:8px;padding:4px 8px;z-index:3;font-size:12.5px;max-width:calc(100% - 20px);white-space:nowrap}
  #bench .bnex .nm{overflow:hidden;text-overflow:ellipsis;max-width:260px}
  #bench .bnview{position:relative;min-width:0;min-height:0;overflow:hidden}
  #bench .bnview canvas{display:block;outline:none}
  #bench .bntools{position:absolute;left:8px;right:8px;top:8px;display:flex;gap:5px;flex-wrap:wrap;align-items:center;z-index:2}
  #bench .bnnote{position:absolute;left:50%;bottom:12px;transform:translateX(-50%);background:var(--panel);color:var(--text);border:1px solid var(--line0);
    padding:4px 10px;border-radius:6px;font-size:12px;pointer-events:none;display:none;z-index:2}
  #bench .bncheck{position:absolute;right:8px;bottom:8px;width:330px;max-height:45%;overflow:auto;background:var(--panel);border:1px solid var(--line);
    border-radius:8px;padding:8px 10px;font-size:12px;z-index:2}
  #bench #bn-array{right:auto;left:8px;bottom:auto;top:84px;width:auto;display:flex;flex-wrap:wrap;gap:8px;align-items:center;max-width:560px}
  #bench .bncheck .sev-error{color:var(--red)} #bench .bncheck .sev-warning{color:var(--amber)} #bench .bncheck .sev-ok{color:var(--green)}
  #bench .bnpop{position:absolute;left:8px;top:48px;width:380px;max-height:70%;overflow:auto;background:var(--panel);border:1px solid var(--line);
    border-radius:8px;padding:8px;z-index:3;box-shadow:0 6px 20px #0006}
  #bench .bnpop button.row{display:block;width:100%;text-align:left;margin:2px 0}
  #bench .bntools .btn.on{border-color:var(--gold);color:var(--gold)}
  #bench .bnbox{position:absolute;border:1px dashed var(--gold);background:#f0cd8722;pointer-events:none;z-index:2;display:none}
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
    // (data-ownkeys: the world's shortcuts (comfort.js) leave the bench's keys alone; Delete there deleted the
    // world's selection)
    box = document.createElement('div'); box.id = 'bench'; box.dataset.ownkeys = '1';
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
        <button class="btn sm" id="bn-start" title="Begin from one of the game's buildings of this style, then change it">🏠 Start from…</button>
        <button class="btn sm" id="bn-fill" title="Put the style's own doors in doorways and windows in window holes, where the game puts them">🚪 Fill openings</button>
        <button class="btn sm" id="bn-check" title="Gaps in the walls, an open roof, pieces touching nothing">🔍 Check</button>
        <button class="btn sm" id="bn-move" title="Move handles (T)">✥ Move</button><button class="btn sm" id="bn-turn" title="Turn handles (R): drag the ring">⟳ Turn</button><button class="btn sm" id="bn-tilt" title="Tilt handles: the red and green rings tip it, the blue one turns it">⤡ Tilt</button><button class="btn sm" id="bn-scale" title="Size handles: drag any handle (the game sizes evenly, ×0.5 to ×2)">⤢ Size</button><button class="btn sm" id="bn-space" title="Handles on the world's axes or on the piece's own, as it is turned">${benchSpace() === 'local' ? '⟀ Own axes' : '✛ World axes'}</button>
        <select id="bn-msnap" title="Moving a piece: to where the game joins it, else flush against the piece beside it; to the game's joins only; or free (Alt while dragging: free for that drag). Arrows nudge 1 (Shift 16), Page Up / Down raise and lower" style="width:auto">${[['all', 'Joins & flush'], ['joins', 'Joins only'], ['free', 'Free']].map(([v, t]) => `<option value="${v}" ${v === benchMoveSnap() ? 'selected' : ''}>${t}</option>`).join('')}</select>
        <select id="bn-rsnap" title="Steps for the turn ring" style="width:auto">${BN_RSNAP.map(d => `<option value="${d}" ${d === BN.rsnap ? 'selected' : ''}>${d ? 'Turn ' + d + '°' : 'Turn free'}</option>`).join('')}</select>
        <select id="bn-grid" title="Moving a piece that joins nothing: to a grid of this step (a join the game makes still wins)" style="width:auto">${[0, 16, 64, 128, 256].map(d => `<option value="${d}" ${d === benchGrid() ? 'selected' : ''}>${d ? 'Grid ' + d : 'Grid off'}</option>`).join('')}</select>
        <select id="bn-pivot" title="What several pieces turn about with [ ], the Turn box and the menu's turns" style="width:auto"><option value="piece" ${benchPivot() === 'piece' ? 'selected' : ''}>About the piece</option><option value="middle" ${benchPivot() === 'middle' ? 'selected' : ''}>About the middle</option></select>
        <label id="bn-turnbox" title="The selected piece's turn, in degrees ([ ] 15°, Shift+[ ] 1°)" style="display:none;font-size:12px">° <input id="bn-deg" type="number" step="1" style="width:58px">
          <span title="The selected pieces' size (×0.5 to ×2)">× <input id="bn-size" type="number" step="0.05" min="0.5" max="2" style="width:58px"></span>
          <span title="Where the selected piece stands: type to move it (the others selected come too)">X <input id="bn-px" type="number" step="1" style="width:68px"> Y <input id="bn-py" type="number" step="1" style="width:68px"> Z <input id="bn-pz" type="number" step="1" style="width:58px"></span>
          <span id="bn-dims" class="msg" title="How big the selection is: across, deep and high, in the game's units (a cell is 8192, a floor tile mostly 256 or 512)"></span></label>
        <button class="btn sm" id="bn-undo" title="Undo on the bench (Ctrl+Z)">↶</button><button class="btn sm" id="bn-redo" title="Redo (Ctrl+Y)">↷</button>
        <button class="btn sm" id="bn-clear" title="Take everything off the bench">Clear</button>
        <button class="btn sm" id="bn-save" title="Keep it in the Library's prefabs too">💾 Save…</button>
        <button class="btn primary sm" id="bn-place" title="Set the whole structure down in the world: it follows the mouse on the land, the wheel turns it, a click puts it down (one Undo)">⤓ Place</button>
        <span style="flex:1"></span>
        <button class="btn sm" id="bn-close" title="Back to the World map (the bench is kept)">✕ Close</button>
      </div>
      <div class="bnnote" id="bn-note"></div><div class="bnex" id="bn-ex" style="display:none"></div><div class="bnbox" id="bn-boxsel"></div>
      <div class="bncheck" id="bn-checkbox" style="display:none"></div>
      <div class="bnhelp" id="bn-help" title="Drag a piece in from the shelf, or click one. Click a piece to move it: it snaps where the game joins it, or flush. Drag on the bench to box-select (Shift adds), Shift+click to add or take one. Right-drag to look round, middle-drag to pan, wheel to zoom. W A S D fly, Q / E down and up, Shift faster. [ ] turn 15° (Shift 1°), R turn handles, T move handles, Del remove. Ctrl+C copy, Ctrl+V paste (click where it goes; the wheel turns it). Ctrl+D a copy beside it along its own red axis (Shift: the other way). Ctrl+M a mirrored copy across X (Shift: across Y).">
        <b>Drag</b> select · <b>Right-drag</b> look · <b>Middle</b> pan · <b>WASD</b> fly · <b>[ ]</b> turn · <b>Ctrl+D</b> copy beside · <b>Ctrl+M</b> mirror</div>
    </div>`;
  $('#bn-close').onclick = benchClose;
  $('#bn-start').onclick = benchStartMenu;
  $('#bn-fill').onclick = benchFill;
  $('#bn-check').onclick = () => benchCheck(true);
  $('#bn-move').onclick = () => { BN.mode = 'translate'; benchSync(); };
  $('#bn-turn').onclick = () => { BN.mode = 'rotate'; benchSync(); };
  $('#bn-scale').onclick = () => { BN.mode = 'scale'; benchSync(); };
  $('#bn-space').onclick = () => {
    BN.space = benchSpace() === 'local' ? 'world' : 'local';
    try { localStorage.setItem('ws-bench-space', BN.space); } catch (e){}
    $('#bn-space').textContent = BN.space === 'local' ? '⟀ Own axes' : '✛ World axes'; benchSync();
  };
  $('#bn-tilt').onclick = () => { BN.mode = 'tilt'; benchSync(); };
  $('#bn-size').onchange = e => { const s = parseFloat(e.target.value); if (isFinite(s)) benchSizeAll(s); else benchTurnBox(); };
  $('#bn-size').onkeydown = e => { e.stopPropagation(); if (e.key === 'Enter') e.target.blur(); };
  $('#bn-rsnap').onchange = e => { BN.rsnap = +e.target.value; try { localStorage.setItem('ws-bench-rsnap', BN.rsnap); } catch (er) {} benchSync(); };
  $('#bn-msnap').onchange = e => { BN.msnap = e.target.value; try { localStorage.setItem('ws-bench-msnap', BN.msnap); } catch (er) {} };
  ['x', 'y', 'z'].forEach((a, i) => {
    const inp = $('#bn-p' + a);
    inp.onchange = () => {
      const p = BN.sel && BN.pieces.find(q => q.k === BN.sel), v = parseFloat(inp.value);
      if (!p || !isFinite(v)) return benchTurnBox();
      const d = [0, 0, 0]; d[i] = v - p.p[i]; benchNudge(d);
    };
    inp.onkeydown = e => { e.stopPropagation(); if (e.key === 'Enter') inp.blur(); };
  });
  $('#bn-grid').onchange = e => { BN.grid = +e.target.value; try { localStorage.setItem('ws-bench-grid', BN.grid); } catch (er) {} };
  $('#bn-pivot').onchange = e => { BN.pivot = e.target.value; try { localStorage.setItem('ws-bench-pivot', BN.pivot); } catch (er) {} };
  $('#bn-deg').onchange = e => {
    const p = BN.sel && BN.pieces.find(q => q.k === BN.sel), d = parseFloat(e.target.value);
    if (!p || !isFinite(d)) return benchTurnBox();
    benchTurnAll(d * Math.PI / 180 - (p.p[5] || 0));     // (the others selected turn with it)
  };
  $('#bn-deg').onkeydown = e => { e.stopPropagation(); if (e.key === 'Enter') e.target.blur(); };
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
  BN.open = false; BN.keys = {}; benchPasteEnd(true); benchExampleEnd();
  const box = $('#bench'); if (box) box.style.display = 'none';
  benchSaveSoon(0);
}

// ----- the styles and the shelf
async function benchStyles(){
  const sel = $('#bn-style'); if (!sel) return;
  let st;
  try { st = (await api('/api/build/modules')).styles || {}; }
  catch (e){
    $('#bn-list').innerHTML = `<div class="msg">${/still learning/i.test(e.message) ? 'Learning the game\'s buildings (a few minutes, once)…' : esc(e.message)}</div>
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
  const tile = (p, tip) => `<div class="bnpc" draggable="true" data-id="${esc(p.id)}" data-type="${p.tag}" title="${esc(tip)}">
        <button class="bneye" title="See it in use">👁</button><img data-tid="${esc(p.id)}" data-ts="64" data-tt="${p.tag}" alt=""><span>${esc(p.id)}</span></div>`;
  const onShelf = new Set();
  const html = BN.shelf.kinds.map(k => {
    const ps = k.pieces.filter(p => !q || p.id.toLowerCase().includes(q));
    ps.forEach(p => onShelf.add(p.id.toLowerCase()));
    if (!ps.length) return '';
    return `<details data-kind="${k.kind}" ${q || BN.openKinds.has(k.kind) ? 'open' : ''}><summary>${esc(k.label)} <span class="msg">${ps.length}</span></summary>
      <div class="bngrid">${ps.map(p => tile(p, `${p.id}: the game uses it ${p.n}×. Drag it onto the bench, or click it. 👁 or right-click: see it in the game's buildings.`)).join('')}</div></details>`;
  }).join('');
  // (a search also looks through every piece in the load order, any style: a piece no building of a style uses, or
  // whose name names no style, was on no shelf; PIN2's ex_drystonewall_s_01, found in Browse but not here)
  const other = q.length >= 3 && BN.other && BN.other.q === q ? BN.other.rows.filter(r => !onShelf.has(r.id.toLowerCase())) : [];
  list.innerHTML = html + (other.length ? `<details data-kind="other" open><summary>Other pieces (any style) <span class="msg">${other.length}</span></summary>
      <div class="bngrid">${other.map(r => tile({id: r.id, tag: r.type}, `${r.id}: not on this style's shelf. Drag it onto the bench, or click it.`)).join('')}</div></details>` : '')
    || (q.length >= 3 && !(BN.other && BN.other.q === q) ? '<div class="msg">Looking through every piece…</div>' : '<div class="msg">No piece by that name.</div>');
  if (q.length >= 3 && !(BN.other && BN.other.q === q) && BN.otherAsk !== q){
    BN.otherAsk = q;
    api('/api/search?' + new URLSearchParams({q, types: 'STAT,DOOR,ACTI', limit: 60, sort: 'uses'})).then(r => {
      BN.other = {q, rows: (r.rows || []).filter(x => ['STAT', 'DOOR', 'ACTI'].includes(x.type))};
      if (BN.q.trim().toLowerCase() === q) benchShelfRender();
    }).catch(() => { BN.other = {q, rows: []}; });
  }
  list.querySelectorAll('details').forEach(d => d.ontoggle = () => { if (d.open){ BN.openKinds.add(d.dataset.kind); v3ThumbScan(d); } else BN.openKinds.delete(d.dataset.kind); });
  list.querySelectorAll('details[open]').forEach(d => v3ThumbScan(d));
  list.querySelectorAll('.bnpc').forEach(el => {
    el.ondragstart = e => { e.dataTransfer.setData('text/x-bench', el.dataset.id); e.dataTransfer.effectAllowed = 'copy'; BN.dragIn = {id: el.dataset.id, type: el.dataset.type}; };
    el.ondragend = () => { BN.dragIn = null; };
    el.onclick = e => { if (e.target.closest('.bneye')) return; benchAddAt(el.dataset.id, el.dataset.type, null); };
    el.querySelector('.bneye').onclick = e => { e.stopPropagation(); benchExample(el.dataset.id); };
    el.oncontextmenu = e => {
      e.preventDefault();
      pnlMenu({x: e.clientX, y: e.clientY}, [{label: el.dataset.id, disabled: true},
        {label: '👁 See it in use', act: () => benchExample(el.dataset.id)},
        {label: '＋ Put it on the bench', act: () => benchAddAt(el.dataset.id, el.dataset.type, null)}]);
    };
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
    // (see-through by default: the game sinks a building's foot into the land, a Hlaalu house a third of its height,
    // Telvanni roots and platforms almost whole, and those parts are kept as the game has them)
    BN.floor = new T.Mesh(new T.PlaneGeometry(BN_GRID * 200, BN_GRID * 200), new T.MeshLambertMaterial({color: 0x3a352d, transparent: true}));
    BN.scene.add(BN.floor);
    benchFloorLook();
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
// the floor: 'see' (see-through, what is under it shows), 'solid', or 'off' (not drawn; still there to point at)
function benchFloorLook(v){
  if (v){ BN.floorLook = v; try { localStorage.setItem('ws-bench-floor', v); } catch (e) {} }
  if (!BN.floorLook){ try { BN.floorLook = localStorage.getItem('ws-bench-floor') || 'see'; } catch (e) { BN.floorLook = 'see'; } }
  const m = BN.floor && BN.floor.material; if (!m) return;
  m.opacity = BN.floorLook === 'solid' ? 1 : 0.55; m.depthWrite = BN.floorLook === 'solid';
  m.visible = BN.floorLook !== 'off'; m.needsUpdate = true;
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
  let last = performance.now();
  const tick = () => {
    if (!BN.open){ BN.looping = false; return; }
    const c = BN.camera, t = BN.target, now = performance.now(), dt = Math.min(0.1, (now - last) / 1000);
    last = now;
    benchFly(dt);
    c.position.set(t.x + BN.dist * Math.cos(BN.pitch) * Math.sin(BN.yaw), t.y - BN.dist * Math.cos(BN.pitch) * Math.cos(BN.yaw), t.z - BN.dist * Math.sin(BN.pitch));
    c.lookAt(t);
    if (BN.sel){ BN.selBox.update(); if (BN.tcBusy) benchOwnAxes(BN.objs.get(BN.sel)); }
    for (const b of BN.mBoxes || []) b.update();
    BN.renderer.render(BN.scene, c);
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

// flying with the keys, as in the 3D view: W/S ahead and back, A/D aside, Q/E down and up, Shift faster; the
// point looked at moves, so the camera keeps its turn and distance (faster the further it stands off)
function benchFly(dt){
  const K = BN.keys; if (!K) return;
  const f = (K.w ? 1 : 0) - (K.s ? 1 : 0), r = (K.d ? 1 : 0) - (K.a ? 1 : 0), u = (K.e ? 1 : 0) - (K.q ? 1 : 0);
  if (!f && !r && !u) return;
  const v = Math.max(500, BN.dist * 0.9) * (K.shift ? 3 : 1) * dt, c = Math.cos(BN.yaw), s = Math.sin(BN.yaw);
  BN.target.x += (-s * f + c * r) * v; BN.target.y += (c * f + s * r) * v; BN.target.z += u * v;
}

// the bench's pieces drawn: one object a piece, from the 3D view's models
// (the handles on the world's axes or on the piece's own, as the 3D view's ✛/⟀; PIN2: "the local axis doesn't
// exist in the prefab tool")
// (a grid step for moving a piece that joins nothing, and what several pieces turn about: kept as the handles' space is)
function benchMoveSnap(){
  if (!BN.msnap){ try { BN.msnap = localStorage.getItem('ws-bench-msnap') || 'all'; } catch (e){ BN.msnap = 'all'; } }
  return BN.msnap;
}
// the selection moved by d [dx, dy, dz] exactly: no joins, no flush (the arrows, Page Up / Down and the X Y Z boxes)
function benchNudge(d){
  const ps = benchSelected(); if (!ps.length) return;
  benchPush();
  for (const q of ps){ q.p = q.p.slice(); for (let i = 0; i < 3; i++) q.p[i] = +((q.p[i] || 0) + d[i]).toFixed(2); }
  benchSync(); benchChanged(); benchTurnBox();
}
function benchGrid(){
  if (BN.grid == null){ try { BN.grid = +localStorage.getItem('ws-bench-grid') || 0; } catch (e){ BN.grid = 0; } }
  return BN.grid;
}
function benchPivot(){
  if (!BN.pivot){ try { BN.pivot = localStorage.getItem('ws-bench-pivot') || 'piece'; } catch (e){ BN.pivot = 'piece'; } }
  return BN.pivot;
}
function benchSpace(){
  if (!BN.space){ try { BN.space = localStorage.getItem('ws-bench-space') || 'world'; } catch (e){ BN.space = 'world'; } }
  return BN.space;
}
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
    o.g.visible = !(BN.hidden && BN.hidden.has(p.k));
  }
  if (BN.hidden) for (const k of [...BN.hidden]) if (!BN.objs.has(k)) BN.hidden.delete(k);
  // (the selection: BN.sel the piece the handles sit on, BN.multi every piece selected with it, BN.sel among them)
  BN.multi = new Set([...(BN.multi || [])].filter(k => BN.objs.has(k)));
  if (BN.sel && !BN.objs.has(BN.sel)) BN.sel = null;
  if (!BN.sel && BN.multi.size) BN.sel = [...BN.multi][0];
  if (BN.sel) BN.multi.add(BN.sel); else BN.multi.clear();
  for (const b of BN.mBoxes || []) BN.scene.remove(b);
  BN.mBoxes = [...BN.multi].filter(k => k !== BN.sel).map(k => { const b = new THREE.BoxHelper(BN.objs.get(k).g, 0xd8b060); BN.scene.add(b); return b; });
  const so = BN.sel && BN.objs.get(BN.sel);
  // (Turn shows the one ring that turns it on the ground; Tilt all three)
  if (so){ if (BN.tc.object !== so.g) BN.tc.attach(so.g); BN.tc.setMode(BN.mode === 'tilt' ? 'rotate' : BN.mode); BN.tc.setSpace(benchSpace()); BN.tc.showX = BN.tc.showY = BN.mode !== 'rotate'; BN.selBox.setFromObject(so.g); BN.selBox.visible = true; }
  else { BN.tc.detach(); BN.selBox.visible = false; }
  // (the selected piece's own axes, always drawn on it, red its length: which way it faces whatever the handles show,
  // and the way Ctrl+D carries a row on. PIN2: the axes should answer to the piece, "a biggy in the long run")
  if (!BN.ownAxes){ BN.ownAxes = new THREE.AxesHelper(1); BN.ownAxes.material.depthTest = false; BN.ownAxes.renderOrder = 999; BN.scene.add(BN.ownAxes); }
  BN.ownAxes.visible = !!so;
  if (so) benchOwnAxes(so);
  BN.tc.setRotationSnap(BN.rsnap ? BN.rsnap * Math.PI / 180 : null);
  for (const [id, m] of [['#bn-move', 'translate'], ['#bn-turn', 'rotate'], ['#bn-tilt', 'tilt'], ['#bn-scale', 'scale']]){ const b = $(id); if (b) b.classList.toggle('on', BN.mode === m); }
  benchTurnBox();
  if (!BN.framed && BN.pieces.length){ BN.framed = true; benchFrame(); }
}
function benchOwnAxes(so){
  const A = BN.ownAxes; if (!A || !so) return;
  so.g.updateMatrixWorld(true);
  const b = new THREE.Box3().setFromObject(so.g), len = Math.max(64, b.getSize(new THREE.Vector3()).length() * 0.45);
  A.position.copy(b.getCenter(new THREE.Vector3())); A.quaternion.copy(so.g.getWorldQuaternion(new THREE.Quaternion()));
  A.scale.setScalar(len); A.updateMatrixWorld(true);
}
// the Turn (°) box: the selected piece's turn, or hidden with nothing selected (pose: a pose being dragged)
function benchTurnBox(pose){
  const box = $('#bn-turnbox'), inp = $('#bn-deg'); if (!box || !inp) return;
  const p = BN.sel && BN.pieces.find(q => q.k === BN.sel);
  box.style.display = p ? '' : 'none';
  if (p && document.activeElement !== inp) inp.value = +(((pose || p.p)[5] || 0) * 180 / Math.PI).toFixed(1);
  ['x', 'y', 'z'].forEach((a, i) => { const pi = $('#bn-p' + a); if (p && pi && document.activeElement !== pi) pi.value = Math.round((pose || p.p)[i] || 0); });
  const si = $('#bn-size'), so = p && BN.objs.get(p.k);
  if (p && si && document.activeElement !== si) si.value = +(BN.drag && so && BN.drag.o === so ? so.g.scale.x : (p.s || 1)).toFixed(2);
  // (the selection's size: its world box, across × deep × high)
  const dm = $('#bn-dims');
  if (dm && p){
    const b = new THREE.Box3();
    for (const q of benchSelected()){ const o = BN.objs.get(q.k); if (o) b.expandByObject(o.g); }
    const s = b.isEmpty() ? null : b.getSize(new THREE.Vector3());
    dm.textContent = s ? `${Math.round(s.x)} × ${Math.round(s.y)} × ${Math.round(s.z)}` : '';
  }
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
// (pick: choosing a piece, so one seen through a see-through floor counts; a drop lands on the floor)
function benchHit(e, skip, pick){
  BN.ray.setFromCamera(benchMouse(e), BN.camera);
  const hits = BN.ray.intersectObjects([BN.root, BN.floor], true);
  let floor = null;
  for (const h of hits){
    let o = h.object; while (o && o.userData.bench == null && o !== BN.floor) o = o.parent;
    if (!o || !o.visible) continue;                // (a hidden piece is out of the way: clicks go through it)
    if (o === BN.floor){ if (pick && BN.floorLook !== 'solid'){ floor = floor || h; continue; } return {key: null, point: h.point}; }
    if (o.userData.bench === skip) continue;
    return {key: o.userData.bench, point: h.point};
  }
  return floor ? {key: null, point: floor.point} : null;
}
function benchBind(el){
  let drag = null;
  el.addEventListener('contextmenu', e => e.preventDefault());
  el.addEventListener('mousedown', e => {
    el.focus();
    if (e.button === 0 && (BN.tc.dragging || BN.tc.axis)) return;
    if (e.button === 1) e.preventDefault();      // (no autoscroll on the middle button)
    drag = {b: e.button, x: e.clientX, y: e.clientY, yaw: BN.yaw, pitch: BN.pitch, t: BN.target.clone(), moved: false, alt: e.altKey, shift: e.shiftKey};
  });
  window.addEventListener('mousemove', e => {
    if (e.target === el){ BN.lastMouse = {clientX: e.clientX, clientY: e.clientY}; if (BN.paste && BN.open) benchPasteMove(e); }
    if (!drag || !BN.open) return;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
    if (!drag.moved) return;
    // (as the 3D view: a left-drag draws a box to select, the right button looks round, the middle one slides;
    // Alt+left looks round too)
    if (drag.b === 0 && !drag.alt){
      const r = el.getBoundingClientRect(), bx = $('#bn-boxsel');
      Object.assign(bx.style, {display: 'block', left: Math.min(drag.x, e.clientX) - r.left + 'px', top: Math.min(drag.y, e.clientY) - r.top + 'px',
                               width: Math.abs(dx) + 'px', height: Math.abs(dy) + 'px'});
    }
    else if (drag.b === 2 || drag.alt){ BN.yaw = drag.yaw - dx * 0.006; BN.pitch = Math.max(-1.5, Math.min(-0.05, drag.pitch - dy * 0.005)); }
    else {
      // (pan along the floor, the floor following the mouse: right is (cos, sin) of the camera's turn, ahead is
      // (-sin, cos); faster the further the camera stands off)
      const k = BN.dist / 900, c = Math.cos(BN.yaw), s = Math.sin(BN.yaw);
      BN.target.set(drag.t.x - (c * dx + s * dy) * k, drag.t.y - (s * dx - c * dy) * k, drag.t.z);
    }
  });
  window.addEventListener('mouseup', e => {
    const d = drag; drag = null;
    if (!d || !BN.open) return;
    // (pasting: a click puts the copy down where it shows, a right-click lets it go; dragging still looks round)
    if (BN.paste && !d.moved && e.target === el){ if (d.b === 0) benchPasteDrop(e); else if (d.b === 2) benchPasteEnd(); return; }
    if (d.b === 0 && !d.alt && d.moved){ $('#bn-boxsel').style.display = 'none'; benchBoxSelect(d, e); return; }
    if (d.b === 2 && !d.moved && e.target === el){ benchMenu(e); return; }   // (a right-click without dragging: the menu)
    if (d.moved || e.target !== el || d.b !== 0) return;
    // (a click selects what is under it; Shift+click adds it or takes it out)
    const h = benchHit(e, null, true), k = h && h.key;
    if (e.shiftKey){
      if (!k) return;
      if (BN.multi.has(k)){ BN.multi.delete(k); if (BN.sel === k) BN.sel = [...BN.multi][0] || null; }
      else { BN.multi.add(k); BN.sel = k; }
    } else { BN.multi = new Set(); BN.sel = k || null; }
    benchSync();
  });
  el.addEventListener('wheel', e => {
    e.preventDefault();
    // (pasting: the wheel turns the copy, 15° a notch, Shift 1°)
    if (BN.paste){ BN.paste.yaw += (e.deltaY < 0 ? 1 : -1) * (e.shiftKey ? 1 : 15) * Math.PI / 180; benchPasteMove(e); return; }
    BN.dist = Math.max(200, Math.min(30000, BN.dist * (e.deltaY > 0 ? 1.12 : 0.89))); }, {passive: false});
  el.addEventListener('dragover', e => { if (BN.dragIn){ e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; } });
  el.addEventListener('drop', e => {
    const id = e.dataTransfer.getData('text/x-bench'); if (!id) return;
    e.preventDefault();
    const h = benchHit(e);
    benchAddAt(id, (BN.dragIn && BN.dragIn.type) || 'STAT', h ? h.point : null);
  });
  // (the keys are the canvas's own: heard only while the bench's view has the focus, never while typing in the
  // shelf's search or a menu)
  BN.keys = {};
  el.addEventListener('keydown', e => {
    if (!BN.open) return;
    const k = (e.key || '').toLowerCase(), ctrl = e.ctrlKey || e.metaKey, mv = v3MoveKey(e);
    if (mv && !ctrl && !e.altKey){ BN.keys[mv] = true; e.preventDefault(); return; }
    if (e.key === 'Shift'){ BN.keys.shift = true; return; }
    if (e.key === 'Alt'){ BN.keys.alt = true; e.preventDefault(); return; }
    if (ctrl && k === 'z'){ e.preventDefault(); benchUndo(); return; }
    if (ctrl && k === 'y'){ e.preventDefault(); benchRedo(); return; }
    if (k === 'escape'){ BN.keys = {}; if (BN.paste){ benchPasteEnd(); return; } if (BN.ex){ benchExampleEnd(); return; } BN.sel = null; BN.multi = new Set(); benchSync(); return; }
    if (ctrl && k === 'v'){ e.preventDefault(); benchPasteStart(); return; }
    // (H hides the selection, Shift+H shows it alone, Alt+H everything again: to work inside a building)
    if (k === 'h' && !ctrl){ e.preventDefault(); benchHide(e.altKey ? 'none' : e.shiftKey ? 'others' : 'these'); return; }
    if (k === 'r'){ BN.mode = 'rotate'; benchSync(); return; }
    if (k === 't' || k === 'g'){ BN.mode = 'translate'; benchSync(); return; }
    const ps = benchSelected();
    if (!ps.length) return;
    // (fine moves: the arrows along the world's X and Y, by 1, Shift 16; Page Up / Down up and down)
    const step = e.shiftKey ? 16 : 1, nudge = {arrowleft: [-step, 0, 0], arrowright: [step, 0, 0], arrowup: [0, step, 0], arrowdown: [0, -step, 0],
                                                pageup: [0, 0, step], pagedown: [0, 0, -step]}[k];
    if (nudge && !ctrl){ e.preventDefault(); benchNudge(nudge); return; }
    if (k === 'delete' || k === 'backspace'){ e.preventDefault(); benchPush(); BN.pieces = BN.pieces.filter(q => !ps.includes(q)); BN.sel = null; BN.multi = new Set(); benchSync(); benchChanged(); }
    // (turning and copying keep off the flying keys: a held D copied the piece over and over, 2.5.2)
    // ([ ] 15°, Shift 1°: by where the key sits, as Shift turns [ into { on most keyboards)
    else if (e.code === 'BracketLeft' || e.code === 'BracketRight' || '[]{}'.includes(e.key)){
      const sgn = e.code === 'BracketRight' || e.key === ']' || e.key === '}' ? 1 : -1;
      benchTurnAll(sgn * (e.shiftKey ? 1 : 15) * Math.PI / 180);
    }
    // (Ctrl+C keeps a copy, Ctrl+V puts it down where you click; Ctrl+D both at once. Nothing goes in on the key)
    else if (ctrl && k === 'c' && !e.repeat){ e.preventDefault(); benchCopy(); }
    // (Ctrl+D a copy beside it at once, along its own red axis, Shift the other way; Ctrl+M mirrored over X, Shift Y)
    else if (ctrl && k === 'd'){ e.preventDefault(); if (!e.repeat) benchDupBeside(e.shiftKey ? -1 : 1); }
    else if (ctrl && k === 'm' && !e.repeat){ e.preventDefault(); benchMirror(e.shiftKey ? 'y' : 'x'); }
  });
  // (letting go always stops, wherever the focus went; and nothing flies on once the view loses it)
  window.addEventListener('keyup', e => {
    const mv = v3MoveKey(e); if (mv) BN.keys[mv] = false;
    if (e.key === 'Shift') BN.keys.shift = false;
    if (e.key === 'Alt') BN.keys.alt = false;
  }, true);
  // (Alt held while dragging a handle: wherever the focus is, as the drag may have taken it)
  window.addEventListener('keydown', e => { if (e.key === 'Alt' && BN.open) BN.keys.alt = true; }, true);
  el.addEventListener('blur', () => { BN.keys = {}; });
}

// the pieces whose middle falls inside the box dragged on the screen (Shift: added to what is selected)
function benchBoxSelect(d, e){
  const r = BN.renderer.domElement.getBoundingClientRect();
  const x0 = Math.min(d.x, e.clientX), x1 = Math.max(d.x, e.clientX), y0 = Math.min(d.y, e.clientY), y1 = Math.max(d.y, e.clientY);
  const got = [];
  for (const [k, o] of BN.objs){
    if (!o.g.visible) continue;
    const b = new THREE.Box3().setFromObject(o.g); if (b.isEmpty()) continue;
    const c = b.getCenter(new THREE.Vector3()).project(BN.camera);
    if (c.z > 1) continue;
    const sx = r.left + (c.x + 1) / 2 * r.width, sy = r.top + (1 - c.y) / 2 * r.height;
    if (sx >= x0 && sx <= x1 && sy >= y0 && sy <= y1) got.push(k);
  }
  if (!d.shift) BN.multi = new Set();
  for (const k of got) BN.multi.add(k);
  if (!BN.multi.has(BN.sel)) BN.sel = got[0] || [...BN.multi][0] || null;
  benchSync();
  benchNote(BN.multi.size > 1 ? BN.multi.size + ' pieces selected' : '');
  clearTimeout(BN.noteT); BN.noteT = setTimeout(() => benchNote(''), 1400);
}
// the selected pieces (the handles' piece first)
function benchSelected(){ return BN.pieces.filter(q => q.k === BN.sel).concat(BN.pieces.filter(q => q.k !== BN.sel && BN.multi && BN.multi.has(q.k))); }
// the selected pieces turned together by a, round the handles' piece
function benchTurnAll(a){
  const ps = benchSelected(); if (!ps.length) return;
  let [cx, cy] = ps[0].p;
  if (ps.length > 1 && benchPivot() === 'middle'){
    // (about the middle of the selection's box, not the handles' piece: a row turns where it stands)
    const b = new THREE.Box3(); for (const q of ps){ const o = BN.objs.get(q.k); if (o) b.expandByObject(o.g); }
    if (!b.isEmpty()){ const m = b.getCenter(new THREE.Vector3()); cx = m.x; cy = m.y; }
  }
  const c = Math.cos(-a), s = Math.sin(-a), tw = 2 * Math.PI;
  benchPush();
  for (const p of ps){
    const dx = p.p[0] - cx, dy = p.p[1] - cy;
    p.p[0] = +(cx + c * dx - s * dy).toFixed(2); p.p[1] = +(cy + s * dx + c * dy).toFixed(2);
    p.p[5] = +((((p.p[5] || 0) + a) % tw + tw) % tw).toFixed(5);
  }
  benchSync(); benchChanged();
}

// ----- a piece in use: the game's buildings that use it, one at a time beside the bench's work, that piece outlined
// and the rest of the building faint; looked at, not edited (the user, 2026-10-28: "hard to get a sense of the use of
// all the pieces in game without seeing them in use first"). Take it onto the bench puts that building there.
async function benchExample(id){
  let r;
  try { r = await api('/api/bench/uses?id=' + encodeURIComponent(id) + '&style=' + encodeURIComponent(BN.style || '')); }
  catch (e){ return toast(e.message, true); }
  if (!r.buildings.length) return toast(`No building of the game's that the Workshop knows uses ${id}.`);
  BN.ex = {id, list: r.buildings, more: r.more, i: 0, g: null};
  await benchExampleShow();
}
async function benchExampleShow(){
  const X = BN.ex; if (!X) return;
  if (X.g){ BN.scene.remove(X.g); X.g = null; }
  const b = X.list[X.i];
  await v3EnsureModels([...new Set(b.pieces.map(p => p.id))]);
  if (BN.ex !== X) return;
  // (beside the bench's work, to its right, as Start from puts a building)
  let ox = 0;
  if (BN.objs.size){ const w = new THREE.Box3(); for (const o of BN.objs.values()) w.expandByObject(o.g); ox = w.max.x + 900 - Math.min(...b.pieces.map(p => p.p[0])); }
  const g = new THREE.Group(), hits = new Set(b.hit), box = new THREE.Box3();
  b.pieces.forEach((p, n) => {
    const o = v3Build({id: p.id, type: p.type || 'STAT', b: null});
    benchPose(o, {p: [p.p[0] + ox, p.p[1], p.p[2], p.p[3], p.p[4], p.p[5]], s: p.s});
    if (!hits.has(n)) o.traverse(ch => { if (ch.isMesh) ch.material = [].concat(ch.material).map(m => { const c = m.clone(); c.transparent = true; c.opacity = 0.35; c.depthWrite = false; return c; }); });
    g.add(o);
    if (hits.has(n)){ const h = new THREE.BoxHelper(o, 0xf0cd87); g.add(h); box.expandByObject(o); }
  });
  BN.scene.add(g); X.g = g;
  // (looked at from where the piece shows, the whole building in view)
  const all = new THREE.Box3().setFromObject(g);
  BN.target.copy((box.isEmpty() ? all : box).getCenter(new THREE.Vector3()));
  BN.dist = Math.max(900, all.getSize(new THREE.Vector3()).length() * 1.1);
  const bar = $('#bn-ex'), n = X.list.length;
  bar.innerHTML = `<span>👁</span><span class="nm" title="${esc(X.id)} in ${esc(b.name)}, a ${esc(b.style || '')} building the game puts up ${b.uses}×${X.more ? `; ${X.more} more use it` : ''}"><b>${esc(X.id)}</b> in ${esc(b.name)}</span>
    <span class="msg">${X.i + 1}/${n}${X.more ? '+' : ''}</span>
    <button class="btn sm" id="bn-exprev" ${n < 2 ? 'disabled' : ''} title="The one before">◀</button><button class="btn sm" id="bn-exnext" ${n < 2 ? 'disabled' : ''} title="The next one">▶</button>
    <button class="btn sm" id="bn-extake" title="Put this building on the bench to change">Take it</button><button class="btn sm" id="bn-exx" title="Close (Esc)">✕</button>`;
  bar.style.display = 'flex';
  bar.querySelector('#bn-exprev').onclick = () => { X.i = (X.i + n - 1) % n; benchExampleShow(); };
  bar.querySelector('#bn-exnext').onclick = () => { X.i = (X.i + 1) % n; benchExampleShow(); };
  bar.querySelector('#bn-extake').onclick = () => { benchExampleEnd(); benchStartFrom(b.key, {name: b.name, pieces: b.pieces}); };
  bar.querySelector('#bn-exx').onclick = benchExampleEnd;
}
function benchExampleEnd(){
  const X = BN.ex; if (!X) return;
  if (X.g) BN.scene.remove(X.g);
  BN.ex = null;
  const bar = $('#bn-ex'); if (bar) bar.style.display = 'none';
}

// ----- copy and paste: the copy is kept, and goes in only where you click
// (BN.clip: the pieces as offsets from the middle of their foot, so the copy stands on what is under the mouse)
function benchCopy(){
  const ps = benchSelected(); if (!ps.length) return;
  const box = new THREE.Box3();
  for (const p of ps){ const o = BN.objs.get(p.k); if (o) box.expandByObject(o.g); }
  // (a copy of something sunk into the floor, as the game sinks a building's foot, keeps that much sunk: its height
  // is taken from the floor, not from its own bottom)
  const c = box.isEmpty() ? new THREE.Vector3(ps[0].p[0], ps[0].p[1], ps[0].p[2]) : box.getCenter(new THREE.Vector3()), z0 = box.isEmpty() ? ps[0].p[2] : Math.max(0, box.min.z);
  BN.clip = ps.map(p => ({id: p.id, type: p.type, s: p.s || 1, p: [p.p[0] - c.x, p.p[1] - c.y, p.p[2] - z0, p.p[3] || 0, p.p[4] || 0, p.p[5] || 0]}));
  benchNote(`Copied ${ps.length === 1 ? ps[0].id : ps.length + ' pieces'} · Ctrl+V, then click`);
  clearTimeout(BN.noteT); BN.noteT = setTimeout(() => { if (!BN.paste) benchNote(''); }, 1800);
}
// the copy's pieces where it would go: at `at` (the point under the mouse), turned by yaw
function benchPastePieces(at, yaw){
  const c = Math.cos(-yaw), s = Math.sin(-yaw), tw = 2 * Math.PI;
  return BN.clip.map(q => ({id: q.id, type: q.type, s: q.s,
    p: [+(at.x + c * q.p[0] - s * q.p[1]).toFixed(2), +(at.y + s * q.p[0] + c * q.p[1]).toFixed(2), +(at.z + q.p[2]).toFixed(2),
        q.p[3], q.p[4], +((((q.p[5] + yaw) % tw) + tw) % tw).toFixed(5)]}));
}
async function benchPasteStart(){
  if (!BN.clip || !BN.clip.length) return toast('Copy something first (Ctrl+C).');
  benchPasteEnd(true);
  await v3EnsureModels([...new Set(BN.clip.map(q => q.id))]);
  const g = new THREE.Group();
  for (const q of BN.clip){
    const o = v3Build({id: q.id, type: q.type || 'STAT', b: null});
    // (a see-through copy: its own materials, so the pieces on the bench stay as they are)
    o.traverse(ch => { if (ch.isMesh) ch.material = [].concat(ch.material).map(m => { const n = m.clone(); n.transparent = true; n.opacity = 0.55; n.depthWrite = false; return n; }); });
    g.add(o);
  }
  BN.paste = {g, yaw: 0, at: null};
  BN.scene.add(g); g.visible = false;
  BN.mode = 'translate'; BN.tc.detach();
  benchNote('Click to put it down · wheel turns · Esc or right-click: not now');
  if (BN.lastMouse) benchPasteMove(BN.lastMouse);
}
function benchPasteMove(e){
  const P = BN.paste; if (!P) return;
  BN.lastMouse = {clientX: e.clientX, clientY: e.clientY};
  const h = benchHit(e); if (!h){ P.g.visible = false; P.at = null; return; }
  P.at = h.point.clone();
  const ps = benchPastePieces(P.at, P.yaw);
  P.g.children.forEach((o, i) => benchPose(o, ps[i]));
  P.g.visible = true;
}
function benchPasteDrop(e){
  const P = BN.paste; if (!P) return;
  benchPasteMove(e);
  if (!P.at) return toast('Point at the floor or a piece.', true);
  benchPush();
  const cs = benchPastePieces(P.at, P.yaw).map(q => Object.assign({k: String(BN.next++)}, q));
  BN.pieces.push(...cs); BN.sel = cs[0].k; BN.multi = new Set(cs.map(c => c.k));
  benchPasteEnd(); benchSync(); benchChanged();
}
function benchPasteEnd(quiet){
  const P = BN.paste; if (!P) return;
  BN.scene.remove(P.g); BN.paste = null;
  if (!quiet) benchNote('');
}

// ----- copies put down at once (PIN2): beside the selection along the handles' piece's own red axis, end to end, the
// copy selected so the key again carries on the row; or mirrored over the selection's far side, for a building's
// other half
function benchCorners(o, frame){
  // (the selection's pieces' mesh corners in a frame: [world point → frame point]; their true extent, not the
  // world box round a turned piece)
  const out = [], inv = frame ? frame.clone().invert() : null;
  o.g.updateMatrixWorld(true);
  o.g.traverse(ch => {
    if (!ch.isMesh || !ch.geometry) return;
    if (!ch.geometry.boundingBox) ch.geometry.computeBoundingBox();
    const b = ch.geometry.boundingBox;
    for (const x of [b.min.x, b.max.x]) for (const y of [b.min.y, b.max.y]) for (const z of [b.min.z, b.max.z]){
      const v = new THREE.Vector3(x, y, z).applyMatrix4(ch.matrixWorld); out.push(inv ? v.applyMatrix4(inv) : v);
    }
  });
  return out;
}
function benchDupBeside(sign){
  const ps = benchSelected(), so = BN.sel && BN.objs.get(BN.sel); if (!ps.length || !so) return;
  const q = so.g.getWorldQuaternion(new THREE.Quaternion()), frame = new THREE.Matrix4().compose(so.g.getWorldPosition(new THREE.Vector3()), q, new THREE.Vector3(1, 1, 1));
  let lo = Infinity, hi = -Infinity;
  for (const p of ps){ const o = BN.objs.get(p.k); if (o) for (const v of benchCorners(o, frame)){ lo = Math.min(lo, v.x); hi = Math.max(hi, v.x); } }
  if (!isFinite(lo)) return;
  const d = new THREE.Vector3(1, 0, 0).applyQuaternion(q).multiplyScalar(sign * (hi - lo));
  benchPush();
  const cs = ps.map(p => ({k: String(BN.next++), id: p.id, type: p.type, s: p.s || 1,
    p: [+(p.p[0] + d.x).toFixed(2), +(p.p[1] + d.y).toFixed(2), +(p.p[2] + d.z).toFixed(2), p.p[3] || 0, p.p[4] || 0, p.p[5] || 0]}));
  BN.pieces.push(...cs);
  const at = ps.findIndex(p => p.k === BN.sel);
  BN.sel = cs[Math.max(0, at)].k; BN.multi = new Set(cs.map(c => c.k));
  benchSync(); benchChanged();
}
async function benchMirror(axis){
  const ps = benchSelected(); if (!ps.length) return;
  // (over the selection's far side on the world's X or Y: the copy meets it there. The game can't flip a piece's shape:
  // a piece with a mirror-image twin in the load order (a left-hand corner's right-hand one, bench.twins) is swapped for
  // it; one without is turned to match, right for the many pieces alike at both ends)
  const box = new THREE.Box3();
  for (const p of ps){ const o = BN.objs.get(p.k); if (o) for (const v of benchCorners(o)) box.expandByPoint(v); }
  if (box.isEmpty()) return;
  let tw_ = {};
  try { tw_ = await post('/api/bench/twins', {ids: [...new Set(ps.map(p => p.id))]}); } catch (e){}
  const edge = axis === 'x' ? box.max.x : box.max.y, tw = 2 * Math.PI, w = a => +((((a % tw) + tw) % tw).toFixed(5));
  // (the mirrored shape: across world X a piece mirrored across its own X is turned by -rz, one mirrored across its own Y
  // by 180° more; across world Y the other way round)
  benchPush();
  let swapped = 0;
  const cs = ps.map(p => {
    const [x, y, z, rx, ry, rz] = [p.p[0], p.p[1], p.p[2], p.p[3] || 0, p.p[4] || 0, p.p[5] || 0];
    const t = tw_[p.id.toLowerCase()];
    const own = t ? t.axis : 'x';
    if (t) swapped++;
    const yaw = (axis === 'x') === (own === 'x') ? -rz : Math.PI - rz;
    const pose = axis === 'x' ? [+(2 * edge - x).toFixed(2), y, z, rx, w(-ry), w(yaw)] : [x, +(2 * edge - y).toFixed(2), z, w(-rx), ry, w(yaw)];
    return {k: String(BN.next++), id: t ? t.twin : p.id, type: p.type, s: p.s || 1, p: pose};
  });
  BN.pieces.push(...cs);
  BN.sel = cs[0].k; BN.multi = new Set(cs.map(c => c.k));
  await benchSync(); benchChanged();
  benchNote(`Mirrored ${cs.length === 1 ? cs[0].id : cs.length + ' pieces'} across ${axis.toUpperCase()}${swapped ? `, ${swapped} swapped for ${swapped === 1 ? 'its' : 'their'} other hand` : ''}`);
  clearTimeout(BN.noteT); BN.noteT = setTimeout(() => benchNote(''), 2200);
}

// ----- many copies at once (Array…): in a row along the handles' piece's red or green axis or up, end to end with a gap,
// or round a ring whose middle stands a radius in from the piece on its green side (a round hall, a tower's wall)
function benchArrayOpen(){
  if (!benchSelected().length) return toast('Select what to copy first.');
  let box = $('#bn-array');
  if (!box){ box = document.createElement('div'); box.id = 'bn-array'; box.className = 'bncheck'; $('#bn-view').appendChild(box); }
  const A = BN.arr = BN.arr || {n: 3, way: 'red', gap: 0, r: 512, deg: 360};
  box.style.display = 'block';
  box.innerHTML = `<b>Array</b>
    <label>Copies <input id="ba-n" type="number" min="1" max="60" value="${A.n}" style="width:54px"></label>
    <label>Way <select id="ba-way">${[['red', 'In a row along its red axis'], ['green', 'In a row along its green axis'], ['up', 'Upwards'], ['ring', 'Round a ring']].map(([v, l]) => `<option value="${v}" ${A.way === v ? 'selected' : ''}>${l}</option>`).join('')}</select></label>
    <label class="ba-row">Gap <input id="ba-gap" type="number" step="8" value="${A.gap}" style="width:64px"></label>
    <label class="ba-ring">Radius <input id="ba-r" type="number" step="16" min="16" value="${A.r}" style="width:64px"></label>
    <label class="ba-ring">All round <input id="ba-deg" type="number" step="15" min="15" max="360" value="${A.deg}" style="width:54px">°</label>
    <span><button class="btn sm primary" id="ba-go">Make them</button> <button class="btn sm" id="ba-x">Close</button></span>`;
  const show = () => { const ring = $('#ba-way').value === 'ring'; box.querySelectorAll('.ba-ring').forEach(e => e.style.display = ring ? '' : 'none'); box.querySelectorAll('.ba-row').forEach(e => e.style.display = ring ? 'none' : ''); };
  box.querySelectorAll('input').forEach(i => i.onkeydown = e => { e.stopPropagation(); if (e.key === 'Enter') $('#ba-go').click(); });
  $('#ba-way').onchange = show; show();
  $('#ba-x').onclick = () => { box.style.display = 'none'; };
  $('#ba-go').onclick = () => {
    Object.assign(A, {n: Math.max(1, Math.min(60, +$('#ba-n').value || 1)), way: $('#ba-way').value, gap: +$('#ba-gap').value || 0,
                      r: Math.max(16, +$('#ba-r').value || 512), deg: Math.max(15, Math.min(360, +$('#ba-deg').value || 360))});
    benchArray(A); box.style.display = 'none';
  };
}
function benchArray(A){
  const ps = benchSelected(), so = BN.sel && BN.objs.get(BN.sel); if (!ps.length || !so) return;
  const q = so.g.getWorldQuaternion(new THREE.Quaternion()), at = so.g.getWorldPosition(new THREE.Vector3());
  const frame = new THREE.Matrix4().compose(at, q, new THREE.Vector3(1, 1, 1));
  const ax = {red: 'x', green: 'y', up: 'z'}[A.way] || 'x';
  const tw = 2 * Math.PI, cs = [];
  if (A.way === 'ring'){
    // (the ring's middle a radius in on the piece's green side; the copies turned round it, a full ring sharing it out)
    const g = new THREE.Vector3(0, 1, 0).applyQuaternion(q), cx = at.x + g.x * A.r, cy = at.y + g.y * A.r;
    const step = (A.deg >= 360 ? 2 * Math.PI / (A.n + 1) : A.deg * Math.PI / 180 / A.n);
    for (let i = 1; i <= A.n; i++){
      const a = i * step, c = Math.cos(-a), s = Math.sin(-a);
      for (const p of ps){
        const dx = p.p[0] - cx, dy = p.p[1] - cy;
        cs.push({k: String(BN.next++), id: p.id, type: p.type, s: p.s || 1, p: [+(cx + c * dx - s * dy).toFixed(2), +(cy + s * dx + c * dy).toFixed(2), p.p[2],
          p.p[3] || 0, p.p[4] || 0, +((((p.p[5] || 0) + a) % tw + tw) % tw).toFixed(5)]});
      }
    }
  } else {
    let lo = Infinity, hi = -Infinity;
    for (const p of ps){ const o = BN.objs.get(p.k); if (o) for (const v of benchCorners(o, ax === 'z' ? null : frame)){ lo = Math.min(lo, v[ax]); hi = Math.max(hi, v[ax]); } }
    if (!isFinite(lo)) return;
    const d = ax === 'z' ? new THREE.Vector3(0, 0, 1) : new THREE.Vector3(ax === 'x' ? 1 : 0, ax === 'y' ? 1 : 0, 0).applyQuaternion(q);
    d.multiplyScalar(hi - lo + A.gap);
    for (let i = 1; i <= A.n; i++){
      for (const p of ps) cs.push({k: String(BN.next++), id: p.id, type: p.type, s: p.s || 1,
        p: [+(p.p[0] + d.x * i).toFixed(2), +(p.p[1] + d.y * i).toFixed(2), +(p.p[2] + d.z * i).toFixed(2), p.p[3] || 0, p.p[4] || 0, p.p[5] || 0]});
    }
  }
  benchPush();
  BN.pieces.push(...cs);
  BN.sel = cs[cs.length - 1].k; BN.multi = new Set(cs.map(c => c.k));
  benchSync(); benchChanged();
  benchNote(`${A.n} cop${A.n === 1 ? 'y' : 'ies'} made (${cs.length} pieces)`);
  clearTimeout(BN.noteT); BN.noteT = setTimeout(() => benchNote(''), 1800);
}

// ----- out of the way: pieces hidden on the bench only (they stay in the building, its check and its placing)
function benchHide(how){
  BN.hidden = BN.hidden || new Set();
  const sel = new Set(benchSelected().map(p => p.k));
  if (how === 'none') BN.hidden.clear();
  else if (how === 'these'){ if (!sel.size) return; for (const k of sel) BN.hidden.add(k); BN.sel = null; BN.multi = new Set(); }
  else { if (!sel.size) return; for (const p of BN.pieces) if (!sel.has(p.k)) BN.hidden.add(p.k); }
  benchSync();
  benchNote(BN.hidden.size ? `${BN.hidden.size} hidden · Alt+H shows them` : '');
  clearTimeout(BN.noteT); BN.noteT = setTimeout(() => benchNote(''), 2500);
}

// the selected pieces sized s each, in place (the game's limits)
function benchSizeAll(s){
  const ps = benchSelected(); if (!ps.length) return;
  s = Math.max(0.5, Math.min(2, +s.toFixed(3)));
  benchPush(); for (const p of ps) p.s = s; benchSync(); benchChanged();
}
// the selected pieces set down together on what is below them (another piece, or the bench's floor)
function benchSetDown(){
  const ps = benchSelected(); if (!ps.length) return;
  const keys = new Set(ps.map(p => p.k)), box = new THREE.Box3();
  for (const p of ps){ const o = BN.objs.get(p.k); if (o) box.expandByObject(o.g); }
  if (box.isEmpty()) return;
  const others = [...BN.objs.values()].filter(o => !keys.has(o.k)).map(o => o.g).concat([BN.floor]);
  let top = -Infinity;
  // (a few rays down from under the selection: its middle and its corners pulled in a little)
  const c = box.getCenter(new THREE.Vector3()), ix = (box.max.x - box.min.x) * 0.35, iy = (box.max.y - box.min.y) * 0.35;
  for (const [dx, dy] of [[0, 0], [-ix, -iy], [ix, -iy], [-ix, iy], [ix, iy]]){
    BN.ray.set(new THREE.Vector3(c.x + dx, c.y + dy, box.min.z + 1), new THREE.Vector3(0, 0, -1));
    const h = BN.ray.intersectObjects(others, true)[0];
    if (h) top = Math.max(top, h.point.z);
  }
  if (!isFinite(top)) top = 0;
  const dz = +(top - box.min.z).toFixed(2);
  if (Math.abs(dz) < 0.5) return benchNote('');
  benchPush(); for (const p of ps) p.p[2] = +(p.p[2] + dz).toFixed(2); benchSync(); benchChanged();
}
// the selected pieces stood upright again (no tilt), keeping their turn
function benchStraighten(){
  const ps = benchSelected().filter(q => q.p[3] || q.p[4]); if (!ps.length) return;
  benchPush(); for (const p of ps){ p.p[3] = 0; p.p[4] = 0; } benchSync(); benchChanged();
}
function benchSelectLike(id){
  BN.multi = new Set(BN.pieces.filter(p => p.id === id).map(p => p.k));
  if (!BN.multi.has(BN.sel)) BN.sel = [...BN.multi][0] || null;
  benchSync();
}
function benchKey(code, key, o){ BN.renderer.domElement.dispatchEvent(new KeyboardEvent('keydown', Object.assign({code, key, bubbles: true, cancelable: true}, o || {}))); }
// the right-click menu: for the piece under the mouse (and the others selected with it), or for the bench
function benchMenu(e){
  const h = benchHit(e, null, true), k = h && h.key, pt = {x: e.clientX, y: e.clientY}, items = [];
  if (k){
    if (!BN.multi.has(k)){ BN.multi = new Set(); BN.sel = k; benchSync(); }
    const ps = benchSelected(), p = ps[0], n = ps.length;
    items.push({label: n > 1 ? n + ' pieces' : p.id, disabled: true},
      {label: '✥ Move', on: BN.mode === 'translate', act: () => { BN.mode = 'translate'; benchSync(); }},
      {label: '⟳ Turn', on: BN.mode === 'rotate', act: () => { BN.mode = 'rotate'; benchSync(); }},
      {label: '⤡ Tilt', on: BN.mode === 'tilt', act: () => { BN.mode = 'tilt'; benchSync(); }},
      {label: '⤢ Size', on: BN.mode === 'scale', act: () => { BN.mode = 'scale'; benchSync(); }}, '-',
      {label: '⟳ Turn 90°', act: () => benchTurnAll(Math.PI / 2)}, {label: '⟲ Turn 90° back', act: () => benchTurnAll(-Math.PI / 2)},
      {label: '⤢ Size…', act: () => { const s = $('#bn-size'); if (s){ s.focus(); s.select(); } }},
      {label: '↺ Size ×1', act: () => benchSizeAll(1)},
      {label: '⊥ Straighten', disabled: !ps.some(q => q.p[3] || q.p[4]), act: benchStraighten},
      {label: '⤓ Set down', act: benchSetDown}, '-',
      {label: '⧉ Copy (Ctrl+C)', act: benchCopy},
      {label: '⧉ Duplicate beside (Ctrl+D)', act: () => benchDupBeside(1)},
      {label: '⧉ Duplicate, then click', act: () => { benchCopy(); benchPasteStart(); }},
      {label: '⇋ Mirror across X (Ctrl+M)', act: () => benchMirror('x')},
      {label: '⇅ Mirror across Y (Ctrl+Shift+M)', act: () => benchMirror('y')},
      {label: '⋯ Array…', act: benchArrayOpen},
      {label: '◌ Hide (H)', act: () => benchHide('these')}, {label: '◎ Show only these (Shift+H)', act: () => benchHide('others')},
      {label: n > 1 ? '💾 Save these ' + n + ' as a prefab…' : '💾 Save it as a prefab…', act: () => benchSavePrefab(true)},
      ...(BN.clip ? [{label: '📋 Paste, then click (Ctrl+V)', act: benchPasteStart}] : []),
      {label: 'Select all like it', act: () => benchSelectLike(p.id)},
      {label: '👁 See it in use', act: () => benchExample(p.id)},
      {label: 'Find on the shelf', act: () => { BN.q = p.id; const q = $('#bn-q'); if (q) q.value = p.id; benchShelfRender(); }},
      {label: '⌖ Look at it', act: () => { const o = BN.objs.get(p.k); if (o){ const b = new THREE.Box3().setFromObject(o.g); BN.target.copy(b.getCenter(new THREE.Vector3())); BN.dist = Math.max(600, b.getSize(new THREE.Vector3()).length() * 1.4); } }}, '-',
      {label: n > 1 ? '✕ Delete all ' + n : '✕ Delete', act: () => benchKey('Delete', 'Delete')});
  } else {
    items.push({label: 'Select all', disabled: !BN.pieces.length, act: () => { BN.multi = new Set(BN.pieces.map(p => p.k)); BN.sel = BN.pieces[0] && BN.pieces[0].k; benchSync(); }},
      {label: '⌖ Show everything', disabled: !BN.pieces.length, act: benchFrame},
      {label: '🚪 Fill openings', disabled: !BN.pieces.length, act: benchFill},
      {label: '🔍 Check', disabled: !BN.pieces.length, act: () => benchCheck(true)});
    if (BN.clip) items.unshift({label: '📋 Paste, then click (Ctrl+V)', act: benchPasteStart});
    items.push('-', ...[['see', 'Floor: see-through'], ['solid', 'Floor: solid'], ['off', 'Floor: hidden']].map(([v, l]) => ({label: l, on: BN.floorLook === v, act: () => benchFloorLook(v)})));
    if (BN.sel) items.push('-', {label: 'Clear the selection', act: () => { BN.sel = null; BN.multi = new Set(); benchSync(); }});
    if (BN.hidden && BN.hidden.size) items.unshift({label: `◉ Show all (${BN.hidden.size} hidden, Alt+H)`, act: () => benchHide('none')});
  }
  pnlMenu(pt, items);
}

// ----- adding a piece: where it was dropped (on the floor or on a piece), else in front of the camera; then snapped
async function benchAddAt(id, type, point){
  benchPush();
  await v3EnsureModels([id]);
  const g = v3Build({id, type, b: null}), box = new THREE.Box3().setFromObject(g);
  const at = point ? point.clone() : BN.target.clone().setZ(0);
  const z = at.z - (box.isEmpty() ? 0 : box.min.z);
  const p = {k: String(BN.next++), id, type, s: 1, p: [Math.round(at.x), Math.round(at.y), Math.round(z), 0, 0, 0]};
  BN.pieces.push(p); BN.sel = p.k; BN.multi = new Set(); BN.mode = 'translate';
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
  // (the others selected ride along: each kept where it stands from the handles' piece; they are never snapped to)
  const others = o.k === BN.sel && BN.multi ? [...BN.multi].filter(k => k !== o.k && BN.objs.has(k)) : [];
  o.g.updateMatrixWorld(true);
  const inv = o.g.matrixWorld.clone().invert();
  const D = {o, startQ: o.g.quaternion.clone(), startS: o.g.scale.x, snaps: [],
             nearObjs: [...BN.objs.values()].filter(x => x !== o && !others.includes(x.k) && x.g.position.distanceTo(o.g.position) < 4000),
             ride: others.map(k => { const g = BN.objs.get(k).g; g.updateMatrixWorld(true); return {k, g, rel: inv.clone().multiply(g.matrixWorld)}; })};
  BN.drag = D;
  D.fetching = benchSnapsFetch(D);
}
async function benchSnapsFetch(D){
  const g = D.o.g, p = BN.pieces.find(q => q.k === D.o.k); if (!p) return;
  D.at = g.position.clone();
  try {
    const ride = new Set((D.ride || []).map(x => x.k));
    const r = await post('/api/bench/snaps', {pieces: BN.pieces.filter(q => q !== p && !ride.has(q.k)), id: p.id, x: g.position.x, y: g.position.y, z: g.position.z});
    if (BN.drag === D) D.snaps = r.snaps || [];
  } catch (e) {}
}
function benchSnap(){
  const D = BN.drag; if (!D) return;
  const g = D.o.g;
  if (BN.mode === 'scale'){
    // (the game sizes a thing evenly, ×0.5 to ×2: whichever handle is dragged sizes all three ways)
    const s0 = D.startS || 1, v = [g.scale.x, g.scale.y, g.scale.z].reduce((a, b) => Math.abs(b - s0) > Math.abs(a - s0) ? b : a, s0);
    g.scale.setScalar(Math.max(0.5, Math.min(2, +v.toFixed(3))));
    g.updateMatrixWorld(true); BN.selBox.setFromObject(g); benchTurnBox(); benchRide(D); return;
  }
  if (BN.mode !== 'translate'){ BN.selBox.setFromObject(g); benchTurnBox(benchPoseOf(g)); benchRide(D); return; }
  if (D.at && g.position.distanceTo(D.at) > 800) D.fetching = benchSnapsFetch(D);
  const ms = BN.keys && BN.keys.alt ? 'free' : benchMoveSnap();
  let best = null;
  for (const s of ms === 'free' ? [] : D.snaps || []){
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
    const st = benchGrid();
    if (st){
      // (on the grid instead of flush with a neighbour: the step chosen, height too)
      g.position.set(Math.round(g.position.x / st) * st, Math.round(g.position.y / st) * st, Math.round(g.position.z / st) * st);
      benchNote(`On the ${st} grid`);
    } else if (ms === 'all'){
      const n = v3SnapFlush(D, g);
      benchNote(n ? `Flush with ${n.r.id}` : '');
    } else benchNote(ms === 'free' ? 'Free' : '');
  }
  g.updateMatrixWorld(true);
  BN.selBox.setFromObject(g);
  benchRide(D);
}
function benchRide(D){
  if (!D.ride || !D.ride.length) return;
  D.o.g.updateMatrixWorld(true);
  const m = new THREE.Matrix4();
  for (const x of D.ride){
    m.multiplyMatrices(D.o.g.matrixWorld, x.rel).decompose(x.g.position, x.g.quaternion, x.g.scale);
    x.g.updateMatrixWorld(true);
  }
}
function benchDragEnd(){
  const D = BN.drag; BN.drag = null;
  benchNote('');
  if (!D) return;
  const p = BN.pieces.find(q => q.k === D.o.k); if (!p) return;
  const np = benchPoseOf(D.o.g), ns = +D.o.g.scale.x.toFixed(3);
  if (np.some((v, i) => Math.abs(v - (p.p[i] || 0)) > 0.01) || Math.abs(ns - (p.s || 1)) > 0.001){
    if (!BN.pushed) benchPush(); p.p = np; p.s = ns;
    for (const x of D.ride || []){ const q = BN.pieces.find(z => z.k === x.k); if (q){ q.p = benchPoseOf(x.g); q.s = Math.max(0.5, Math.min(2, +x.g.scale.x.toFixed(3))); } }
    benchChanged();
  }
  BN.pushed = false;
  benchTurnBox();
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

// a check line's first clause, for the panel (the whole line is its tooltip): up to a '; ', '. ' or ' (', then
// up to a ': ' when what comes before it says enough, at most 56 letters
function benchShort(t){
  let s = String(t || '');
  for (const c of ['; ', '. ', ' (']){ const i = s.indexOf(c); if (i > 0) s = s.slice(0, i); }
  if (s.length > 56){ const i = s.indexOf(': '); if (i >= 14) s = s.slice(0, i); }
  return s.length > 56 ? s.slice(0, 55).replace(/\s+\S*$/, '') + '…' : s;
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
  box.innerHTML = `<b title="Checked by the rules of the game's own ${esc(r.style || '')} buildings">🔍 Check</b> <span class="msg">${r.style ? esc(r.style) : ''}</span>
    ${r.lines.map((l, n) => `<div class="sev-${l.sev}" style="margin:3px 0" title="${esc(l.text)}">${l.sev === 'ok' ? '✓' : l.sev === 'warning' ? '⚠' : '✗'} ${esc(benchShort(l.text))}${l.at ? ` <button class="btn sm" data-at="${n}" title="Look at it">⌖</button>` : ''}</div>`).join('')}`;
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
  if (!r.add.length) return toast('Nothing left to fill.');
  benchPush();
  for (const a of r.add) BN.pieces.push({k: String(BN.next++), id: a.id, type: a.type, s: a.s || 1, p: a.p});
  await benchSync(); benchChanged();
  const doors = r.add.filter(a => a.type === 'DOOR').length;
  toast(`Filled ${doors} door${doors === 1 ? '' : 's'}, ${r.add.length - doors} window${r.add.length - doors === 1 ? '' : 's'} (↶ undoes)`);
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
    pop.querySelector('.bnrows').innerHTML = ls.slice(0, 120).map((b, n) => `<button class="btn sm row" data-k="${esc(b.key)}">${esc(b.name)} <span class="msg">· ${b.pieces} pieces · ${b.uses}×${b.home ? '' : ' · not a home'}</span></button>`).join('') || '<div class="msg">None by that name.</div>';
    pop.querySelectorAll('[data-k]').forEach(btn => btn.onclick = () => benchStartFrom(btn.dataset.k));
  };
  pop.innerHTML = `<div style="display:flex;gap:6px;align-items:center;margin-bottom:6px"><b>Start from a game building</b><span style="flex:1"></span><button class="btn sm" id="bn-popx">✕</button></div>
    <div class="msg">Most built first.</div>
    <input id="bn-popq" placeholder="Find…" style="width:100%;margin:6px 0"><div class="bnrows"></div>`;
  pop.querySelector('#bn-popx').onclick = () => pop.remove();
  pop.querySelector('#bn-popq').oninput = e => draw(e.target.value.trim().toLowerCase());
  draw('');
}
async function benchStartFrom(key, given){
  // (given: the building already in hand, {name, pieces}, as an example of a piece in use shows it)
  let r = given;
  if (!r) try { r = await api('/api/bench/building?key=' + encodeURIComponent(key)); } catch (e){ return toast(e.message, true); }
  const pop = $('#bn-pop'); if (pop) pop.remove();
  benchPush();
  // (beside what is on the bench already, not in it)
  let ox = 0;
  if (BN.pieces.length){ const b = new THREE.Box3(); for (const o of BN.objs.values()) b.expandByObject(o.g); ox = b.max.x + 600 - Math.min(...r.pieces.map(p => p.p[0])); }
  for (const p of r.pieces) BN.pieces.push({k: String(BN.next++), id: p.id, type: p.type, s: p.s, p: [p.p[0] + ox, p.p[1], p.p[2], p.p[3], p.p[4], p.p[5]]});
  BN.framed = false; await benchSync(); benchChanged();
  toast(`${r.name} is on the bench (its foot sunk as in the game)`);
}

// ----- out of the bench: as a prefab, or into the world
// (the pieces as a group: offsets from the middle and from the lowest point, as groups.place and the ghost take them)
// (foot: the piece stands on the bench's floor; footUp: how far that floor is over the group's lowest point. On the
// land the ground under the foot pieces sets the height: by the lowest pieces, steps going down a slope set it, and
// a house stood 378 over the ground, 2026-10-27)
function benchItems(only){
  // (only: some of the pieces, a part saved as a prefab of its own, a porch or a tower's top)
  const pcs = only || BN.pieces;
  const b = new THREE.Box3(); for (const p of pcs){ const o = BN.objs.get(p.k); if (o) b.expandByObject(o.g); }
  const cx = pcs.reduce((a, p) => a + p.p[0], 0) / pcs.length, cy = pcs.reduce((a, p) => a + p.p[1], 0) / pcs.length;
  const minZ = b.isEmpty() ? 0 : b.min.z;
  return pcs.map(p => {
    const o = BN.objs.get(p.k), ob = o ? new THREE.Box3().setFromObject(o.g) : null;
    return {id: p.id, type: p.type, dx: +(p.p[0] - cx).toFixed(2), dy: +(p.p[1] - cy).toFixed(2), dz: +(p.p[2] - minZ).toFixed(2),
            rx: p.p[3] || 0, ry: p.p[4] || 0, rz: p.p[5] || 0, s: p.s || 1,
            foot: !!(ob && !ob.isEmpty() && ob.min.z <= 40 && ob.max.z > 0), footUp: +(-minZ).toFixed(2)};
  });
}
async function benchSavePrefab(selection){
  if (!BN.pieces.length) return toast('Put some pieces on the bench first.');
  const only = selection ? benchSelected() : null;
  if (selection && !only.length) return toast('Select the pieces to save first.');
  const name = prompt(only ? `Save the ${only.length} selected piece${only.length === 1 ? '' : 's'} as a prefab, in the Library. Its name:` : 'Save the bench as a prefab, in the Library. Its name:', '');
  if (!name || !name.trim()) return;
  try { await post('/api/prefabs/save', {name: name.trim(), items: benchItems(only), source: 'the prefab workbench'}); W.prefabs = null; toast('Saved as the prefab "' + name.trim() + '" (Library > Prefabs).'); }
  catch (e){ toast(e.message, true); }
}
async function benchPlace(){
  if (!BN.pieces.length) return toast('Put some pieces on the bench first.');
  if (!W.key || !W.ext) return toast('Open an outdoor place first.', true);
  const items = benchItems();
  benchClose();
  if (!V3.on && typeof v3Enable === 'function') await v3Enable(true);
  startGroupPlace(items, 'the bench\'s building (' + items.length + ' pieces)');
  W.groupPlace.bench = true;
  toast('Click to put it down · wheel turns · Esc cancels');
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

// the Ctrl+K command list and a shortcut you can change (comfort.js): from any page
if (typeof CF_ACT !== 'undefined') CF_ACT.push({id: 'bench', label: 'Prefab workbench (build from the game\'s pieces)', keys: ['Ctrl+B'], run: () => benchOpen()});
