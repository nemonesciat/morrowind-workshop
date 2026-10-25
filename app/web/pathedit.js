// Editing walking paths (path grids) by hand, on the flat map and in 3D: click to add a point (joined
// to the selected one), drag a point to move it, Shift+click a point to join or unjoin it, Delete to
// take one out. The changes are kept here until you finish, then saved into the mod as one Undo.
let PE = null;      // {cell, pts: [[x, y, z]], edges: [[a, b]], sel, hist, dirty, drag, ver}
const PE_HIT = 9, PE_HIT3 = 13;

function peCanEdit(){ return !!(W.key && W.info && (W.info.interior || W.key.startsWith('#'))); }

async function peStart(){
  if (!peCanEdit()) return toast('Walking paths belong to an interior or an outdoor cell: open one first.', true);
  if (!await needProject()) return;
  const cell = W.key, src = (W.cells[cell] || W.info).paths || {pts: [], edges: []};
  if (W.mode) setMode(null);
  PE = {cell, ext: cell.startsWith('#'), pts: src.pts.map(p => p.slice(0, 3)), edges: src.edges.map(e => e.slice()),
        sel: null, hist: [], dirty: false, drag: null, ver: 1};
  W.showPaths = true;
  setMode('paths');
  PNL.show('world', 'paths');
  renderWside(); drawMap();
}

// leaving the mode (Esc, Done, another tool, another place) keeps what you did; Discard throws it away
function peLeave(){
  const P = PE; if (!P) return;
  PE = null;
  if (P.dirty && !P.discard){
    // shown as you left them straight away, while they're being saved (not the old ones for a moment)
    const now = {pts: P.pts, edges: P.edges}, c = W.cells[P.cell];
    if (c) c.paths = now;
    if (W.info && W.info.key === P.cell) W.info.paths = now;
    peSave(P);
  }
  else if (P.dirty) toast('Left the walking paths as they were.');
  drawMap(); if (typeof renderWside === 'function') setTimeout(renderWside, 0);
}
async function peSave(P){
  try {
    const m = await post('/api/paths/save', {cell: P.cell, pts: P.pts, edges: P.edges});
    W.cells[P.cell] = prepCell(m); if (P.cell === W.key) W.info = m;
    toast(`Saved the walking paths: ${m.saved.points} points, ${m.saved.links} links. Undo takes them back.`);
    drawMap(); renderWside(); afterChange();
  } catch (err){ toast(err.message, true); worldReloadCell(P.cell); }
}

function peCount(){ const n = PE.pts.length, l = PE.edges.length; return `${n} point${n === 1 ? '' : 's'}, ${l} link${l === 1 ? '' : 's'}`; }
function peBanner(){
  if (!PE) return;
  const pc = $('#pe-count'); if (pc) pc.textContent = peCount();
  const n = PE.pts.length, sel = PE.sel != null ? PE.edges.filter(e => e[0] === PE.sel || e[1] === PE.sel).length : 0;
  setBanner(`<span><b>Walking paths</b> · ${n} point${n === 1 ? '' : 's'}${PE.sel != null ? ` · selected one has ${sel} link${sel === 1 ? '' : 's'}` : ''}.
    Click to add a point (joined to the selected one, Ctrl: not joined), drag one to move it, <b>Shift+click</b> a point to join or unjoin it, <b>Delete</b> takes it out, Ctrl+Z undoes.</span>
    <span style="white-space:nowrap;margin-left:8px"><button class="btn sm primary" id="pe-done">✓ Done</button> <button class="btn sm" id="pe-discard">Discard</button></span>`);
  const d = $('#pe-done'); if (d) d.onclick = e => { e.stopPropagation(); setMode(null); };
  const x = $('#pe-discard'); if (x) x.onclick = e => { e.stopPropagation(); if (PE) PE.discard = true; setMode(null); };
}

// ----- changes (each one can be undone while you're here)
function peSnap(){ PE.hist.push(JSON.stringify([PE.pts, PE.edges, PE.sel])); if (PE.hist.length > 200) PE.hist.shift(); PE.dirty = true; }
function peChanged(){ PE.ver++; peBanner(); drawMap(); }
function peUndo(){
  if (!PE.hist.length) return toast('Nothing more to undo here.');
  [PE.pts, PE.edges, PE.sel] = JSON.parse(PE.hist.pop()); PE.dirty = true; peChanged();
}
function peEdge(a, b){ return PE.edges.findIndex(e => (e[0] === a && e[1] === b) || (e[0] === b && e[1] === a)); }
function peLink(a, b){
  if (a === b) return;
  peSnap();
  const i = peEdge(a, b);
  if (i >= 0) PE.edges.splice(i, 1); else PE.edges.push([a, b]);
  PE.sel = b; peChanged();
}
function peAdd(p, join){
  if (PE.ext && cellKeyAt(p[0], p[1]) !== PE.cell) return toast('That is outside this cell: each outdoor cell keeps its own paths. Finish here, then open the next cell.', true);
  peSnap();
  PE.pts.push([Math.round(p[0]), Math.round(p[1]), Math.round(p[2])]);
  const k = PE.pts.length - 1;
  if (join && PE.sel != null) PE.edges.push([PE.sel, k]);
  PE.sel = k; peChanged();
}
function peDelete(i){
  if (i == null) return;
  peSnap();
  PE.pts.splice(i, 1);
  PE.edges = PE.edges.filter(e => e[0] !== i && e[1] !== i).map(e => e.map(v => v > i ? v - 1 : v));
  PE.sel = null; peChanged();
}
function peUnlinkAll(i){ peSnap(); PE.edges = PE.edges.filter(e => e[0] !== i && e[1] !== i); peChanged(); }
// the height for a point put down on the flat map: the selected (or nearest) point's floor indoors, the ground outdoors
function peZ(x, y){
  if (PE.ext){ const t = terrainAt(x, y); if (t != null) return t; }
  if (PE.sel != null) return PE.pts[PE.sel][2];
  let best = null, bd = 1e18;
  for (const p of PE.pts){ const d = (p[0] - x) ** 2 + (p[1] - y) ** 2; if (d < bd){ bd = d; best = p; } }
  return best ? best[2] : groundZ(x, y);
}

// ----- the flat map
function pePoint2D(sx, sy){
  let best = null, bd = PE_HIT;
  PE.pts.forEach((p, i) => { const [x, y] = toScreen(p[0], p[1]), d = Math.hypot(x - sx, y - sy); if (d <= bd){ bd = d; best = i; } });
  return best;
}
function peDraw2D(){
  g.save();
  g.strokeStyle = '#7fd0ffcc'; g.lineWidth = 2;
  for (const [a, b] of PE.edges){
    const A = PE.pts[a], B = PE.pts[b]; if (!A || !B) continue;
    const [x1, y1] = toScreen(A[0], A[1]), [x2, y2] = toScreen(B[0], B[1]);
    g.beginPath(); g.moveTo(x1, y1); g.lineTo(x2, y2); g.stroke();
  }
  // where the next point would join
  if (PE.sel != null && W.mouse && !PE.drag && PE.pts[PE.sel]){
    const [x1, y1] = toScreen(PE.pts[PE.sel][0], PE.pts[PE.sel][1]);
    g.setLineDash([5, 4]); g.strokeStyle = '#7fd0ff77'; g.beginPath(); g.moveTo(x1, y1); g.lineTo(W.mouse[0], W.mouse[1]); g.stroke(); g.setLineDash([]);
  }
  PE.pts.forEach((p, i) => {
    const [x, y] = toScreen(p[0], p[1]);
    g.fillStyle = i === PE.sel ? '#f0cd87' : '#7fd0ff'; g.strokeStyle = '#0b1a24'; g.lineWidth = 1.5;
    g.beginPath(); g.arc(x, y, i === PE.sel ? 6.5 : 5, 0, Math.PI * 2); g.fill(); g.stroke();
  });
  g.restore();
}

let peRaf = 0;
function peRedraw(){ if (!peRaf) peRaf = requestAnimationFrame(() => { peRaf = 0; drawMap(); }); }

// heard before the map's own handlers (capture), so selecting and moving objects stay out of the way
document.addEventListener('mousedown', e => {
  if (!PE || e.button !== 0) return;
  if (e.target === cv){
    e.stopPropagation();
    const i = pePoint2D(e.offsetX, e.offsetY);
    if (i != null){
      if (e.shiftKey && PE.sel != null && PE.sel !== i){ peLink(PE.sel, i); return; }
      PE.sel = i; PE.drag = {kind: 'pt', i, sx: e.offsetX, sy: e.offsetY, moved: false}; peChanged();
    } else PE.drag = {kind: 'pan', sx: e.offsetX, sy: e.offsetY, cx: W.cam.x, cy: W.cam.y, moved: false, ctrl: e.ctrlKey || e.metaKey};
    return;
  }
  if (V3.on && V3.renderer && e.target === V3.renderer.domElement && !e.altKey){
    if (V3.tc && (V3.tc.dragging || V3.tc.axis)) return;
    e.stopPropagation();
    const i = pePoint3D(e);
    if (i != null){
      if (e.shiftKey && PE.sel != null && PE.sel !== i){ peLink(PE.sel, i); return; }
      PE.sel = i; PE.drag = {kind: 'pt3', i, x: e.clientX, y: e.clientY, moved: false}; peChanged();
    } else PE.drag = {kind: 'add3', x: e.clientX, y: e.clientY, moved: false, ctrl: e.ctrlKey || e.metaKey};
  }
}, true);
document.addEventListener('mousemove', e => {
  if (!PE) return;
  const D = PE.drag;
  if (!D){ if (PE.sel != null && e.target === cv) peRedraw(); return; }
  if (!(e.buttons & 1)){ PE.drag = null; return; }       // let go somewhere we couldn't see
  if (D.kind === 'pt' || D.kind === 'pan'){
    const dx = e.offsetX - D.sx, dy = e.offsetY - D.sy;
    if (e.target !== cv) return;
    e.stopPropagation();
    if (!D.moved && Math.hypot(dx, dy) > 4){ D.moved = true; if (D.kind === 'pt') peSnap(); }
    if (!D.moved) return;
    if (D.kind === 'pan'){ cv.classList.add('dragging'); W.cam.x = D.cx - dx / W.cam.z; W.cam.y = D.cy + dy / W.cam.z; drawMap(); return; }
    const [wx, wy] = toWorld(e.offsetX, e.offsetY), p = PE.pts[D.i];
    p[0] = Math.round(wx); p[1] = Math.round(wy);
    if (PE.ext){ const t = terrainAt(wx, wy); if (t != null) p[2] = Math.round(t); }
    PE.ver++; peRedraw();
    return;
  }
  if (Math.hypot(e.clientX - D.x, e.clientY - D.y) > 3 && !D.moved){ D.moved = true; if (D.kind === 'pt3') peSnap(); }
  if (D.kind === 'pt3' && D.moved){
    e.stopPropagation();
    const h = v3Pick(e, true);
    if (h && h.world){ const p = PE.pts[D.i]; p[0] = Math.round(h.world[0]); p[1] = Math.round(h.world[1]); p[2] = Math.round(h.world[2]); PE.ver++; }
  }
}, true);
window.addEventListener('mouseup', e => {
  if (!PE || !PE.drag) return;
  const D = PE.drag; PE.drag = null; cv.classList.remove('dragging');
  if (D.kind === 'pan'){
    if (D.moved){ if (W.ext) recentre(); return; }
    if (e.target !== cv) return;
    const [wx, wy] = toWorld(e.offsetX, e.offsetY);
    if (PE.sel == null && pePoint2D(e.offsetX, e.offsetY) == null && !PE.pts.length) toast('First point down. Click again to add the next one, joined to it.');
    peAdd([wx, wy, peZ(wx, wy)], !D.ctrl);
    return;
  }
  if (D.kind === 'add3' && !D.moved && V3.on && e.target === V3.renderer.domElement){
    const h = v3Pick(e, true);
    if (!h || !h.world) return toast('Click on a floor or the ground.', true);
    peAdd(h.world, !D.ctrl);
    return;
  }
  if ((D.kind === 'pt' || D.kind === 'pt3') && D.moved) peChanged();
}, true);

// ----- 3D: the points as dots, the links as lines, drawn over everything
function pePoint3D(e){
  const b = V3.renderer.domElement.getBoundingClientRect(), o = V3.origin, v = new THREE.Vector3();
  let best = null, bd = PE_HIT3;
  PE.pts.forEach((p, i) => {
    v.set(p[0] - o[0], p[1] - o[1], p[2] - o[2] + 8).project(V3.camera);
    if (v.z > 1 || v.z < -1) return;
    const x = (v.x + 1) / 2 * b.width + b.left, y = (1 - v.y) / 2 * b.height + b.top, d = Math.hypot(x - e.clientX, y - e.clientY);
    if (d <= bd){ bd = d; best = i; }
  });
  return best;
}
function pe3DTick(){
  const sig = PE && V3.on ? PE.cell + '|' + PE.ver + '|' + PE.sel + '|' + V3.origin.join(',') : '';
  if (sig === V3.peSig) return;
  V3.peSig = sig;
  if (V3.peObj){ V3.scene.remove(V3.peObj); V3.peObj.traverse(x => { if (x.geometry) x.geometry.dispose(); if (x.material) x.material.dispose(); }); V3.peObj = null; }
  if (!sig) return;
  const T = THREE, o = V3.origin, grp = new T.Group(), at = p => [p[0] - o[0], p[1] - o[1], p[2] - o[2] + 8];
  const lines = [];
  for (const [a, b] of PE.edges) if (PE.pts[a] && PE.pts[b]) lines.push(...at(PE.pts[a]), ...at(PE.pts[b]));
  const lg = new T.BufferGeometry(); lg.setAttribute('position', new T.Float32BufferAttribute(lines, 3));
  // (links bright where seen, faint behind rock; the points stay grabbable through it)
  const ln = new T.LineSegments(lg, new T.LineBasicMaterial({color: 0x7fd0ff, transparent: true, opacity: 0.95}));
  const lb = new T.LineSegments(lg, new T.LineBasicMaterial({color: 0x7fd0ff, depthTest: false, transparent: true, opacity: 0.18}));
  ln.renderOrder = 11; lb.renderOrder = 10; grp.add(lb, ln);
  const dots = (list, color, size) => {
    const pg = new T.BufferGeometry(); pg.setAttribute('position', new T.Float32BufferAttribute(list, 3));
    const pt = new T.Points(pg, new T.PointsMaterial({color, size, sizeAttenuation: false, depthTest: false, transparent: true}));
    pt.renderOrder = 12; grp.add(pt);
  };
  dots(PE.pts.flatMap((p, i) => i === PE.sel ? [] : at(p)), 0x7fd0ff, 9);
  if (PE.sel != null && PE.pts[PE.sel]) dots(at(PE.pts[PE.sel]), 0xf0cd87, 13);
  V3.peObj = grp; V3.scene.add(grp);
}

// ----- keys (asked first by the shortcut handler in comfort.js) and the right-click menu
function peKey(e){
  if (!PE || cfTyping(e) || document.querySelector('.modal-bg')) return false;
  const ctrl = e.ctrlKey || e.metaKey, k = e.key;
  let done = true;
  if ((k === 'Delete' || k === 'Backspace') && PE.sel != null) peDelete(PE.sel);
  else if (ctrl && !e.shiftKey && (k === 'z' || k === 'Z')) peUndo();
  else if (k === 'Escape'){ if (PE.sel != null){ PE.sel = null; peChanged(); } else setMode(null); }
  else if (k === 'Enter' && !ctrl) setMode(null);
  else done = false;
  if (done){ e.preventDefault(); e.stopPropagation(); }
  return done;
}
function peMenu(e){
  if (!PE) return;
  const i = V3.on ? pePoint3D(e) : pePoint2D(e.offsetX, e.offsetY), items = [];
  if (i != null){
    PE.sel = i; peChanged();
    items.push({label: 'Take this point out', act: () => peDelete(i)});
    items.push({label: 'Unjoin all its links', act: () => peUnlinkAll(i)});
    items.push('-');
  }
  if (PE.hist.length) items.push({label: '↶ Undo', act: peUndo});
  items.push({label: '✓ Done', act: () => setMode(null)});
  items.push({label: 'Discard my path changes', act: () => { PE.discard = true; setMode(null); }});
  pnlMenu({x: e.clientX, y: e.clientY}, items);
}

// opening another place finishes the paths here first
(function(){
  const open = worldOpen;
  worldOpen = function(){ if (PE) setMode(null); return open.apply(this, arguments); };
})();
