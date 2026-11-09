// ---------- The land map on the World map: every outdoor cell by how freely it may be shaped, cells marked for
// shaping, and "Raise the marked cells into land" (landsurvey.py, landrange.py) ----------
const LM = {data: null, show: false, drag: null, loading: null, poll: null, warned: {}, height: 600, coast: 6144, rough: 1, paint: true};
const LM_LEVELS = {
  sea:     {label: 'Sea bed', fill: 'rgba(70,140,220,0.22)', note: 'only the sea bed: free to shape'},
  wild:    {label: 'Wild', fill: 'rgba(90,190,90,0.30)', note: 'nothing built: free to shape, rocks and plants follow the ground'},
  light:   {label: 'Light', fill: 'rgba(230,200,70,0.32)', note: 'a few pieces, a tomb or a cave mouth: shape round them with care'},
  settled: {label: 'Settled', fill: 'rgba(220,80,70,0.38)', note: 'a town: locked (hold Shift to mark it anyway)'},
};

async function lmLoad(force, keepPlan){
  if (LM.data && !force) return LM.data;
  if (!LM.loading) LM.loading = api('/api/landmap').then(d => {
    d.marked = new Set(d.marks); LM.data = d; LM.loading = null;
    if (!LM.plan || (force && !keepPlan)){
      LM.plan = d.plan || {layers: [], rough: 1, fade: 1024, paint: true, seed: 1};
      LM.histCur = JSON.stringify(LM.plan); LM.hist = []; LM.fut = [];     // (a plan read afresh starts its own history)
    }
    if (LM.plan.layers.length && LM.prevOn !== false) lsPreviewSoon();
    // (the land survey still learning: ask again until it's done. The plan here stays: the server's copy can be
    // older than a change not yet saved, and a removed shape came back)
    clearTimeout(LM.poll);
    if (d.learning) LM.poll = setTimeout(async () => { await lmLoad(true, true); drawMap(); if (PNL.isShown('world', 'land')) renderWside(); }, 5000);
    return d;
  }).catch(e => { LM.loading = null; throw e; });
  return LM.loading;
}
function lmCell(k){ return LM.data && LM.data.cells[k]; }
function lmHasLand(k){ return !!(lmCell(k) || (LM.data && LM.data.own[k])); }

// called by drawMap outdoors, after the ground and the regions are drawn
function lmDraw(g){
  if (!LM.show || !LM.data || !W.ext) return;
  const z = W.cam.z, sz = CELL * z, D = LM.data;
  const [wx0, wy1] = toWorld(0, 0), [wx1, wy0] = toWorld(W.w, W.h);
  const gx0 = Math.floor(wx0 / CELL) - 1, gx1 = Math.floor(wx1 / CELL) + 1, gy0 = Math.floor(wy0 / CELL) - 1, gy1 = Math.floor(wy1 / CELL) + 1;
  if ((gx1 - gx0) * (gy1 - gy0) > 60000) return;
  g.save();
  // the plan's land, worked out at every 4th point (landshapes.preview), over the marked cells
  // Only on cells still marked (Clear marks left the old preview painted until the next one came), and dimmed while
  // a newer one is on its way: a removed shape stayed drawn for seconds and looked like the ✕ hadn't worked
  if (LM.prev && LM.prevOn !== false){
    g.imageSmoothingEnabled = true;
    if (LM.prevStale) g.globalAlpha = 0.45;
    for (const [k, img] of Object.entries(LM.prev)){
      if (!D.marked.has(k)) continue;
      const [x, y] = k.split(',').map(Number), [sx, sy] = toScreen(x * CELL, (y + 1) * CELL), size = (CELL + CELL / 16) * z;
      if (sx > W.w || sy > W.h || sx + size < 0 || sy + size < 0) continue;
      g.drawImage(img, sx, sy, size, size);
    }
    g.globalAlpha = 1;
  }
  // (also on the first preview, with nothing drawn yet: a big one takes a minute or two and the map said nothing)
  if (LM.prevStale && LM.prevBusy && LM.prevOn !== false && D.marks.length){
    g.font = '12px sans-serif'; g.textAlign = 'center';
    const sec = LM.prevT ? Math.floor((Date.now() - LM.prevT) / 1000) : 0;
    const t = 'Updating the preview…' + (sec >= 3 ? ` ${sec} s` : ''), w = g.measureText(t).width + 16;
    g.fillStyle = 'rgba(0,0,0,0.6)'; g.fillRect(W.w / 2 - w / 2, 8, w, 22);
    g.fillStyle = '#fff'; g.fillText(t, W.w / 2, 23); g.textAlign = 'start';
  }
  for (let x = gx0; x <= gx1; x++) for (let y = gy0; y <= gy1; y++){
    const k = x + ',' + y, c = D.cells[k], own = D.own[k], [sx, sy] = toScreen(x * CELL, (y + 1) * CELL);
    if (c){
      g.fillStyle = LM_LEVELS[c[0]].fill; g.fillRect(sx, sy, sz + 0.5, sz + 0.5);
      if (c[5] && sz >= 10){
        // another mod's land (Project Tamriel's, say): hatched
        g.save(); g.beginPath(); g.rect(sx, sy, sz, sz); g.clip();
        g.strokeStyle = 'rgba(255,255,255,0.16)'; g.lineWidth = 1;
        for (let t = -sz; t < sz; t += Math.max(6, sz / 6)){ g.beginPath(); g.moveTo(sx + t, sy + sz); g.lineTo(sx + t + sz, sy); g.stroke(); }
        g.restore();
      }
    } else if (!own && sz >= 6){
      // no land at all: the frontier (next to land) outlined, room to grow into
      const nb = [[1, 0], [-1, 0], [0, 1], [0, -1]].some(([dx, dy]) => lmHasLand((x + dx) + ',' + (y + dy)));
      if (nb){ g.setLineDash([3, 3]); g.strokeStyle = 'rgba(140,200,255,0.55)'; g.lineWidth = 1; g.strokeRect(sx + 1.5, sy + 1.5, sz - 3, sz - 3); g.setLineDash([]); }
    }
    // (your own land: thin and dashed, so it doesn't read as a selection, as a solid box did to the user)
    if (own){ g.setLineDash([2, 4]); g.strokeStyle = 'rgba(190,130,255,0.75)'; g.lineWidth = 1; g.strokeRect(sx + 3.5, sy + 3.5, sz - 7, sz - 7); g.setLineDash([]); }
    if (D.marked.has(k)){
      if (!(LM.prev && LM.prevOn !== false && LM.prev[k])){ g.fillStyle = 'rgba(255,255,255,0.28)'; g.fillRect(sx, sy, sz + 0.5, sz + 0.5); }
      g.strokeStyle = '#fff'; g.lineWidth = 2;
      if (!D.marked.has((x + 1) + ',' + y)){ g.beginPath(); g.moveTo(sx + sz, sy); g.lineTo(sx + sz, sy + sz); g.stroke(); }
      if (!D.marked.has((x - 1) + ',' + y)){ g.beginPath(); g.moveTo(sx, sy); g.lineTo(sx, sy + sz); g.stroke(); }
      if (!D.marked.has(x + ',' + (y + 1))){ g.beginPath(); g.moveTo(sx, sy); g.lineTo(sx + sz, sy); g.stroke(); }
      if (!D.marked.has(x + ',' + (y - 1))){ g.beginPath(); g.moveTo(sx, sy + sz); g.lineTo(sx + sz, sy + sz); g.stroke(); }
    }
  }
  lmFlowDraw(g);
  lsDrawShapes(g);
  g.restore();
}

// what a cell is, for the hover card
function lmTip(k){
  const D = LM.data; if (!D) return '';
  const c = D.cells[k], own = D.own[k], [gx, gy] = k.split(',');
  const head = `<b>${c && c[7] ? esc(c[7]) + ' ' : ''}(${gx}, ${gy})</b>`;
  const mark = D.marked.has(k) ? ' · <span style="color:#fff">marked</span>' : '';
  if (!c) return `${head}${mark}<br><span style="color:var(--faint)">${own ? 'Land your mod made (' + own + ')' : 'No land in any plugin: the open sea bed at −2048'}</span>`;
  const L = LM_LEVELS[c[0]];
  return `${head} <span style="color:var(--faint)">${esc(L.label)}</span>${mark}<br>
    ${esc(D.plugins[c[4]])}${c[6] ? ' · ' + esc(c[6].replace(/ region$/, '')) : ''}${own ? ' · changed by your mod' : ''}<br>
    ground ${c[2]} to ${c[3]}${c[1] === 'shore' ? ' (shore)' : c[1] === 'sea' ? ' (under the sea)' : ''}<br>
    ${c[8]} objects · ${c[9]} building pieces · ${c[10]} door${c[10] === 1 ? '' : 's'} inside · ${c[11]} people and creatures`;
}
function lmHover(e){
  const tip = $('#maptip');
  if (!LM.show || !LM.data || !W.ext){ return false; }
  const k = regCellAt(e.offsetX, e.offsetY);
  tip.style.display = 'block'; tip.style.whiteSpace = 'normal'; tip.style.width = '300px'; tip.style.maxWidth = '';
  tip.innerHTML = lmTip(k);
  // (on the side of the mouse with room for it)
  const left = e.offsetX + 14 + 300 > W.w ? e.offsetX - 14 - 300 : e.offsetX + 14;
  const top = e.offsetY + 10 + tip.offsetHeight > W.h ? e.offsetY - 10 - tip.offsetHeight : e.offsetY + 10;
  tip.style.left = Math.max(0, left) + 'px'; tip.style.top = Math.max(0, top) + 'px';
  return true;
}

// ----- marking cells: drag over them (Ctrl: unmark; Shift: settled cells too)
function lmMark(){
  if (V3.on){ toast('The land map is on the flat map: turn off 3D first.', true); return; }
  LM.show = true;
  $('#maptip').style.display = 'none';
  setMode('landmap'); cv.classList.add('place');
  setBanner(`⛰ Marking cells for shaping: drag over cells to mark them. <kbd>Ctrl</kbd> unmarks, <kbd>Shift</kbd> marks settled cells too. <button class="btn sm" id="lm-done">Done</button>`);
  $('#lm-done').onclick = () => { setMode(null); renderWside(); drawMap(); };
  lmLoad().then(drawMap);
}
// (a drag marks the box of cells from where it started to where it is; settled ones only with Shift held)
function lmDown(e){
  if (!LM.data) return;
  LM.drag = {add: !e.ctrlKey, force: e.shiftKey, start: regCellAt(e.offsetX, e.offsetY), before: new Set(LM.data.marked), cells: [], refused: []};
  lmMove(e);
}
function lmMove(e){
  const D = LM.drag; if (!D) return false;
  const [x0, y0] = D.start.split(',').map(Number), [x1, y1] = regCellAt(e.offsetX, e.offsetY).split(',').map(Number);
  const M = LM.data.marked = new Set(D.before);
  D.cells = []; D.refused = [];
  for (let x = Math.min(x0, x1); x <= Math.max(x0, x1); x++) for (let y = Math.min(y0, y1); y <= Math.max(y0, y1); y++){
    const k = x + ',' + y, c = lmCell(k);
    if (D.add && c && c[0] === 'settled' && !D.force && !e.shiftKey){ D.refused.push(k); continue; }
    D.cells.push(k);
    if (D.add) M.add(k); else M.delete(k);
  }
  drawMap();
  return true;
}
async function lmUp(){
  const D = LM.drag; LM.drag = null; if (!D) return;
  if (D.refused.length){
    const c = lmCell(D.refused[0]);
    toast(`${D.refused.length} settled cell${D.refused.length === 1 ? '' : 's'} left unmarked${c ? ` (${c[7] || D.refused[0]}: ${c[10]} doors into interiors, ${c[9]} building pieces)` : ''}. Hold Shift to mark them anyway.`);
  }
  const cells = D.cells.filter(k => D.add !== D.before.has(k));
  if (!cells.length) return;
  if (!await needProject()){ await lmLoad(true); drawMap(); return; }
  // (only the newest answer counts: marked one after another while the Workshop was busy, an older answer came back
  // after a newer click and unmarked its cells until the next one came, "my cell keeps getting deselected" 2026-11-02)
  try { await lmMarksPost(D.add ? {add: cells} : {remove: cells}); }
  catch (err){ toast(err.message, true); await lmLoad(true, true); }
  drawMap(); if (PNL.isShown('world', 'land')) renderWside();
}
// marks sent to the server: only the newest answer counts. Marked one after another while the Workshop was busy,
// an older answer came back after a newer click and unmarked its cells until the next one came, "my cell keeps
// getting deselected" (2026-11-02)
async function lmMarksPost(body){
  const seq = LM.markSeq = (LM.markSeq || 0) + 1;
  const r = await post('/api/land/marks', body);
  if (seq === LM.markSeq) lmMarksAre(r.marks);
  return r;
}
// the marks as the server now has them, and the plan's preview over them asked for again
function lmMarksAre(marks){
  LM.data.marks = marks; LM.data.marked = new Set(marks);
  if (LM.plan && LM.plan.layers.length) lsPreviewSoon();
  lmFlowSoon();
}
// ----- before and after: the map's ground as it was just before Shape them or Texture only, shown while ◐ is held
async function lmKeepBefore(what){
  // (the cells in view loaded first, the open sea among them: kept as they were, so ◐ shows them, not now's land)
  try { await loadAround(Math.floor(W.cam.x / CELL), Math.floor(W.cam.y / CELL)); } catch (e){}
  LM.before = {lands: Object.assign({}, W.lands), what};
}
function lmShowBefore(on){
  const B = LM.before; if (!B) return;
  if (on && !LM.afterLands){
    LM.afterLands = W.lands;
    // (the cells kept from before, the rest as they are now: the map was moved since, say)
    W.lands = Object.assign({}, W.lands, B.lands);
  } else if (!on && LM.afterLands){
    W.lands = Object.assign(LM.afterLands, {});
    LM.afterLands = null;
  }
  const b = $('#lm-before'); if (b) b.classList.toggle('primary', !!on);
  drawMap();
}

// ----- the flow overlay: where the rain runs over the marked cells (landshapes.flow_lines, landwater)
function lmFlowSoon(){
  clearTimeout(LM.flowT);
  if (!LM.flowOn){ LM.flow = null; return; }
  LM.flowT = setTimeout(lmFlowLoad, 400);
}
async function lmFlowLoad(){
  if (!LM.flowOn || !LM.data) return;
  if (!LM.data.marks.length){ LM.flow = null; drawMap(); return; }
  const ask = LM.flowN = (LM.flowN || 0) + 1;
  try {
    const shaped = !!(LM.plan && LM.plan.layers.length && LM.prevOn !== false);
    const r = await post('/api/land/flow', {cells: LM.data.marks, plan: LM.plan, shaped});
    if (ask === LM.flowN){ LM.flow = r; drawMap(); }
  } catch (e){ toast(e.message, true); }
}
function lmFlowDraw(g){
  const F = LM.flow; if (!F || !LM.flowOn || !F.lines.length) return;
  const z = W.cam.z;
  g.save(); g.lineCap = 'round';
  for (const [x0, y0, x1, y1, a] of F.lines){
    const [sx0, sy0] = toScreen(x0, y0), [sx1, sy1] = toScreen(x1, y1);
    if (Math.max(sx0, sx1) < 0 || Math.min(sx0, sx1) > W.w || Math.max(sy0, sy1) < 0 || Math.min(sy0, sy1) > W.h) continue;
    const bed = F.bed != null && a >= F.bed;
    // (thicker the more drains through, in proportion to the zoom but never a hair nor a band)
    g.lineWidth = Math.max(1, Math.min(7, (0.5 + Math.log2(a) * 0.45) * Math.min(1.6, z * 140)));
    g.strokeStyle = bed ? 'rgba(120,205,255,0.95)' : `rgba(70,150,235,${Math.min(0.85, 0.3 + Math.log2(a) * 0.08)})`;
    g.beginPath(); g.moveTo(sx0, sy0); g.lineTo(sx1, sy1); g.stroke();
  }
  g.restore();
}

// ----- the Land panel outdoors: the land map and shaping
function lmViewHtml(i){
  if (!i || i.interior) return '';
  const D = LM.data, n = D ? D.marks.length : 0;
  const counts = {};
  if (D) for (const k of D.marks){ const c = D.cells[k]; const lv = c ? c[0] : D.own[k] ? 'yours' : 'none'; counts[lv] = (counts[lv] || 0) + 1; }
  // (the raise-into-land sliders stand open only when a marked cell has no land or is sea bed; on land they read as
  // the next step before the shapes and folded away, 2026-11-04)
  const bare = Object.keys(counts).some(k => k === 'none' || /sea/i.test(k));
  const what = Object.entries(counts).map(([lv, m]) => `${m} ${lv === 'none' ? 'with no land yet' : lv === 'yours' ? 'of your own land' : LM_LEVELS[lv].label.toLowerCase()}`).join(', ');
  // (one button pinned at the top for everything drawn: the ground shapes into the marked cells, then each town built
  // on it. Shape them shaped only the ground and a town needed its own Make it, found only with the town selected:
  // "why do I HAVE to have town selected ... it's not clear how you get to apply these, if there's an order", 2026-11-01)
  // (castles too: the button said "Build the town" and left the castle drawn beside it unbuilt, its own Make it
  // hidden down the panel, 2026-11-02)
  const pin = lsPinWhat(), towns = pin.towns, castles = pin.castles, ng = pin.ground, built = towns.length + castles.length;
  const tReady = towns.every(L => { const T = (LM.towns || {})[L.id]; return T && T.plan && T.plan.plots.length; });
  const cReady = castles.every(L => { const C = (LM.castles || {})[L.id]; return C && C.plan && !C.busy; });
  const nrd = ((LM.plan && LM.plan.layers) || []).filter(L => L.kind === 'road' && L.on !== false && L.pts && L.pts.length).length;
  const shp = ng - (lsTerrOn() ? 1 : 0) - nrd;
  const pinWhat = [ng ? `⛰ ${[shp ? `${shp} ground shape${shp === 1 ? '' : 's'}` : '', nrd ? `${nrd} road${nrd === 1 ? '' : 's'}` : '', lsTerrOn() ? 'region pass' : ''].filter(Boolean).join(' + ')} · ${n ? `${n} cell${n === 1 ? '' : 's'}` : 'no cells marked'}` : '',
    towns.length ? `🏘 ${towns.length === 1 ? esc(towns[0].p.name || (LM.towns && LM.towns[towns[0].id] && LM.towns[towns[0].id].plan && LM.towns[towns[0].id].plan.name) || 'a town') : towns.length + ' towns'}${tReady ? '' : ' (planning…)'}` : '',
    castles.length ? `🏰 ${castles.length === 1 ? esc(castles[0].p.name || (LM.castles && LM.castles[castles[0].id] && LM.castles[castles[0].id].plan && LM.castles[castles[0].id].plan.name) || 'a castle') : castles.length + ' castles'}${cReady ? '' : ' (planning…)'}` : ''].filter(Boolean).join('<br>');
  // (only those not built yet are counted: the button leaves a built one as it is, lsDoAll)
  const nt = towns.filter(L => !lsKnownBuilt(L)).length, nc = castles.filter(L => !lsKnownBuilt(L)).length, todoB = nt + nc;
  const whatBuilt = !todoB ? '' : todoB > 1 ? `${todoB} ${nt && nc ? 'towns and castles' : nt ? 'towns' : 'castles'}` : nt ? 'the town' : 'the castle';
  // (built once, the button says so and waits: a second press built the town again on top of the first, 2026-11-04)
  const allBuilt = built && !ng && !todoB;
  const label = allBuilt ? '✓ Built' : ng && todoB ? 'Shape, then build' : ng ? 'Shape the ground' : `Build ${whatBuilt}`;
  const can = (!ng || n) && tReady && cReady && !allBuilt;
  const bar = (ng || built) ? `<div class="ls-pin"><span class="msg">${pinWhat}</span>
    <button class="btn sm primary" id="ls-apply-top" ${can ? '' : 'disabled'} title="${allBuilt ? 'Built. Change the outline or a setting to plan it anew; ✕ Remove the town takes it away' : `${ng && built ? 'The ground first, then each town and castle on it' : ng ? 'The ground shapes into the marked cells' : 'Every town and castle drawn, as planned'}; one already built is left as it is. Nothing changes the mod before this. One Undo a step`}">${((LM.plan && LM.plan.layers) || []).some(L => (L.p || {}).proposed) ? '<b class="ls-step">2</b>' : ''}${label}</button></div>` : '';
  return `${bar}<h3>Land shaping${lsGuide('Land shaping: how it works')}</h3>
    <label class="msg" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="lm-show" ${LM.show ? 'checked' : ''}> Show the land map</label>
    <label class="msg" style="display:flex;gap:6px;align-items:center" title="The way the rain runs over the marked cells: thicker where more ground drains through, brighter where Stream beds would texture it. On the plan's preview when there are shapes, else on the land as it is"><input type="checkbox" id="lm-flow" ${LM.flowOn ? 'checked' : ''}> Show where water runs</label>
    ${LM.before ? `<div class="actions"><button class="btn sm" id="lm-before" title="Hold to see the land as it was before the last ${esc(LM.before.what)}; let go for now">◐ Before</button></div>` : ''}
    ${D && D.learning ? '<div class="msg" style="font-size:11.5px">Still learning the game\'s land (about a minute)…</div>' : ''}
    <div class="lm-legend">${Object.entries(LM_LEVELS).map(([k, L]) => `<span title="${esc(L.note)}"><i style="background:${L.fill}"></i>${esc(L.label)}</span>`).join('')}
      <span title="Land from another mod: your mod would override it"><i class="lm-hatch"></i>Another mod's</span>
      <span title="Land your mod made or changed"><i style="border:1px dashed rgba(190,130,255,0.9)"></i>Yours</span>
      <span title="No land in any plugin yet, next to land: room to grow"><i style="border:1px dashed rgba(140,200,255,0.8)"></i>Room to grow</span></div>
    <div class="actions" style="margin-top:6px"><button class="btn sm" id="lm-mark">⛰ Mark cells…</button><button class="btn sm" id="lm-clear" ${n ? '' : 'disabled'}>Clear marks</button><button class="btn sm" id="lm-revert" ${n ? '' : 'disabled'} title="Put the land in the marked cells back as it was before your mod: heights, ground textures and grass. Your objects stay. Undo brings it back">↶ Undo my land</button><button class="btn sm" id="lm-dress" ${n || lmDressRings().length ? '' : 'disabled'} title="The marked cells' land (or a ▢ Dress area's) dressed as the game dresses its region: rocks and cliffs turned to their slopes, trees, plants and logs laid as the region's own land has them. One Undo">🪨 Dress…</button></div>
    <div class="msg" style="font-size:11.5px">${n ? `${n} cell${n === 1 ? '' : 's'} marked${what ? ': ' + esc(what) : ''}.` : 'Mark the cells to shape on the map.'}</div>
    ${n && !bare ? '<details class="lm-raise-fold"><summary class="msg" style="cursor:pointer;font-size:11.5px" title="Plain rolling land at one height in the marked cells, with no shapes drawn">Plain land instead of shapes</summary>' : ''}${n ? `<div class="lm-raise">
      <label>Height <input type="range" id="lm-h" min="0" max="6000" step="50" value="${LM.height}"><span>${LM.height}</span></label>
      <label title="How far in from the edge of the marked cells the land reaches its height">Coast width <input type="range" id="lm-c" min="2048" max="16384" step="256" value="${LM.coast}"><span>${LM.coast}</span></label>
      <label title="Rolling ground on top, as rough as the game's land (1) or smoother or rougher">Roughness <input type="range" id="lm-r" min="0" max="2" step="0.1" value="${LM.rough}"><span>${LM.rough}</span></label>
      <label class="msg" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="lm-p" ${LM.paint ? 'checked' : ''}> Texture it the way the region's land is</label>
      <div class="actions"><button class="btn sm primary" id="lm-raise">Raise the marked cells into land</button></div>
      <div class="msg" style="font-size:11.5px">Cells with no land get some first (the sea bed). The edges with unmarked cells stay as they are. One Undo takes it back; then shape it further with ⛰ Ground in 3D.</div></div>` : ''}${n && !bare ? '</details>' : ''}
    ${lsHtml()}
    <h3>Height maps${lsGuide('Height maps')}</h3>
    <div class="actions"><button class="btn sm" id="lm-export" ${n ? '' : 'disabled'} title="The marked cells (the box round them) as a 16-bit greyscale PNG, a pixel a point of the land">⬇ Save marked as a height map</button>
      <button class="btn sm" id="lm-import">⬆ Bring in a height map…</button><input type="file" id="lm-file" accept=".png,image/png" style="display:none"></div>
    <div class="msg" style="font-size:11.5px">Work on the land in World Machine, Gaea, GIMP or Krita and bring it back: a map the Workshop saved comes back where it was, at the same heights.</div>
    <div id="lm-imp"></div>`;
}
// the import box, once a PNG is picked: where it goes, how high, and the sea level
function lmImportHtml(f){
  const I = LM.imp;
  return `<div class="lm-raise" style="border:1px solid var(--line2);border-radius:6px;padding:8px">
    <div class="msg"><b>${esc(I.name)}</b>: ${I.info.w} × ${I.info.h} pixels${I.info.x0 != null ? ', saved by the Workshop from cells ' + I.info.x0 + ', ' + I.info.y0 + ' to ' + I.info.x1 + ', ' + I.info.y1 : ''}.</div>
    <label title="The cell at the map's bottom-left (south-west) corner">South-west cell <input class="inp" id="lmi-x" type="number" value="${I.gx}" style="width:70px"> <input class="inp" id="lmi-y" type="number" value="${I.gy}" style="width:70px"></label>
    <label title="How many cells wide the map becomes (stretched to fit, its shape kept); at a pixel a point it is ${I.info.across}">Cells across <input class="inp" id="lmi-n" type="number" min="1" max="40" value="${I.across}" style="width:70px"> <span id="lmi-down" style="width:auto;text-align:left;color:var(--faint)"></span></label>
    <label title="The height of the map's white">White is <input class="inp" id="lmi-w" type="number" step="64" value="${I.white}" style="width:90px"> units high</label>
    <label title="The grey that is the water line: darker is under the sea">Sea level at <input class="inp" id="lmi-s" type="number" min="0" max="99" step="1" value="${I.sea}" style="width:70px"> % grey</label>
    <label title="How far in from the area's edge the map fades in from the land around it">Blend <input type="range" id="lmi-b" min="256" max="8192" step="256" value="${I.blend}"><span>${I.blend}</span></label>
    <label class="msg" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="lmi-p" ${I.paint ? 'checked' : ''}> Texture it the way the region's land is</label>
    <label class="msg" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="lmi-a"> Allow settled cells</label>
    <div class="actions"><button class="btn sm primary" id="lmi-go">Bring it in</button><button class="btn sm" id="lmi-x2">Cancel</button></div>
    <div class="msg" id="lmi-note" style="font-size:11.5px"></div></div>`;
}
function lmImportBind(){
  const I = LM.imp, box = $('#lm-imp'); if (!box) return;
  if (!I){ box.innerHTML = ''; return; }
  box.innerHTML = lmImportHtml();
  const down = () => { const n = Math.max(1, +$('#lmi-n').value || 1), m = Math.max(1, Math.round(n * (I.info.h - 1) / Math.max(1, I.info.w - 1)));
    $('#lmi-down').textContent = `× ${m} = ${n * m} cells, black at ${Math.round(lmBlack())}`; };
  const lmBlack = () => {
    const w = +$('#lmi-w').value, sv = +$('#lmi-s').value, s = Math.min(99, Math.max(0, sv)) / 100;
    if (w === I.white && sv === I.sea) return I.black;          // (as saved: exactly the heights it came from)
    return -w * s / (1 - s);
  };
  for (const id of ['lmi-n', 'lmi-w', 'lmi-s']) $('#' + id).oninput = down;
  $('#lmi-b').oninput = e => { e.target.nextElementSibling.textContent = e.target.value; };
  down();
  $('#lmi-x2').onclick = () => { LM.imp = null; lmImportBind(); };
  $('#lmi-go').onclick = async () => {
    if (!await needProject()) return;
    const go = $('#lmi-go'); go.disabled = true; go.textContent = 'Bringing it in…';
    try {
      const r = await post('/api/land/heightmap/import', {png: I.png, gx: +$('#lmi-x').value, gy: +$('#lmi-y').value, across: +$('#lmi-n').value,
        black: lmBlack(), white: +$('#lmi-w').value, blend: +$('#lmi-b').value, paint: $('#lmi-p').checked, allow_settled: $('#lmi-a').checked});
      toast(`Brought the height map in over ${r.cells} cell${r.cells === 1 ? '' : 's'} (${r.across} × ${r.down})${r.new ? `, ${r.new} new` : ''}${r.eased ? `; ${r.eased} steps too steep for the game eased` : ''}${r.moved ? `; ${r.moved} objects followed it` : ''}. Changes to the ground show in game after a restart.`);
      LM.imp = null;
      W.lands = {}; if (typeof v3LandsReload === 'function') v3LandsReload();
      await afterChange(); await lmLoad(true, true);
      await lmReloadObjects();
      await loadAround(Math.floor(W.cam.x / CELL), Math.floor(W.cam.y / CELL));
      drawMap(); renderWside();
    } catch (err){ $('#lmi-note').textContent = err.message; go.disabled = false; go.textContent = 'Bring it in'; }
  };
}
async function lmExport(){
  const ks = LM.data.marks.map(k => k.split(',').map(Number)); if (!ks.length) return;
  const xs = ks.map(k => k[0]), ys = ks.map(k => k[1]);
  try {
    const r = await post('/api/land/heightmap/export', {x0: Math.min(...xs), y0: Math.min(...ys), x1: Math.max(...xs), y1: Math.max(...ys)});
    const bin = atob(r.png), bytes = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([bytes], {type: 'image/png'})); a.download = r.name;
    document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    toast(`Saved ${r.name}: ${r.size[0]} × ${r.size[1]} pixels, black ${r.lo} and white ${r.hi} units high.`);
  } catch (err){ toast(err.message, true); }
}
async function lmPicked(file){
  const buf = new Uint8Array(await file.arrayBuffer());
  let s = ''; for (let i = 0; i < buf.length; i += 8192) s += String.fromCharCode.apply(null, buf.subarray(i, i + 8192));
  const png = btoa(s);
  try {
    const info = await post('/api/land/heightmap/info', {png});
    const ks = (LM.data.marks || []).map(k => k.split(',').map(Number));
    const known = info.x0 != null;
    const black = known ? info.black : -2048, white = known ? info.white : 4096;
    LM.imp = {png, info, name: file.name, paint: !known,
      gx: known ? info.x0 : ks.length ? Math.min(...ks.map(k => k[0])) : (W.info ? W.info.gx : 0),
      gy: known ? info.y0 : ks.length ? Math.min(...ks.map(k => k[1])) : (W.info ? W.info.gy : 0),
      across: known ? info.x1 - info.x0 + 1 : info.across, white, black, sea: Math.round(Math.max(0, Math.min(99, -black / (white - black) * 100))),
      blend: known ? 256 : 2048};
    lmImportBind();
  } catch (err){ toast(err.message, true); }
}
function lmCss(){
  if ($('#lm-css')) return;
  const c = document.createElement('style'); c.id = 'lm-css';
  c.textContent = `.lm-legend{display:flex;flex-wrap:wrap;gap:4px 10px;margin-top:6px;font-size:11.5px;color:var(--muted)}
    .lm-legend span{display:flex;gap:4px;align-items:center;cursor:help}.lm-legend i{display:inline-block;width:12px;height:12px;border-radius:2px;box-sizing:border-box}
    .lm-legend .lm-hatch{background:repeating-linear-gradient(135deg,#ffffff40 0 2px,transparent 2px 5px);border:1px solid var(--line2)}
    .lm-raise{display:flex;flex-direction:column;gap:4px;margin-top:6px}.lm-raise label{display:flex;gap:6px;align-items:center;font-size:12px;color:var(--muted)}
    .lm-raise input[type=range]{flex:1;min-width:0}.lm-raise label span{width:44px;text-align:right;color:var(--text)}`;
  document.head.appendChild(c);
}
async function lmViewBind(i){
  if (!i || i.interior) return;
  lmCss();
  if (!LM.data){ try { await lmLoad(); } catch (e){ return; } renderWside(); return; }
  const sh = $('#lm-show'); if (sh) sh.onchange = () => { LM.show = sh.checked; drawMap(); };
  const fl = $('#lm-flow'); if (fl) fl.onchange = () => { LM.flowOn = fl.checked; if (fl.checked){ LM.show = true; lmFlowLoad(); } else { LM.flow = null; } drawMap(); };
  const bf = $('#lm-before'); if (bf){
    bf.onpointerdown = e => { e.preventDefault(); lmShowBefore(true); };
    bf.onpointerup = bf.onpointerleave = bf.onpointercancel = () => lmShowBefore(false);
  }
  const mk = $('#lm-mark'); if (mk) mk.onclick = async () => { if (V3.on) await v3Enable(false); lmMark(); };
  const cl = $('#lm-clear'); if (cl) cl.onclick = async () => {
    if (!await needProject()) return;
    await lmMarksPost({clear: true}); drawMap(); renderWside();
  };
  const rv = $('#lm-revert'); if (rv) rv.onclick = async () => {
    if (!await needProject()) return;
    const cells = LM.data.marks.slice(); if (!cells.length) return;
    rv.disabled = true;
    try {
      const r = await post('/api/land/revert', {cells});
      toast(`Put the land back in ${r.cells} cell${r.cells === 1 ? '' : 's'}. Undo brings yours back.`);
      W.lands = {}; if (typeof v3LandsReload === 'function') v3LandsReload();
      await afterChange(); await lmLoad(true, true);
      await lmReloadObjects();
      await loadAround(Math.floor(W.cam.x / CELL), Math.floor(W.cam.y / CELL));
      drawMap(); renderWside();
    } catch (err){ toast(err.message, true); rv.disabled = false; }
  };
  const dr = $('#lm-dress'); if (dr) dr.onclick = () => lmDressAsk();
  for (const [id, f] of [['lm-h', 'height'], ['lm-c', 'coast'], ['lm-r', 'rough']]){
    const el = $('#' + id); if (el) el.oninput = () => { LM[f] = +el.value; el.nextElementSibling.textContent = el.value; };
  }
  const pp = $('#lm-p'); if (pp) pp.onchange = () => { LM.paint = pp.checked; };
  const go = $('#lm-raise'); if (go) go.onclick = () => lmRaise(go);
  const ex = $('#lm-export'); if (ex) ex.onclick = lmExport;
  const im = $('#lm-import'), fi = $('#lm-file');
  if (im && fi){ im.onclick = () => fi.click(); fi.onchange = () => { if (fi.files[0]) lmPicked(fi.files[0]); fi.value = ''; }; }
  lmImportBind();
  lsBind();
}

// ---------- Shapes drawn on the map (landshapes.py): layers of a plan over the marked cells ----------
const LS_KINDS = {
  coast:   {icon: '🏝', label: 'Coast', color: '#7fd1ff', closed: true, how: 'Click along the shore all the way round the land; click the first point (or double-click) to close it. The outline becomes the waterline: inside rises out of the sea.'},
  ridge:   {icon: '⛰', label: 'Ridge', color: '#e8d27a', how: 'Click along the crest, double-click to finish. A range rises along it.'},
  river:   {icon: '〰', label: 'River', color: '#4aa8ff', how: 'Click from the source down to the sea, double-click to finish. Its bed is dug under the water all along (the game has one water level).'},
  valley:  {icon: '⌄', label: 'Valley', color: '#b6e08a', how: 'Click along the valley floor, double-click to finish. A dry trough.'},
  plateau: {icon: '▭', label: 'Plateau', color: '#f0a060', closed: true, how: 'Click round the top, then the first point to close. A level top with a cliff round it.'},
  lake:    {icon: '◍', label: 'Lake', color: '#58c8e8', closed: true, how: 'Click round the shore, then the first point to close. A basin under the water line.'},
  stamp:   {icon: '◉', label: 'Stamp', color: '#ff8fb8', how: 'Click where it goes: a volcano, a crater, a dome, or a piece of the game\'s own land.'},
  spring:  {icon: '⇣', label: 'Spring', color: '#5fd0ff', point: true, how: 'Click where a river rises. It finds its own way down to the water.'},
  // (a line the region's cliff rocks are chained along, facing the drop: cliffline.py; it shapes no ground itself)
  cliff:   {icon: '🪨', label: 'Cliff', color: '#d8a878', how: 'Click along the edge of the drop, double-click to finish. The rocks the region makes its cliffs of are chained along it, facing the lower side.'},
  // (an outline that shapes nothing: pick it, and 🪨 Dress… keeps to it; landshapes leaves it out)
  area:    {icon: '▢', label: 'Dress area', color: '#9be37a', closed: true, how: 'Click round a part of the land, then the first point to close. It changes no ground: 🪨 Dress… can dress only inside it.'},
  // (a farm or an orchard laid on the outline, storydress.lay_field; the longest edge is the gate side. No ground shaped)
  farm:    {icon: '🌾', label: 'Farm', color: '#e0c060', closed: true, how: 'Click round the farm, then the first point to close. Fields of the region\'s own crop fill it, the culture\'s farm fence round them; the longest side has the gate.'},
  orchard: {icon: '🍐', label: 'Orchard', color: '#a0d070', closed: true, how: 'Click round the orchard, then the first point to close. A loose grid of the region\'s fruit tree fills it.'},
  // (a town's outline: its streets and buildings planned in a culture's way, townplan.py; it shapes no ground itself)
  // (a dungeon's door outside: built by Build the dungeons with the dungeon generator, placeplan.py; it shapes no ground)
  // (a road between towns: its bed cut level across and painted by Shape the ground, landroads.py; it shapes no other ground)
  road:    {icon: '🛤', label: 'Road', color: '#e0c090', how: 'Click along the road from town to town, double-click to finish. Shape the ground cuts its bed level across and paints it in the culture\'s road texture.'},
  // (where a town's docks go: the game's own dock scene laid on the shore by Build the places, harbours.py)
  label: {icon: '🏷', label: 'Name', color: '#f0e0c8', point: true, nodraw: true, how: 'Proposed with the places: a name of the land\'s, a peak, a pass, a headland, a lake or a crossing, given to its cell as the game names Mount Kand\'s.'},
  small: {icon: '✦', label: 'Small place', color: '#e8d27f', point: true, nodraw: true, how: 'Proposed between the places: a camp, a cart by the road, a grave, someone\'s remains, a wayside shrine, a wreck, a fishing spot: one of the game\'s own laid on this ground.'},
  harbour: {icon: '⚓', label: 'Harbour', color: '#7fc8e8', point: true, nodraw: true, how: 'Proposed with a town by the water: its docks, boats and nets, one of the game\'s own docks laid on this shore.'},
  dungeon: {icon: '🕳', label: 'Dungeon', color: '#d89060', point: true, how: 'Click where its door outside goes. Build the dungeons makes it with the Dungeon tool, its door facing down the slope.'},
  town:    {icon: '🏘', label: 'Town', color: '#ffb86b', closed: true, how: 'Click round where the town goes, then the first point to close. Its streets and buildings are planned the way a culture\'s towns are.'},
  // (a keep or castle: its walls, towers, keep and rooms planned the way a culture builds its forts, castle.py, web/castle.js)
  castle:  {icon: '🏰', label: 'Castle', color: '#e0a060', closed: true, how: 'Click round where the castle goes, then the first point to close. Its walls, towers and keep are planned the way a culture builds its forts.'},
  // (drawn in a town, from its panel: its own streets, quarters and wall, PIN2 2026-11-01; townplan opts)
  street:  {icon: '〰', label: 'Street', color: '#d8c8a8', town: true, how: 'Click along the street, double-click to finish. The town\'s streets follow the ones you draw.'},
  zone:    {icon: '▧', label: 'Zone', color: '#c890ff', closed: true, town: true, how: 'Click round a quarter of the town, then the first point to close. Pick what it is: houses, business or noble.'},
  gate:    {icon: '⛩', label: 'Gate', color: '#4caf50', point: true, town: true, how: 'Click on the wall where a way in goes, one click a gate. The wall opens only at the gates you put, and a street runs in from each. Drag one to move it.'},
  wall:    {icon: '🧱', label: 'Wall', color: '#b08a60', closed: true, town: true, how: 'Click round the town: the wall keeps to a grid of its pieces from your first point, its corners square. The town fills it.'},
};
const LS_ZONES = {residential: ['Houses', '#7fbf7f'], business: ['Business', '#5aa0dc'], noble: ['Noble', '#c85a8c']};
const lsNoShape = k => k === 'area' || k === 'town' || k === 'dungeon' || k === 'road' || k === 'harbour' || k === 'small' || k === 'label' || k === 'castle' || k === 'cliff' || k === 'farm' || k === 'orchard' || !!(LS_KINDS[k] && LS_KINDS[k].town);
const lsIsField = k => k === 'farm' || k === 'orchard';
// sliders per kind: [param, label, min, max, step, tip]
const LS_PARAMS = {
  area: [],
  cliff: [['height', 'Height', 200, 3000, 50, 'About how tall the face stands: the rocks are scaled to it within the sizes the game uses them at'], ['amount', 'Loose rocks', 0, 2, 0.25, 'Boulders at the foot and pieces on the crest: 1 as the game has them, 0 the face alone']],
  town: [], castle: [], street: [], zone: [], wall: [], farm: [], orchard: [], dungeon: [], road: [], harbour: [], small: [], label: [], gate: [],
  coast: [['height', 'Height', 0, 6000, 50, 'How high the land stands a coast width in from the water'], ['width', 'Coast width', 1024, 16384, 256, 'How far it takes to rise out of the sea'], ['wander', 'Wander', 0, 2, 0.1, 'Small bays and headlands along the waterline (a few hundred units either side of the line drawn)']],
  ridge: [['height', 'Crest', 500, 12000, 100, 'The crest\'s height (lower at the ends)'], ['width', 'Width', 1024, 24576, 256, 'From the crest out to its foot'], ['sharp', 'Sharp', 0, 1, 0.05, '0 rounded hills, 1 a knife-edge crest'], ['spurs', 'Spurs', 0, 2, 0.1, 'How much its width wanders, in spurs and gullies'],
    ['crags', 'Crags', 0, 2, 0.1, 'Sharp crags and arêtes near the crest (0: smooth)']],
  river: [['depth', 'Bed depth', 64, 1024, 16, 'How far under the water its bed lies'], ['width', 'Bed width', 64, 1536, 32, 'Half the width of its bed'], ['banks', 'Banks', 256, 8192, 128, 'How far out its banks reach the ground']],
  valley: [['depth', 'Depth', 100, 4000, 50, 'How deep below the ground (it stays above the water)'], ['width', 'Width', 1024, 16384, 256, 'From its floor out to the rim'], ['round', 'U or V', 0, 1, 0.05, '1 a rounded U, 0 a V']],
  plateau: [['height', 'Top', 0, 8000, 50, 'The height of its top'], ['width', 'Cliff', 128, 4096, 64, 'How far in from its edge the top is reached'], ['terraces', 'Terraces', 0, 6, 1, 'Steps up its sides']],
  lake: [['depth', 'Depth', 64, 2000, 16, 'How deep its middle is'], ['width', 'Shore', 256, 6144, 128, 'How far its shore slopes']],
  spring: [['rise', 'Water from', 0, 4000, 50, 'Above this height it is a dry ravine; below it, a river'], ['wander', 'Winding', 0, 2, 0.1, 'How much it winds where the land is flat'],
    ['depth', 'Bed depth', 64, 1024, 16, 'How far under the water its bed lies'], ['width', 'Bed width', 64, 1536, 32, 'Half the width of its bed'], ['banks', 'Banks', 256, 8192, 128, 'How far out its banks reach the ground']],
  stamp: [['radius', 'Radius', 1024, 32768, 256, 'How far it reaches'], ['height', 'Height', -6000, 12000, 50, 'Its height (a crater: its depth); for the game\'s land, 0 keeps it as it is'], ['stretch', 'Stretch', 1, 4, 0.1, 'An oval: so many times longer one way (1: round)'], ['turn', 'Turn', 0, 359, 1, 'Which way its long side points (0: east, 90: north); the game\'s land turns with it']],
};
const LS_SHAPES = [['volcano', 'Volcano'], ['cone', 'Cone'], ['caldera', 'Caldera'], ['crater', 'Crater'], ['dome', 'Dome'], ['mesa', 'Mesa'], ['game', 'The game\'s own land']];
// (a new layer's own seed: every castle and town started at seed 1 and came out the same, the user 2026-11-06)
function lsFresh(p){ if (p.seed != null) p.seed = 1 + Math.floor(Math.random() * 99999); return p; }
const LS_DEFAULTS = {area: {}, harbour: {scene: 0, phi: 0, built: '', proposed: false}, small: {what: 'camp', scene: 0, phi: 0, built: '', proposed: false}, label: {what: 'peak', name: '', built: '', proposed: false}, road: {culture: '', proposed: false}, dungeon: {kit: 'cave_mud', name: '', size: 'small', rz: 0, built: '', place: 'cave'}, cliff: {height: 600, side: 0, amount: 1, raise: 0, seed: 1}, town: {culture: '', seed: 1}, farm: {culture: '', seed: 1, built: ''}, orchard: {culture: '', seed: 1, built: ''}, castle: {style: 'Imperial', size: 'medium', seed: 1, rooms: 'furnished'}, street: {}, zone: {zone: 'residential'}, wall: {}, gate: {}, coast: {height: 600, width: 6144, wander: 1, sea: 0}, ridge: {height: 3500, width: 3072, sharp: 0.5, spurs: 1, crags: 0.6}, river: {depth: 256, width: 256, banks: 2048, canyon: 0},
  valley: {depth: 900, width: 4096, round: 0.6}, plateau: {height: 2000, width: 768, terraces: 0}, lake: {depth: 400, width: 1536},
  stamp: {shape: 'volcano', radius: 8192, height: 4000, turn: 0, stretch: 1, src: null}, spring: {rise: 800, wander: 1, depth: 256, width: 256, banks: 2048, canyon: 0}};

// ----- whole plans to start from, laid out over the marked cells (or the 4 x 4 cells round the view, then marked):
// the shapes and passes of an island, a mountain range, a river valley, a volcanic isle or a lake in the hills, to
// change from there. ↶ takes it back
const LS_PRESETS = [
  ['island', '🏝 Island', 'A coast round the marked cells, a ridge along it and a spring: a whole island'],
  ['range', '⛰ Mountain range', 'Two craggy ridges along the marked cells, with valleys and rock layers'],
  ['valley', '〰 River valley', 'A valley down the middle with a river in it and hills on both sides'],
  ['volcano', '🌋 Volcanic isle', 'A round coast with a volcano in the middle'],
  ['lake', '◍ Lake in the hills', 'A lake with low hills round it'],
];
async function lsPreset(kind){
  if (!await needProject()) return;
  const P = LM.plan, C = CELL;
  let keys = LM.data.marks.slice();
  if (!keys.length){
    const gx = Math.floor(W.cam.x / C), gy = Math.floor(W.cam.y / C);
    for (let x = gx - 2; x < gx + 2; x++) for (let y = gy - 2; y < gy + 2; y++){ const c = lmCell(x + ',' + y); if (!(c && c[0] === 'settled')) keys.push(x + ',' + y); }
    try { await lmMarksPost({add: keys}); } catch (e){ toast(e.message, true); return; }
  }
  const xs = keys.map(k => +k.split(',')[0]), ys = keys.map(k => +k.split(',')[1]);
  const x0 = Math.min(...xs) * C, x1 = (Math.max(...xs) + 1) * C, y0 = Math.min(...ys) * C, y1 = (Math.max(...ys) + 1) * C;
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, wx = x1 - x0, wy = y1 - y0, long = wx >= wy;
  const Lg = Math.max(wx, wy), S = Math.min(wx, wy);
  // (a point t of the way along the long side from the middle, `off` across it)
  const along = (t, off) => long ? [Math.round(cx + t * Lg), Math.round(cy + off * S)] : [Math.round(cx + off * S), Math.round(cy + t * Lg)];
  const ring = (rx, ry, n, wob) => Array.from({length: n}, (_, i) => { const a = i / n * Math.PI * 2, k = 1 + (wob || 0) * Math.sin(a * 3 + 1); return [Math.round(cx + Math.cos(a) * rx * k), Math.round(cy + Math.sin(a) * ry * k)]; });
  const lay = (k, pts, p) => ({id: String(Date.now()) + Math.random().toString(36).slice(2, 6), kind: k, name: '', on: true, pts, p: lsFresh(Object.assign({}, LS_DEFAULTS[k], p || {}))});
  const W_ = (f, lo, hi) => Math.round(Math.max(lo, Math.min(hi, S * f)) / 128) * 128;
  let layers = [], passes = {};
  if (kind === 'island'){
    layers = [lay('coast', ring(wx * 0.4, wy * 0.4, 12, 0.08), {height: 600, width: W_(0.18, 2048, 6144)}),
      lay('ridge', [along(-0.28, 0.02), along(0, -0.04), along(0.28, 0.03)], {height: 2800, width: W_(0.22, 2048, 8192)}),
      lay('spring', [along(0.12, -0.03)], {rise: 900})];
    passes = {valleys: 1, rock: 0.3};
  } else if (kind === 'range'){
    layers = [lay('ridge', [along(-0.42, -0.08), along(-0.15, -0.12), along(0.15, -0.06), along(0.42, -0.1)], {height: 6500, width: W_(0.3, 3072, 12288), crags: 1.2, sharp: 0.7}),
      lay('ridge', [along(-0.3, 0.22), along(0.05, 0.18), along(0.35, 0.24)], {height: 3800, width: W_(0.2, 2048, 8192), crags: 0.8})];
    passes = {valleys: 1.2, rock: 0.6};
  } else if (kind === 'valley'){
    const line = [along(-0.45, 0.02), along(-0.15, -0.04), along(0.15, 0.04), along(0.45, -0.02)];
    layers = [lay('ridge', [along(-0.42, -0.34), along(0, -0.38), along(0.42, -0.33)], {height: 3200, width: W_(0.25, 2048, 8192)}),
      lay('ridge', [along(-0.42, 0.34), along(0, 0.36), along(0.42, 0.32)], {height: 2800, width: W_(0.25, 2048, 8192)}),
      lay('valley', line, {depth: 1200, width: W_(0.28, 2048, 8192)}), lay('river', line.map(p => p.slice()))];
    passes = {valleys: 0.6};
  } else if (kind === 'volcano'){
    const r = Math.min(wx, wy) * 0.4;
    layers = [lay('coast', ring(r, r, 12, 0.06), {height: 500, width: W_(0.15, 2048, 6144)}),
      lay('stamp', [[Math.round(cx), Math.round(cy)]], {shape: 'volcano', radius: Math.round(r * 0.75 / 256) * 256, height: 6000})];
    passes = {valleys: 0.8, rock: 0.4};
  } else if (kind === 'lake'){
    layers = [lay('ridge', ring(wx * 0.36, wy * 0.36, 9, 0.1).slice(0, 7), {height: 1800, width: W_(0.18, 2048, 6144)}),
      lay('lake', ring(wx * 0.18, wy * 0.18, 10, 0.12), {depth: 500})];
    passes = {valleys: 0.5};
  }
  P.layers = layers; P.passes = Object.assign({}, LS_PASSES, P.passes || {}, passes);
  LM.sel = null; LM.prevOn = true; LM.show = true;
  lsChanged(true);
  const name = (LS_PRESETS.find(p => p[0] === kind) || [])[1] || kind;
  toast(`${name}: ${layers.length} shapes over ${keys.length} cells. Change them as you like, then Shape them; ↶ takes it back.`);
}

function lsHtml(){
  const P = LM.plan || {layers: []}, sel = P.layers[LM.sel];
  // (the ground sections only when a ground shape is drawn: a town or castle alone showed Protection, the passes,
  // Dressing and Shape the marked cells, none of which touch it, 2026-11-04; or the region pass is on)
  const ng = P.layers.filter(L => L.on !== false && !lsNoShape(L.kind)).length, gnd = ng || lsTerrOn() || P.layers.some(L => L.kind === 'road' && L.on !== false);
  const row = (L, i) => `<div class="ls-row${i === LM.sel ? ' on' : ''}" data-i="${i}"><input type="checkbox" data-on="${i}" ${L.on !== false ? 'checked' : ''} title="Use this shape">
      <span style="color:${LS_KINDS[L.kind].color}">${LS_KINDS[L.kind].icon}</span><span class="ls-n">${esc(L.name || LS_KINDS[L.kind].label)}</span>
      <button class="xbtn" data-up="${i}" title="Earlier (later shapes act on what earlier ones made)">↑</button><button class="xbtn" data-dn="${i}" title="Later">↓</button><button class="xbtn" data-dup="${i}" title="Duplicate (a copy beside it)">⧉</button><button class="xbtn" data-del="${i}" title="Remove">✕</button></div>`;
  let params = '';
  if (sel){
    const p = sel.p || {};
    if (sel.kind === 'town') params += lsTownHtml(sel);
    if (sel.kind === 'dungeon') params += lsDungeonHtml(sel);
    if (sel.kind === 'label') params += `<label title="The name its cell takes when built: on the game's map and as you walk in">Name <input class="inp" id="lsn-name" value="${esc(sel.name || (sel.p || {}).name || '')}"></label>${(sel.p || {}).built ? `<div class="msg" style="font-size:11.5px">Built: ${esc(sel.p.built)}.</div>` : ''}`;
    if (lsIsField(sel.kind)) params += lsFieldHtml(sel);
    if (LS_KINDS[sel.kind].town) params += lsTownPartHtml(sel);
    if (sel.kind === 'castle' && typeof csHtml === 'function') params += csHtml(sel);
    if (sel.kind === 'stamp') params += `<label>Shape <select class="inp" id="ls-shape">${LS_SHAPES.map(([v, t]) => `<option value="${v}" ${p.shape === v ? 'selected' : ''}>${t}</option>`).join('')}</select></label>`;
    if (sel.kind === 'stamp' && p.shape === 'game'){
      const s = p.src || ['', '', '', ''];
      params += `<label title="The game's cells to copy (their shape over their own surroundings), at most 6 x 6">Cells <input class="inp" data-src="0" type="number" value="${s[0]}" style="width:52px"><input class="inp" data-src="1" type="number" value="${s[1]}" style="width:52px"> to <input class="inp" data-src="2" type="number" value="${s[2]}" style="width:52px"><input class="inp" data-src="3" type="number" value="${s[3]}" style="width:52px"></label>
        <div class="actions"><button class="btn sm" id="ls-src-here" title="Copy the cell open now (and the ones round it)">Use the cell open now</button></div>`;
    }
    for (const [k, lab, mn, mx, st, tip] of LS_PARAMS[sel.kind]) params += `<label title="${esc(tip)}">${lab} <input type="range" data-p="${k}" min="${mn}" max="${mx}" step="${st}" value="${p[k] != null ? p[k] : LS_DEFAULTS[sel.kind][k]}"><span>${p[k] != null ? p[k] : LS_DEFAULTS[sel.kind][k]}</span></label>`;
    if (sel.kind === 'cliff'){
      const picked = selectionRefs().map(([c, r]) => r.id).filter(id => /rock|stone|boulder|cliff|crag/i.test(id));
      params += `<label title="Which side of the line drops away: the lower ground (or the water) as drawn, or say which">Drops <select class="inp" id="ls-cside"><option value="0" ${!p.side ? 'selected' : ''}>to the lower side</option><option value="1" ${p.side === 1 ? 'selected' : ''}>to the left (as drawn)</option><option value="-1" ${p.side === -1 ? 'selected' : ''}>to the right</option></select></label>
        <label title="Whose rocks: the line's own region's, or another's">Like ${lsRegionSel('ls-like', sel.like || '', 'its own region')}</label>
        ${picked.length ? `<label class="msg" style="display:flex;gap:6px;align-items:center" title="Chain the rocks you have selected (${esc(picked.slice(0, 3).join(', '))}${picked.length > 3 ? '…' : ''}) instead of the region's"><input type="checkbox" id="ls-cpick" ${p.pick ? 'checked' : ''}> Use the ${picked.length} selected rock${picked.length === 1 ? '' : 's'}</label>` : ''}
        <label class="msg" style="display:flex;gap:6px;align-items:center" title="Lift the ground behind the line to the face's top, fading back into the land, so the land meets the cliff"><input type="checkbox" id="ls-craise" ${p.raise ? 'checked' : ''}> Raise the land behind it</label>
        <label class="msg" style="display:flex;gap:6px;align-items:center" title="The steep ground within 1,000 of the line clad the way the game's gorges are: faces, rocks on the lip and at the foot, every piece sunk until no bottom edge shows"><input type="checkbox" id="ls-cclad" ${p.clad !== 0 ? 'checked' : ''}> Rock the slopes beside it</label>
        <div class="actions"><button class="btn sm primary" id="ls-clay" title="Lay the rocks along the line now. One Undo takes them back; lay it again for another arrangement">🪨 Lay the cliff</button></div>`;
    }
    if (sel.kind === 'river' || sel.kind === 'spring') params += `<label class="msg" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="ls-canyon" ${p.canyon ? 'checked' : ''}> A canyon (steep walls)</label>`;
    if (sel.kind === 'coast') params += `<label class="msg" style="display:flex;gap:6px;align-items:center" title="Off: only a strip just outside the outline goes under water, and other land further out stays. On: all the land outside every coast in the marked cells sinks to the sea bed."><input type="checkbox" id="ls-sea" ${p.sea ? 'checked' : ''}> Sea outside (sink all other land)</label>`;
    // (where it acts, and whose character its ground takes; coasts are worked out together, so not for them)
    if (sel.kind !== 'coast' && !lsNoShape(sel.kind)){
      params += `<label title="Only in one region of the marked cells, fading out at its border" style="white-space:nowrap">Only in ${lsRegionSel('ls-only', (sel.only || [])[0] || '', 'everywhere', lsHereRegions())}</label>
        <label title="Its ground as rough and steep as another region's land; the textures stay the cell's own region's">Like ${lsRegionSel('ls-like', sel.like || '', 'its own region')}</label>`;
    }
    params += `<div class="msg" style="font-size:11.5px" title="Drag a point to move it; click the line to add a point; Ctrl+click a point to remove it; Shift+drag the line to move the whole shape">On the map: drag points · click the line to add · Ctrl+click removes · Shift+drag moves it all.${LS_KINDS[sel.kind].closed ? ' The last point joins the first.' : ''}</div>`;
    // (whether the marked cells cover it: a shape only changes the marked cells)
    const sc = lsShapeCells(sel), M = LM.data ? LM.data.marked : new Set(), inM = sc.filter(k => M.has(k)).length;
    if (inM < sc.length && !lsNoShape(sel.kind)) params += `<div class="msg warn" style="font-size:11.5px;margin-top:4px">${sc.length - inM} town cell${sc.length - inM === 1 ? '' : 's'} left as ${sc.length - inM === 1 ? 'it is' : 'they are'}.
      <button class="btn sm" id="ls-markit" title="Shift+click: mark the towns it reaches too, to shape them">⛰ Mark its cells</button></div>`;
  }
  return `<h3 style="display:flex;align-items:center;gap:4px">Shapes${lsGuide('Step 2: draw shapes')}<span style="flex:1"></span>
      <button class="btn sm" id="ls-undo" ${LM.hist.length ? '' : 'disabled'} title="Undo the last change to the shapes and their settings">↶</button><button class="btn sm" id="ls-redo" ${LM.fut.length ? '' : 'disabled'} title="Redo">↷</button></h3>
    <div class="ls-add">${Object.entries(LS_KINDS).filter(([k, K]) => !K.town && !K.nodraw).map(([k, K]) => `<button class="btn sm" data-add="${k}" title="${esc(K.how)}"><span style="color:${K.color}">${K.icon}</span> ${K.label}</button>`).join('')}</div>
    <label title="A whole plan laid out over the marked cells (or the 4 x 4 cells round the view), in place of the shapes there; ↶ takes it back" style="margin-top:6px">Start from <select class="inp" id="ls-preset"><option value="">a ready plan…</option>${LS_PRESETS.map(([v, t, tip]) => `<option value="${v}" title="${esc(tip)}">${t}</option>`).join('')}</select></label>
    ${P.layers.length ? `<div class="ls-list">${P.layers.map(row).join('')}</div>
      <div class="actions"><button class="btn sm" id="ls-clearall" title="Take every shape off the map (the land already shaped stays as it is)">Clear shapes</button></div>` : '<div class="msg" style="font-size:11.5px">Pick a shape and draw it on the map. Towns, castles, farms and orchards need no marked cells.</div>'}
    ${sel ? `<div class="lm-raise">${params}</div>` : ''}
    ${lsRegionPassHtml(P)}
    ${lsPlacesHtml(P)}
    ${lsYardHtml(P)}
    ${gnd ? lsPassesHtml(P, ng) : lsTexHtml(P)}
    ${gnd ? `<div class="lm-raise">
      ${ng ? `<label title="Rolling ground on the new land, as rough as the region's (1)">Roughness <input type="range" data-g="rough" min="0" max="2" step="0.1" value="${P.rough}"><span>${P.rough}</span></label>` : ''}
      <label title="How far in from the marked cells' edge the shapes fade in (the edges with other cells never move)">Edge fade <input type="range" data-g="fade" min="256" max="8192" step="256" value="${P.fade}"><span>${P.fade}</span></label>
      ${lsHereRegions().length > 1 || (P.only || []).length ? `<label title="Shape only the marked cells in one region; the rest stay as they are" style="white-space:nowrap">Only in ${lsRegionSel('ls-ponly', (P.only || [])[0] || '', 'all marked cells', lsHereRegions())}</label>` : ''}
      ${ng ? `<label class="msg" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="ls-paint" ${P.paint !== false ? 'checked' : ''}> Texture it the way the region's land is</label>` : ''}
      <label class="msg" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="ls-prev" ${LM.prevOn !== false ? 'checked' : ''}> Preview on the map</label>
      <div class="actions"><button class="btn sm" id="ls-seed" title="The same shapes with other rolling ground and shores">🎲 Re-roll</button><button class="btn sm primary" id="ls-apply" ${LM.data && LM.data.marks.length ? '' : 'disabled title="Mark the cells to shape first"'}>Shape the marked cells</button></div>
      <div class="msg" id="ls-note" style="font-size:11.5px">${LM.data && !LM.data.marks.length ? 'No cells marked: ⛰ Mark cells to shape them.' : `${LM.applyNote ? esc(LM.applyNote) + ' ' : ''}One Undo takes it back. The shapes stay, to change and shape again.`}</div></div>` : ''}`;
}
// stage 3 and 4 (landpasses.py, landdress.py): the natural passes and the dressing, with the plan's own defaults
const LS_PASSES = {detail: true, detail_k: 1, settle: true, angle: 0, gullies: 0, terraces: false, tstep: 256, tsharp: 0.6, tslope: 20, valleys: 0,
  rock: 0, rthick: 512, rdip: 0, rdir: 0, rshare: 0.45, ronly: ''};
const LS_DRESS = {variety: -1, tints: true, seams: true, hollows: true, shade: 1, region: '', assign: false, rocks: 1, flow: 0, shore: '', clad: true};
// the region pass (landregion.py): the land that is there made as rough, as broken into ranges and as cut by valleys
// as a hand-made region's, no shapes needed; Shape the ground runs it (tile by tile past 400 cells, one Undo)
const LS_TERRAIN = {on: false, like: '', relief: 1, ranges: 1, valleys: 1, cliffs: 1, rocks: true, rockfrom: '', trees: true, plants: true, falls: true, paint: false};
function lsTerrOn(){ return !!(LM.plan && LM.plan.terrain && LM.plan.terrain.on); }
// ----- places (placeplan.py): towns, villages and dungeons proposed at the game's rates and on its ground, as
// layers to move, drop or keep; towns are built by Shape, then build, dungeons by Build the dungeons
const LS_PLACES = {settlements: 1, dungeons: 1, small: 1, culture: ''};
const LS_PLACE_NAME = {harbour: ['harbour', 'harbours'], mine: ['mine', 'mines'], farm: ['field', 'fields'], city: ['city', 'cities'], town: ['town', 'towns'], village: ['village', 'villages'], cave: ['cave', 'caves'], tomb: ['tomb', 'tombs'],
  dwemer: ['Dwemer ruin', 'Dwemer ruins'], daedric: ['Daedric ruin', 'Daedric ruins'], fort: ['fort', 'forts'], tower: ['tower', 'towers'],
  farmstead: ['farmstead', 'farmsteads'], inn: ['roadside inn', 'roadside inns'], road: ['road', 'roads'], camp: ['camp', 'camps'], cart: ['cart', 'carts'],
  burial: ['burial site', 'burial sites'], cairn: ['cairn', 'cairns'], remains: ['remains', 'remains'], shrine: ['wayside shrine', 'wayside shrines'], wreck: ['wreck', 'wrecks'],
  fishing: ['fishing spot', 'fishing spots'], name: ['name', 'names']};
(function(){ if (document.getElementById('ls-step-css')) return; const st = document.createElement('style'); st.id = 'ls-step-css';
  st.textContent = '.ls-step{display:inline-block;min-width:15px;height:15px;line-height:15px;border-radius:8px;margin-right:5px;font-size:10.5px;text-align:center;background:var(--gold,#d2a85a);color:#1a1208;font-weight:700}';
  document.head.appendChild(st); })();
function lsPlacesHtml(P){
  const Q = P.places = Object.assign({}, LS_PLACES, P.places || {});
  if (!LM.cultures) lsCultures().then(cs => { if (cs && cs.length) renderWside(); });
  const cs = LM.cultures || [];
  const todo = lsPlacesToBuild(P);
  const cnt = {};
  for (const L of P.layers) if ((L.p || {}).proposed){ const k = L.p.place || L.kind; cnt[k] = (cnt[k] || 0) + 1; }
  const said = Object.entries(cnt).map(([k, n]) => `${n} ${(LS_PLACE_NAME[k] || [k, k])[n === 1 ? 0 : 1]}`).join(', ');
  const tr = {};
  for (const L of P.layers) if (L.kind === 'town' && (L.p || {}).trade) tr[L.p.trade] = (tr[L.p.trade] || 0) + 1;
  const LIVE = {harbour: 'by the sea', farm: 'by farming', mine: 'by a mine', trade: 'by trade'};
  const lives = Object.entries(tr).map(([k, n]) => `${n} ${LIVE[k] || k}`).join(', ');
  const sl = (key, lab, tip) => `<label title="${esc(tip)}">${lab} <input type="range" data-pl="${key}" min="0" max="2" step="0.1" value="${Q[key]}"><span>${Q[key]}</span></label>`;
  return `<h3>Places${lsGuide('Places')}</h3><div class="lm-raise">
      ${sl('settlements', 'Towns', 'Cities, towns and villages, as many as the game has on as much land (1). Set where the game sets its own: by the sea and big streams, on the flat')}
      ${sl('dungeons', 'Dungeons', 'Caves, tombs, Dwemer and Daedric ruins, forts and towers, as many as the game has on as much land (1): caves and tombs in hollows on steep ground, Dwemer ruins high up')}
      ${sl('small', 'Small things', 'Camps, carts by the road, graves, remains, wayside shrines, wrecks and fishing spots, as many as the game has between its places (1, about eleven in a hundred cells), each one of its own scenes')}
      <label title="Whose towns they are planned like, and so whose tombs and towers there are (only Dunmer land has them). Nearest: the game town nearest in weather and on the map">Culture <select class="inp" id="lsq-cult"><option value="">nearest in weather</option>${cs.map(c => `<option value="${esc(c.id)}" ${Q.culture === c.id ? 'selected' : ''}>${esc(c.id)}</option>`).join('')}</select></label>
      <div class="msg" style="font-size:11.5px" title="1 puts them on the map as markers to move or drop. 2, Shape, then build at the top, shapes the ground and builds the towns with their people. 3 builds the dungeons, fields, docks, small things and names. 4 brings travellers, campers and creatures (once). 5 needs the towns and dungeons built. Propose roads re-joins the towns after you move some">Press in order: <b class="ls-step">1</b> → <b class="ls-step">2</b> (top) → <b class="ls-step">3</b> → <b class="ls-step">4</b> → <b class="ls-step">5</b></div>
      <div class="actions"><button class="btn sm" id="lsq-go" ${LM.data && LM.data.marks.length ? '' : 'disabled title="Mark the cells first"'} title="Places for the marked cells, as layers to move or drop, grown as the game's: towns first, villages in the gaps, the roads joining them, farms and inns along the roads, dungeons by the roads and off the towns. Proposing again replaces the proposed places and roads not yet built"><b class="ls-step">1</b>🎲 Propose places</button><button class="btn sm" id="lsq-roads" ${P.layers.some(L => L.kind === 'town' && L.on !== false) || (LM.data && LM.data.marks.length) ? '' : 'disabled'} title="Roads between the towns drawn or proposed and the game's own towns near the marked cells, as the game's roads run: gently up the slopes, round the steep ground, never through water or a building. Shape the ground lays them">🛤 Propose roads</button><button class="btn sm primary" id="lsq-build" ${todo.length ? '' : 'disabled'} title="Make each dungeon and mine marker with the Dungeon tool (its door outside at the marker), lay the proposed farms' fields, the harbours' docks and the small things. One Undo for them all"><b class="ls-step">3</b>Build the places${todo.length ? ' (' + todo.length + ')' : ''}</button><button class="btn sm" id="lsq-folk" ${LM.data && LM.data.marks.length ? '' : 'disabled'} title="People by the roads and at the built camps, and the land's and the water's creatures, over the marked cells as many as the game has outside its towns: each person made in the region's own way, the creatures of the region's own lists. Press after the places are built; One Undo takes them back"><b class="ls-step">4</b>🧍 People and beasts</button><button class="btn sm" id="lsq-rum" ${LM.data && LM.data.marks.length ? '' : 'disabled'} title="The dungeons you've built in the marked cells talked of in the towns you've built near them: a topic each, saying where it lies and who is there, a rumour that teaches it, and a quest from the publican where a band holds one. Press after the towns and the places are built; One Undo takes them back"><b class="ls-step">5</b>📜 Rumours and quests</button></div>
      ${said ? `<div class="msg" style="font-size:11.5px">Proposed: ${esc(said)}.${lives ? ` Towns living ${esc(lives)}.` : ''} Shape, then build makes the towns.</div>` : ''}
    </div>`;
}
function lsDungeonHtml(sel){
  const p = sel.p || {}, kinds = typeof RUIN_KINDS !== 'undefined' ? RUIN_KINDS : [];
  const sizes = typeof RUIN_OPTS !== 'undefined' ? RUIN_OPTS.size : [['small', 'Small']];
  return `${p.place === 'mine' ? '<div class="msg" style="font-size:11.5px">The mine its town lives by.</div>' : ''}<label title="What it is: the Dungeon tool's kinds">Kind <select class="inp" id="lsd-kit">${kinds.map(k => `<option value="${esc(k[0])}" ${p.kit === k[0] ? 'selected' : ''}>${esc(k[1])}</option>`).join('')}</select></label>
    <label title="The place's name, its cell's">Name <input class="inp" id="lsd-name" value="${esc(p.name || '')}" placeholder="${esc((kinds.find(k => k[0] === p.kit) || [])[2] || '')}"></label>
    <label>Size <select class="inp" id="lsd-size">${sizes.map(([v, t]) => `<option value="${v}" ${p.size === v ? 'selected' : ''}>${esc(t)}</option>`).join('')}</select></label>
    ${p.built ? `<div class="msg" style="font-size:11.5px">Built: ${esc(p.built)}.</div>` : `<div class="actions"><button class="btn sm primary" id="lsd-build" title="Make it with the Dungeon tool, its door outside here, facing down the slope">Build it</button></div>`}`;
}
// (what Build the places makes: the dungeon and mine markers, the proposed farms and the harbours, not yet built)
function lsPlacesToBuild(P){
  return P.layers.filter(L => L.on !== false && !(L.p || {}).built && (L.kind === 'dungeon' || L.kind === 'harbour' || L.kind === 'small' || L.kind === 'label' || (L.kind === 'farm' && (L.p || {}).proposed)));
}
async function lsBuildDungeons(list, btn){
  if (!list.length || !await needProject()) return;
  if (btn){ btn.disabled = true; btn.textContent = `Building ${list.length}…`; }
  try {
    const r = await post('/api/land/places/build', {
      dungeons: list.filter(L => L.kind === 'dungeon').map(L => ({id: L.id, kit: L.p.kit, name: L.p.name || L.name, size: L.p.size, x: L.pts[0][0], y: L.pts[0][1], rz: L.p.rz})),
      farms: list.filter(L => L.kind === 'farm').map(L => ({id: L.id, pts: L.pts, culture: L.p.culture || '', seed: L.p.seed || 1})),
      harbours: list.filter(L => L.kind === 'harbour').map(L => ({id: L.id, scene: L.p.scene, x: L.pts[0][0], y: L.pts[0][1], phi: L.p.phi})),
      small: list.filter(L => L.kind === 'small').map(L => ({id: L.id, what: L.p.what, scene: L.p.scene, x: L.pts[0][0], y: L.pts[0][1], phi: L.p.phi})),
      labels: list.filter(L => L.kind === 'label').map(L => ({id: L.id, name: L.name || L.p.name, cell: `${Math.floor(L.pts[0][0] / 8192)},${Math.floor(L.pts[0][1] / 8192)}`}))});
    const mark = (id, v) => { const L = LM.plan.layers.find(x => x.id === id); if (L) L.p.built = v || 'yes'; };
    for (const b of r.built || []) mark(b.id, b.cell);
    // (a farm's own form, as its Make it writes it: things/plants/culture/outline's hash, so its editor shows it built)
    for (const b of r.farms || []){ const L = LM.plan.layers.find(x => x.id === b.id); if (L && b.things) L.p.built = [b.things, b.plants, String(L.p.culture || '').replace(/\//g, ' '), lsFieldHash(lsFieldKey(L))].join('/'); }
    for (const b of r.harbours || []) mark(b.id, b.pieces + ' pieces');
    for (const b of r.small || []) mark(b.id, b.things + ' things');
    for (const b of r.labels || []) mark(b.id, 'cell ' + b.cell);
    const bad = r.failed || [], nd = (r.built || []).length, nf = (r.farms || []).length, nh = (r.harbours || []).length, ns = (r.small || []).length, nn = (r.labels || []).length;
    const said = [nd ? `${nd} dungeon${nd === 1 ? '' : 's'}` : '', nf ? `${nf} field${nf === 1 ? '' : 's'}` : '', nh ? `${nh} harbour${nh === 1 ? '' : 's'}` : '', ns ? `${ns} small place${ns === 1 ? '' : 's'}` : '', nn ? `${nn} name${nn === 1 ? '' : 's'} on the land` : ''].filter(Boolean).join(', ') || 'nothing';
    toast(`Built ${said}${bad.length ? `; ${bad.length} not: ${bad[0].why}` : ''}${r.learning ? `. The Dungeon tool is still learning its ${r.learning} pieces: build the rest again in a few minutes` : ''}. One Undo takes them back.`, !!bad.length && !(nd + nf + nh + ns + nn));
    await afterChange(); await lmReloadObjects();
  } catch (err){ toast(err.message, true); }
  lsChanged(true);
}
// ----- the yardstick (yardstick.py): the marked cells against the hand-made region they take after
function lsYardHtml(P){
  const R = LM.yard, pct = k => ['steep30', 'steep45', 'road'].includes(k);
  const fmt = (k, v) => pct(k) ? `${(100 * v).toFixed(v < 0.1 ? 1 : 0)}%` : (v >= 100 ? Math.round(v) : +(+v).toFixed(v < 1 ? 2 : 1));
  const col = s => s >= 0.8 ? 'var(--green, #8fbf7a)' : s >= 0.5 ? 'var(--amber, #e2b04a)' : 'var(--red, #e0705b)';
  let body = '';
  if (R && R.layers && R.layers.length){
    body = `<div style="display:flex;align-items:baseline;gap:8px;margin:4px 0"><b style="font-size:20px">${R.score}</b><span class="msg" style="font-size:11.5px" title="Each layer: the smaller figure over the larger; the whole: their mean">against ${esc(R.like)} (${R.ref_cells} of its cells), ${R.cells} cells measured</span></div>
      <div style="display:grid;grid-template-columns:1fr auto auto 40px;gap:1px 8px;font-size:11.5px">
        <span class="msg">Layer</span><span class="msg">Here</span><span class="msg">Region</span><span></span>
        ${R.layers.map(L => `<span>${esc(L.label)}</span><span style="text-align:right">${fmt(L.key, L.ours)}</span><span style="text-align:right;opacity:.75">${fmt(L.key, L.game)}</span><span title="${L.score}" style="align-self:center;height:6px;border-radius:3px;background:${col(L.score)};width:${Math.max(4, Math.round(40 * L.score))}px"></span>`).join('')}
      </div>
      ${(R.worst || []).length ? `<div class="msg" style="font-size:11.5px;margin-top:6px">Cells to look at:</div>${R.worst.map(w => `<div style="display:flex;gap:6px;align-items:center;font-size:11.5px"><button class="btn sm" data-ylook="${esc(w.cell)}" title="Open the cell in 3D">Look</button><span>${esc(w.cell)}: ${esc(w.why)}</span></div>`).join('')}` : ''}`;
  } else if (R && R.cells === 0) body = '<div class="msg" style="font-size:11.5px">No land in the marked cells to measure.</div>';
  return `<h3>Yardstick${lsGuide('Yardstick')}</h3><div class="lm-raise">
      <div class="actions"><button class="btn sm" id="lsy-go" ${LM.data && LM.data.marks.length ? '' : 'disabled title="Mark the cells first"'} title="The marked cells as they stand, layer by layer (the ground, trees, plants, rocks, roads, places, small things, people, creatures), against the hand-made region they take after; and the cells furthest off">📏 Measure</button></div>
      ${body}</div>`;
}
async function lsYardLook(cell){
  worldOpen('#' + cell);
  await new Promise(r => setTimeout(r, 900));
  const b = document.querySelector('[data-view3d="1"]');
  if (b && !(typeof V3 !== 'undefined' && V3.on)) b.click();
}
function lsPlacesBind(P){
  const Q = P.places || (P.places = Object.assign({}, LS_PLACES));
  const root = lsRoot();
  root.querySelectorAll('[data-pl]').forEach(r => r.oninput = () => { Q[r.dataset.pl] = +r.value; r.nextElementSibling.textContent = r.value; lsChanged(); });
  const cu = $('#lsq-cult'); if (cu) cu.onchange = () => { Q.culture = cu.value; lsChanged(); };
  const go = $('#lsq-go'); if (go) go.onclick = async () => {
    if (!await needProject()) return;
    go.disabled = true; go.textContent = 'Proposing…';
    try {
      const r = await post('/api/land/places', {cells: LM.data.marks, amounts: {settlements: Q.settlements, dungeons: Q.dungeons, small: Q.small}, culture: Q.culture,
        seed: 1 + Math.floor(Math.random() * 99999)});
      // (the last proposal's places not yet built go: proposing again is a new roll)
      P.layers = P.layers.filter(L => !((L.p || {}).proposed && !(L.p || {}).built));
      for (const q of r.places || []){
        const id = String(Date.now()) + Math.floor(Math.random() * 1e6);
        if (q.kind === 'farm') P.layers.push({id, kind: 'farm', name: '', on: true, pts: q.outline,
          p: lsFresh(Object.assign({}, LS_DEFAULTS.farm, {culture: q.culture, proposed: true, place: 'farm'}))});
        else if (q.kind === 'label') P.layers.push({id, kind: 'label', name: q.name, on: true, pts: [[q.x, q.y]],
          p: Object.assign({}, LS_DEFAULTS.label, {what: q.what, name: q.name, culture: q.culture, proposed: true, place: 'name'})});
        else if (q.what) P.layers.push({id, kind: 'small', name: (q.label || q.what).replace(/^./, c => c.toUpperCase()), on: true, pts: [[q.x, q.y]],
          p: Object.assign({}, LS_DEFAULTS.small, {what: q.what, scene: q.scene, phi: q.phi, fit: q.fit || 0, culture: q.culture, proposed: true, place: q.what})});
        else if (q.kind === 'harbour') P.layers.push({id, kind: 'harbour', name: 'Harbour', on: true, pts: [[q.x, q.y]],
          p: Object.assign({}, LS_DEFAULTS.harbour, {scene: q.scene, phi: q.phi, fit: q.fit || 0, culture: q.culture, proposed: true})});
        else if (q.outline) P.layers.push({id, kind: 'town', name: q.name || '', on: true, pts: q.outline,
          p: lsFresh(Object.assign({}, LS_DEFAULTS.town, {culture: q.culture, proposed: true, place: q.kind, trade: q.trade || ''},
            q.name ? {name: q.name} : {}, q.density ? {density: q.density} : {}, q.counts ? {counts: q.counts} : {}))});
        else P.layers.push({id, kind: 'dungeon', name: q.name || '', on: true, pts: [[q.x, q.y]],
          p: Object.assign({}, LS_DEFAULTS.dungeon, {kit: q.kit, name: q.name || '', rz: q.rz || 0, proposed: true, place: q.kind})});
      }
      // (the roads the places grew along: proposed roads, as Propose roads makes them)
      for (const q of r.roads || []) P.layers.push({id: String(Date.now()) + Math.floor(Math.random() * 1e6), kind: 'road', name: `${q.from} – ${q.to}`.slice(0, 60), on: true,
        pts: q.pts, p: {culture: q.culture || '', proposed: true, bridges: q.bridges || []}});
      LM.sel = null;
      const n = (r.places || []).length, nr = (r.roads || []).length;
      toast(n ? `Proposed ${n} place${n === 1 ? '' : 's'}${nr ? ` and ${nr} road${nr === 1 ? '' : 's'}` : ''} for ${r.land_cells} cells of land. Move or remove them on the map, then Shape, then build for the towns and Build the places for the rest.`
              : 'No places proposed: too little land marked, or none it suits.');
    } catch (err){ toast(err.message, true); }
    lsChanged(true);
  };
  const rd = $('#lsq-roads'); if (rd) rd.onclick = async () => {
    if (!await needProject()) return;
    rd.disabled = true; rd.textContent = 'Finding the ways…';
    try {
      const r = await post('/api/land/roads', {cells: LM.data.marks, layers: P.layers.filter(L => L.kind === 'town' && L.on !== false)});
      // (proposing again is a new set: the last proposal's roads go, the ones drawn by hand stay)
      P.layers = P.layers.filter(L => !(L.kind === 'road' && (L.p || {}).proposed));
      for (const q of r.roads || []) P.layers.push({id: String(Date.now()) + Math.floor(Math.random() * 1e6), kind: 'road', name: `${q.from} – ${q.to}`.slice(0, 60), on: true,
        pts: q.pts, p: {culture: q.culture || '', proposed: true, bridges: q.bridges || []}});
      LM.sel = null;
      const n = (r.roads || []).length;
      const nb = (r.roads || []).reduce((a, q) => a + (q.bridges || []).length, 0);
      toast(n ? `Proposed ${n} road${n === 1 ? '' : 's'} between ${r.towns} towns${nb ? `, ${nb} bridge${nb === 1 ? '' : 's'} over the water` : ''}. Shape the ground lays the ones in the marked cells.`
              : (r.towns < 2 ? 'No roads: it needs two towns or more, drawn, proposed or the game\'s, near the marked cells.' : 'No roads: no way between the towns that stays off the water and the steepest ground.'));
    } catch (err){ toast(err.message, true); }
    lsChanged(true);
  };
  const bd = $('#lsq-build'); if (bd) bd.onclick = () => lsBuildDungeons(lsPlacesToBuild(P), bd);
  const ln = $('#lsn-name'); if (ln && P.layers[LM.sel] && P.layers[LM.sel].kind === 'label') ln.onchange = () => { const L = P.layers[LM.sel]; L.name = L.p.name = ln.value.trim().slice(0, 63); lsChanged(true); };
  const yg = $('#lsy-go'); if (yg) yg.onclick = async () => {
    yg.disabled = true; yg.textContent = 'Measuring…';
    try {
      LM.yard = await post('/api/land/yardstick', {cells: LM.data.marks, like: (P.terrain && P.terrain.like) || '',
        towns: P.layers.filter(L => L.kind === 'town' && L.on !== false).map(L => L.pts)});
    } catch (err){ toast(err.message, true); }
    renderWside();
  };
  lsRoot().querySelectorAll('[data-ylook]').forEach(b => b.onclick = () => lsYardLook(b.dataset.ylook));
  const rq = $('#lsq-rum'); if (rq) rq.onclick = async () => {
    if (!await needProject()) return;
    rq.disabled = true; rq.textContent = 'Writing…';
    try {
      const r = await post('/api/land/rumours', {cells: LM.data.marks, seed: 1 + Math.floor(Math.random() * 99999)});
      toast(r.places ? `${r.places} place${r.places === 1 ? '' : 's'} talked of in ${r.towns} town${r.towns === 1 ? '' : 's'}: ${r.lines} line${r.lines === 1 ? '' : 's'}${r.quests ? `, ${r.quests} quest${r.quests === 1 ? '' : 's'} (on the Quest Board)` : ''}. One Undo takes them back.`
                     : (r.dungeons ? `None of the ${r.dungeons} dungeons has a town of yours within reach to talk of it.` : 'No dungeons of yours in the marked cells: build the places first.'), !r.places);
    } catch (err){ toast(err.message, true); }
    lsChanged(true);
  };
  const fk = $('#lsq-folk'); if (fk) fk.onclick = async () => {
    if (!await needProject()) return;
    fk.disabled = true; fk.textContent = 'Bringing them in…';
    try {
      const on = P.layers.filter(L => L.on !== false);
      const r = await post('/api/land/folk', {cells: LM.data.marks, seed: 1 + Math.floor(Math.random() * 99999), culture: Q.culture,
        roads: on.filter(L => L.kind === 'road').map(L => L.pts), towns: on.filter(L => L.kind === 'town').map(L => L.pts),
        camps: on.filter(L => L.kind === 'small' && (L.p || {}).what === 'camp' && (L.p || {}).built).map(L => L.pts[0])});
      toast(r.people || r.creatures ? `${r.people} ${r.people === 1 ? 'person' : 'people'} by the roads and at the camps, ${r.creatures} creature${r.creatures === 1 ? '' : 's'}. One Undo takes them back.`
                                    : 'Nobody to bring: mark land with roads or camps, or land for the creatures.');
      await afterChange(); await lmReloadObjects();
    } catch (err){ toast(err.message, true); }
    lsChanged(true);
  };
  const sel = P.layers[LM.sel];
  if (sel && sel.kind === 'dungeon'){
    const k = $('#lsd-kit'); if (k) k.onchange = () => { sel.p.kit = k.value; lsChanged(true); };
    const nm = $('#lsd-name'); if (nm) nm.onchange = () => { sel.p.name = nm.value.trim(); sel.name = sel.p.name; lsChanged(true); };
    const sz = $('#lsd-size'); if (sz) sz.onchange = () => { sel.p.size = sz.value; lsChanged(); };
    const b1 = $('#lsd-build'); if (b1) b1.onclick = () => lsBuildDungeons([sel], b1);
  }
}
function lsRegionPassHtml(P){
  const T = P.terrain = Object.assign({}, LS_TERRAIN, P.terrain || {});
  if (!LM.handmade && !LM.handmadeAsk){
    LM.handmadeAsk = true;
    api('/api/land/handmade').then(r => { LM.handmade = r.regions || []; LM.clads = r.clads || []; if (T.on) renderWside(); }).catch(() => { LM.handmadeAsk = false; });
  }
  const sl = (key, lab, tip) => `<label title="${esc(tip)}">${lab} <input type="range" data-tr="${key}" min="0" max="2" step="0.1" value="${T[key]}"><span>${T[key]}</span></label>`;
  const TI = (LM.prevInfo || {}).terrain || {};
  const took = Object.entries(TI.like || {});
  const rk = [...new Set(Object.values(TI.rocks || {}))], pk = [...new Set(Object.values(TI.plants || {}).filter(Boolean))];
  const tookTxt = (took.length ? 'Taking after: ' + took.map(([r, l]) => r === l ? lsRegionName(r) : `${lsRegionName(r)} → ${lsRegionName(l)}`).join(', ') + '.' : '')
    + (rk.length && T.rocks && T.cliffs > 0 ? ` Rock from ${rk.map(lsRegionName).join(', ')}.` : '')
    + (pk.length && T.plants ? ` Plants from ${pk.map(lsRegionName).join(', ')}.` : '');
  return `<h3>Region pass${lsGuide('Region pass')}</h3><div class="lm-raise">
      <label class="msg" style="display:flex;gap:6px;align-items:center" title="The marked cells' land made as rough, as broken into ranges and as cut by valleys as a hand-made region's land, as it is: no shapes needed. Shape the ground runs it; up to ${'2,048'} cells at once, 400 at a time"><input type="checkbox" id="lst-on" ${T.on ? 'checked' : ''}> Like hand-made land</label>
      ${T.on ? `<label title="The hand-made region whose roughness and slopes the land takes on. Nearest: for each region, the hand-made one closest to it in relief (plains take after gentle land, mountains after mountains)">Like <select class="inp" id="lst-like"><option value="">nearest in relief</option>${(LM.handmade || []).map(r => `<option value="${esc(r)}" ${r === T.like ? 'selected' : ''}>${esc(lsRegionName(r))}</option>`).join('')}</select></label>
        ${sl('ranges', 'Ranges', 'Side crests and spurs between the long ridges, on land standing over its valleys (plains stay plains). 0: none')}
        ${sl('relief', 'Relief', 'Rolling ground and crags from 4,096 down to 256 across, until the land is as rough as the region it takes after. 0: none')}
        ${sl('valleys', 'Valleys', 'The rain carves valleys into the result: deep where much ground drains. 0: none')}
        ${sl('cliffs', 'Cliffs', 'Hard rock stepped into cliffs and ledges where the game has its steep ground: high over the valleys, mid-slope, where the land is rough, in the rock texture of such ground. As much as the region it takes after has. 0: none')}
        ${T.cliffs > 0 ? `<label class="msg" style="display:flex;gap:6px;align-items:center" title="Clad the steep ground in cliff pieces, faces, lips, feet and outcrops, as the game does (the land's own rocks stay and follow the ground)"><input type="checkbox" id="lst-rocks" ${T.rocks ? 'checked' : ''}> Rock the cliffs</label>
        ${T.rocks ? `<label title="Whose cliff pieces. Nearest: the region's own where the game clad its cliffs, else the region nearest in weather and on the map that did">Rock <select class="inp" id="lst-rockfrom"><option value="">nearest in weather</option>${(LM.clads || []).map(r => `<option value="${esc(r)}" ${r === T.rockfrom ? 'selected' : ''}>${esc(lsRegionName(r))}</option>`).join('')}</select></label>` : ''}` : ''}
        <label class="msg" style="display:flex;gap:6px;align-items:center" title="The land's own trees stood as the game's: few on steep ground, gathered into groves with a few more of their kind, fewer in the open between. Your own trees stay"><input type="checkbox" id="lst-trees" ${T.trees ? 'checked' : ''}> Trees in groves</label>
        <label class="msg" style="display:flex;gap:6px;align-items:center" title="Plants where the land has none of its own: those of the nearest region in weather and on the map that has, as its own land grows them, up to about the game's number"><input type="checkbox" id="lst-plants" ${T.plants ? 'checked' : ''}> Plants</label>
        <label class="msg" style="display:flex;gap:6px;align-items:center" title="Waterfalls where the streams drop over the new cliffs, as the game lays them: the fall scaled to the drop, a plunge pool dug at its foot, mist and its sound. Needs Tamriel_Data"><input type="checkbox" id="lst-falls" ${T.falls ? 'checked' : ''}> Waterfalls</label>
        <label class="msg" style="display:flex;gap:6px;align-items:center" title="Texture the land again by its new slopes (Dressing), blended over the region borders as the game blends them. Off: the textures stay as they are but for the cliffs'"><input type="checkbox" id="lst-paint" ${T.paint ? 'checked' : ''}> Texture it too</label>
        ${tookTxt ? `<div class="msg" style="font-size:11.5px">${esc(tookTxt)}</div>` : ''}` : ''}
    </div>`;
}
function lsPassesHtml(P, shapes){
  if (shapes === undefined) shapes = 1;
  const A = P.passes = Object.assign({}, LS_PASSES, P.passes || {}), D = P.dress = Object.assign({}, LS_DRESS, P.dress || {});
  const info = LM.prevInfo || {};
  const chk = (id, on, text, tip) => `<label class="msg" style="display:flex;gap:6px;align-items:center" title="${esc(tip)}"><input type="checkbox" id="${id}" ${on ? 'checked' : ''}> <span style="flex:1;min-width:0;text-align:left">${text}</span></label>`;
  const sl = (key, grp, lab, mn, mx, st, v, tip) => `<label title="${esc(tip)}">${lab} <input type="range" data-${grp}="${key}" min="${mn}" max="${mx}" step="${st}" value="${v}"><span>${v}</span></label>`;
  const R = P.protect = Object.assign({hold: true, margin: 512, fresh: true}, P.protect || {});
  return `<h3>Protection${lsGuide('Protection')}</h3><div class="lm-raise">
      ${chk('lsr-fresh', R.fresh, 'Start from the land under my mod', 'Each Shape starts from the marked cells’ land as it is without your mod (the game’s, or the sea bed), so a moved or removed shape leaves nothing behind. Off: it starts from your land as it is now, keeping what you sculpted by hand')}
      ${chk('lsr-hold', R.hold, `Hold the ground under buildings, ruins and doors <span id="ls-held-t">${info.held != null ? '(' + info.held + ' here, outlined on the map)' : ''}</span>`, 'Under each building piece, ruin wall and door the ground stays exactly as it is, fading back to the plan over the margin round it, so nothing is buried or left standing in the air')}
      ${R.hold ? sl('margin', 'pr', 'Margin', 128, 2048, 64, R.margin, 'How far round each held piece the ground fades back to the plan') : ''}
      <div class="msg" style="font-size:11.5px">Rocks, trees, plants, crates, people and creatures move up or down with the ground instead, and walking paths too.</div>
    </div>
    ${shapes ? `<h3>Natural passes${lsGuide('Natural passes')}</h3><div class="lm-raise">
      ${chk('lsp-detail', A.detail, 'Match the region\'s roughness', 'Rolling detail added (or the ground softened) until the plan\'s land is as rough as the region\'s own, measured 1024 and 128 units apart by the land survey')}
      ${sl('valleys', 'pa', 'Valleys', 0, 2, 0.1, A.valleys, 'Rain carves branching valleys: deep where much ground drains, faint on small slopes (0: none)')}
      ${sl('rock', 'pa', 'Rock layers', 0, 1, 0.05, A.rock, 'Bands of hard and soft rock: the hard stand as cliffs with ledges on top, the soft wear back to scree (0: none)')}
      ${A.rock > 0 ? sl('rthick', 'pa', 'Layer height', 128, 2048, 64, A.rthick, 'How tall each band of rock is') + sl('rshare', 'pa', 'Hard rock', 0.1, 0.9, 0.05, A.rshare, 'How many of the bands are hard')
        + sl('rdip', 'pa', 'Tilt', 0, 45, 1, A.rdip, 'How steeply the layers dip (degrees): tilted layers make one-sided ridges') + (A.rdip > 0 ? sl('rdir', 'pa', 'Tilt way', 0, 359, 1, A.rdir, 'Which way the layers dip (degrees from east)') : '')
        + (lsHereRegions().length > 1 || A.ronly ? `<label title="Rock layers only in one region of the marked cells, fading out at its border" style="white-space:nowrap">Only in ${lsRegionSel('lsp-ronly', A.ronly || '', 'everywhere', lsHereRegions())}</label>` : '') : ''}
      ${sl('gullies', 'pa', 'Rain gullies', 0, 2, 0.1, A.gullies, 'Raindrops run down the slopes, cut gullies and leave fans at their feet (0: none). Light-handed: the game\'s land is not heavily worn')}
      ${chk('lsp-settle', A.settle, `Settle the steepest slopes <span id="ls-settle-t" title="${esc(lsSettleTip(info.settle_angle))}">${lsSettleText(info.settle_angle)}</span>`, 'Ground slides down where it is steeper than 99% of the region\'s own land, so the plan keeps no more cliff than the region has')}
      ${chk('lsp-terr', A.terraces, 'Terraces', 'Steps up the slopes, the Ashlands and Molag Amur look')}
      ${A.terraces ? sl('tstep', 'pa', 'Step height', 64, 1024, 32, A.tstep, 'How high each step is') + sl('tsharp', 'pa', 'Sharpness', 0, 1, 0.05, A.tsharp, '0 soft benches, 1 hard steps') + sl('tslope', 'pa', 'From slopes of', 5, 45, 1, A.tslope, 'Only slopes steeper than this (degrees) get steps') : ''}
    </div>` : ''}
    ${shapes || (P.terrain || {}).paint ? `<h3>Dressing${lsGuide('Dressing')}</h3><div class="lm-raise">
      ${lsDressPick(D)}
      ${D.region ? chk('lsd-assign', D.assign, 'Put the cells in this region (its weather, sounds, creatures)', 'The marked cells join the region in the same Undo') : ''}
      ${chk('lsd-tints', D.tints, 'Tint each texture as the game does', 'landshade "By texture": the colour the region\'s land gives each texture')}
      ${chk('lsd-seams', D.seams, 'Darken where textures meet', 'landshade "Where textures meet": the join tinted as the game tints it at that pair')}
      ${chk('lsd-hollows', D.hollows, 'Darker hollows, lighter crests', 'As the region\'s land is: the land survey measured hollows 6 to 14% darker than level ground, crests 1 to 5% lighter')}
      ${sl('shade', 'dr', 'Shading', 0, 1, 0.05, D.shade, 'How strongly the tints, seams and hollows are laid on')}
      ${sl('rocks', 'dr', 'Rocks', 0, 2, 0.1, D.rocks, 'The region\'s rocks on the new slopes and cliffs, as thickly as the game sets them on such ground (1), fewer or more (0: none). Set when you shape')}
      ${D.rocks > 0 ? chk('lsd-clad', D.clad, 'Rock the steep ground', 'A ridge, valley, river or plateau\'s steep ground clad in the region\'s cliff pieces the way the game\'s gorges and hilltops are: big faces, smaller rocks on the lip and at the foot, banks along the water, outcrops on knolls; every piece sunk until no bottom edge shows. Off: the plain rock scatter alone') : ''}
      ${sl('flow', 'dr', 'Stream beds', 0, 2, 0.1, D.flow, 'Where much water runs, the region\'s water\'s-edge textures (mud, wet ground), so streams show. The Bitter Coast\'s own land does this; most regions\' don\'t, so 0 (off) is the game\'s way there. Higher: smaller streams too')}
      ${chk('lsd-tview', LM.texView, 'Show the textures in the preview', 'Each texture its own colour over the preview, as the plan would lay them')}
      <div class="ls-tex" id="ls-texlegend">${lsLegend()}</div>
      ${lsTexButton()}
    </div>` : ''}`;
}
// (the region the textures come from and how many a cell: shared by Dressing and "Texture the land")
function lsDressPick(D){
  const regs = (typeof REG !== 'undefined' && REG.data) ? REG.data.regions : [];
  return `<label title="The region whose land the plan takes after: its textures, its tints and shading, its roughness and slopes">Like <select class="inp" id="lsd-region"><option value="">the nearest region</option>${regs.map(r => `<option value="${esc(r.id.toLowerCase())}" ${r.id.toLowerCase() === D.region ? 'selected' : ''}>${esc(r.name)}</option>`).join('')}</select></label>
      <label title="The shores: as the region lays them (West Gash's are rock), or sandy beaches or rocky shores whatever the region, at the water's edge and the flat ground just over it">Shores <select class="inp" id="lsd-shore">${[['', "as the region's"], ['sand', 'sandy'], ['rock', 'rocky']].map(([v, t]) => `<option value="${v}" ${(D.shore || '') === v ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
      <label title="How many textures a cell: as the region's own cells have (the land survey's median), or fewer or more">Textures <select class="inp" id="lsd-var">${[[-1, 'as many a cell as the region'], [0.4, 'fewer'], [1, 'more'], [2, 'many']].map(([v, t]) => `<option value="${v}" ${+D.variety === v ? 'selected' : ''}>${t}</option>`).join('')}</select></label>`;
}
// Texture only: the marked cells' land textured by its slopes, heights and shores, as it is (landshapes.texture_only)
function lsTexButton(){
  const n = LM.data ? LM.data.marks.length : 0;
  return `<div class="actions"><button class="btn sm" id="ls-texonly" ${n ? '' : 'disabled'} title="Texture the marked cells the way the region's land is textured at each slope, height and shore, with these settings. Heights stay; roads, paving and the ground under buildings stay. One Undo">🎨 Texture only</button></div>`;
}
// with no shapes drawn: the texturing on its own
function lsTexHtml(P){
  P.passes = Object.assign({}, LS_PASSES, P.passes || {});
  const D = P.dress = Object.assign({}, LS_DRESS, P.dress || {});
  P.protect = Object.assign({hold: true, margin: 512}, P.protect || {});
  return `<h3>Texture the land${lsGuide('Texture only')}</h3><div class="lm-raise">
      ${lsDressPick(D)}
      <label title="Where much water runs, the region's water's-edge textures (mud, wet ground), so streams show. The Bitter Coast's own land does this; most regions' don't (0: off). Show where water runs to see them">Stream beds <input type="range" data-dr="flow" min="0" max="2" step="0.1" value="${D.flow}"><span>${D.flow}</span></label>
      <label class="msg" style="display:flex;gap:6px;align-items:center" title="Under each building piece, ruin wall and door the ground keeps its texture"><input type="checkbox" id="lsr-hold" ${P.protect.hold ? 'checked' : ''}> Keep the ground under buildings</label>
      ${lsTexButton()}
      <div class="msg" style="font-size:11.5px">Heights stay as they are; roads and paving too.</div></div>`;
}
async function lsTexOnly(btn){
  if (!await needProject()) return;
  btn.disabled = true; btn.textContent = `Texturing ${LM.data.marks.length} cell${LM.data.marks.length === 1 ? '' : 's'}…`;
  await lmKeepBefore('texturing');
  try {
    const r = await post('/api/land/texture', {cells: LM.data.marks, plan: LM.plan});
    toast(`Textured ${r.cells} cell${r.cells === 1 ? '' : 's'}${r.textures_a_cell ? `, about ${r.textures_a_cell} textures a cell` : ''}${r.kept ? `; ${r.kept} patches of road or under buildings kept` : ''}. One Undo takes it back.`);
    W.lands = {}; if (typeof v3LandsReload === 'function') v3LandsReload();
    await afterChange();
    await loadAround(Math.floor(W.cam.x / CELL), Math.floor(W.cam.y / CELL));
    lmFlowSoon(); drawMap(); renderWside();
  } catch (err){ toast(err.message, true); btn.disabled = false; btn.textContent = '🎨 Texture only'; }
}
// a "?" beside a section, opening the land guide there (help.js)
function lsGuide(section){ return typeof guideLink === 'function' ? guideLink('shaping-the-land.md', section, 'How this works (the land guide)') : ''; }
// the cells a shape reaches (with its widths and the plan's edge fade): for "Mark its cells", and to say when a shape
// lies outside the marked cells and so changes nothing (the user drew a river with nothing marked, 2026-10-28)
function lsShapeCells(L){
  const C = 8192, p = Object.assign({}, LS_DEFAULTS[L.kind], L.p || {}), fade = (LM.plan && LM.plan.fade) || 1024;
  const reach = {coast: Math.min(1536, p.width * 0.25) + 1024, plateau: 1024, ridge: p.width * 1.5, river: p.width + p.banks,
    valley: p.width, lake: p.width + 512, stamp: p.radius, spring: 2 * C, area: 0, farm: 0, orchard: 0}[L.kind] + fade;
  const pts = L.pts, closed = !!LS_KINDS[L.kind].closed, half = C * Math.SQRT2 / 2;
  const segDist = (x, y, a, b) => {
    const dx = b[0] - a[0], dy = b[1] - a[1], l2 = dx * dx + dy * dy;
    const t = l2 ? Math.max(0, Math.min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / l2)) : 0;
    return Math.hypot(x - a[0] - t * dx, y - a[1] - t * dy);
  };
  const inside = (x, y) => { let c = false; for (let i = 0, j = pts.length - 1; i < pts.length; j = i++){ const [ax, ay] = pts[i], [bx, by] = pts[j]; if ((ay > y) !== (by > y) && x < ax + (y - ay) * (bx - ax) / (by - ay)) c = !c; } return c; };
  const xs = pts.map(q => q[0]), ys = pts.map(q => q[1]);
  const gx0 = Math.floor((Math.min(...xs) - reach) / C), gx1 = Math.floor((Math.max(...xs) + reach) / C);
  const gy0 = Math.floor((Math.min(...ys) - reach) / C), gy1 = Math.floor((Math.max(...ys) + reach) / C);
  const out = [];
  for (let gx = gx0; gx <= gx1; gx++) for (let gy = gy0; gy <= gy1; gy++){
    const cx = (gx + 0.5) * C, cy = (gy + 0.5) * C;
    let d = Infinity;
    if (pts.length === 1) d = Math.hypot(cx - pts[0][0], cy - pts[0][1]);
    else for (let i = 0; i < pts.length - (closed ? 0 : 1); i++) d = Math.min(d, segDist(cx, cy, pts[i], pts[(i + 1) % pts.length]));
    if (d - half <= reach || (closed && inside(cx, cy))) out.push(gx + ',' + gy);
  }
  return out;
}
// regions: a select of them (ids, as the land survey keys them), and the ones the marked cells are in
function lsRegionName(id){
  const r = ((typeof REG !== 'undefined' && REG.data) ? REG.data.regions : []).find(r => r.id.toLowerCase() === id);
  return r ? r.name : id;
}
function lsHereRegions(){ return (LM.prevInfo && LM.prevInfo.marked_regions) || []; }
function lsRegionSel(id, cur, none, only){
  const all = ((typeof REG !== 'undefined' && REG.data) ? REG.data.regions : []).map(r => r.id.toLowerCase());
  const ids = only || all;
  if (cur && !ids.includes(cur)) ids.unshift(cur);
  return `<select class="inp" id="${id}"><option value="">${none}</option>${ids.map(r => `<option value="${esc(r)}" ${r === cur ? 'selected' : ''}>${esc(lsRegionName(r))}</option>`).join('')}</select>`;
}
function lsSettleText(a){
  if (a == null || a === '') return 'to the region\'s';
  if (typeof a === 'number') return `(over ${a}°, the region's steepest)`;
  const v = Object.values(a);
  return `(over ${Math.min(...v)}–${Math.max(...v)}°, each region's own)`;
}
function lsSettleTip(a){
  return a && typeof a === 'object' ? Object.entries(a).map(([r, v]) => `${lsRegionName(r)}: ${v}°`).join('\n') : '';
}
function lsLegend(){
  if (!LM.prevTex) return '';
  return Object.entries(LM.prevTex).sort((a, b) => b[1] - a[1]).slice(0, 12).map(([t, n]) =>
    `<span title="${esc(t)}: in ${n} cell${n === 1 ? '' : 's'}"><i style="background:${lsTexColor(t)}"></i>${esc(t.replace(/^.*[\\/]/, '').replace(/\.(tga|dds|bmp)$/, ''))}</span>`).join('');
}
// the preview's pictures: the land hill-shaded, and with the texture view, each patch in its texture's colour over it
function lsBuildPrev(){
  const R = LM.prevData; if (!R){ LM.prev = null; return; }
  const imgs = {};
  for (const [k, c] of Object.entries(R.cells)){
    const base = landImage(c);
    if (!LM.texView || !c.t){ imgs[k] = base; continue; }
    const cv2 = document.createElement('canvas'); cv2.width = cv2.height = 64;
    const g = cv2.getContext('2d'); g.imageSmoothingEnabled = true; g.drawImage(base, 0, 0, 64, 64);
    g.globalAlpha = 0.6;
    for (let p = 0; p < 256; p++){ g.fillStyle = lsTexColor(c.t[p]); g.fillRect((p % 16) * 4, (15 - Math.floor(p / 16)) * 4, 4, 4); }
    imgs[k] = cv2;
  }
  LM.prev = imgs;
}
function lsTexColor(t){
  let h = 0; for (const c of t) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return `hsl(${h % 360},${45 + (h >> 9) % 30}%,${42 + (h >> 17) % 20}%)`;
}
// the Land panel's own box: its bindings stay in it (page-wide, "[data-add]" took the Build window's + Room menu and
// "[data-pa]" Populate's sliders: a room picked began a land shape of a kind there is none of, the user 2026-10-31)
function lsRoot(){
  const ub = $('#ls-undo');
  return (ub && (ub.closest('.pbody') || ub.parentElement.parentElement)) || document;
}
function lsPassesBind(P){
  const A = P.passes, D = P.dress, R = P.protect;
  const on = (id, f) => { const el = $('#' + id); if (el) el.onchange = () => f(el); };
  on('lsr-hold', el => { R.hold = el.checked; lsChanged(true); });
  on('lsr-fresh', el => { R.fresh = el.checked; lsChanged(true); });
  lsRoot().querySelectorAll('[data-pr]').forEach(r => r.oninput = () => { R[r.dataset.pr] = +r.value; r.nextElementSibling.textContent = r.value; lsChanged(); });
  on('lsp-detail', el => { A.detail = el.checked; lsChanged(); });
  on('lsp-settle', el => { A.settle = el.checked; lsChanged(); });
  on('lsp-terr', el => { A.terraces = el.checked; lsChanged(true); });
  on('lsp-ronly', el => { A.ronly = el.value; lsChanged(); });
  // (Rock layers and Tilt show their own sliders when they go from 0 or back to it: drawn again then)
  lsRoot().querySelectorAll('[data-pa]').forEach(r => r.oninput = () => {
    const was = A[r.dataset.pa]; A[r.dataset.pa] = +r.value; r.nextElementSibling.textContent = r.value;
    lsChanged(['rock', 'rdip'].includes(r.dataset.pa) && (was > 0) !== (+r.value > 0));
  });
  lsRoot().querySelectorAll('[data-dr]').forEach(r => r.oninput = () => { D[r.dataset.dr] = +r.value; r.nextElementSibling.textContent = r.value; lsChanged(); });
  on('lsd-region', el => { D.region = el.value; if (!el.value) D.assign = false; lsChanged(true); });
  on('lsd-assign', el => { D.assign = el.checked; lsChanged(); });
  on('lsd-var', el => { D.variety = +el.value; lsChanged(); });
  on('lsd-shore', el => { D.shore = el.value; lsChanged(); });
  on('lsd-tints', el => { D.tints = el.checked; lsChanged(); });
  on('lsd-seams', el => { D.seams = el.checked; lsChanged(); });
  on('lsd-hollows', el => { D.hollows = el.checked; lsChanged(); });
  on('lsd-clad', el => { D.clad = el.checked; lsChanged(); });
  on('lsd-tview', el => { LM.texView = el.checked; lsBuildPrev(); drawMap(); });
  if (typeof regLoad === 'function' && !REG.data) regLoad().then(() => renderWside()).catch(() => {});
}
function lsCss(){
  if ($('#ls-css')) return;
  const c = document.createElement('style'); c.id = 'ls-css';
  c.textContent = `.ls-add{display:flex;flex-wrap:wrap;gap:4px}.ls-list{display:flex;flex-direction:column;gap:2px;margin-top:6px}
    .ls-row{display:flex;gap:6px;align-items:center;padding:2px 6px;border-radius:5px;cursor:pointer;font-size:12.5px;color:var(--text)}
    .ls-row.on{background:color-mix(in srgb,var(--accent,#c9a227) 20%,transparent)}.ls-row .ls-n{flex:1}.ls-row .xbtn{padding:0 4px}
    .ls-tex{display:flex;flex-wrap:wrap;gap:3px 9px;font-size:11px;color:var(--muted)}.ls-tex span{display:flex;gap:4px;align-items:center}
    .ls-tex i{display:inline-block;width:10px;height:10px;border-radius:2px}
    .ls-tch{display:flex;flex-direction:column;gap:1px;max-height:260px;overflow:auto;margin:4px 0}
    .ls-tch label{display:flex;align-items:center;gap:6px;font-size:12px;padding:1px 2px;border-radius:4px}
    .ls-tch label.off{opacity:.45}.ls-tch label>span{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .ls-tch img{width:32px;height:32px;flex:none}.ls-tch b{font-weight:normal;color:var(--muted);min-width:14px;text-align:right}
    .ls-pin{position:sticky;top:-14px;z-index:5;display:flex;align-items:center;justify-content:space-between;gap:8px;
      margin:-14px -14px 8px;padding:8px 14px;background:var(--panel);border-bottom:1px solid var(--line)}
    .ls-pin .msg{font-size:11.5px;line-height:1.35}.ls-pin .btn{flex:none}`;
  document.head.appendChild(c);
}
function lsBind(){
  lsCss();
  const P = LM.plan; if (!P) return;
  // (its own buttons only: bound page-wide, "[data-add]" took the Build window's + Room menu too, and a room picked
  // there began a land shape of a kind there is none of, PIN2/the user 2026-10-31)
  const root = lsRoot();
  lsTownBind();
  lsFieldBind();
  lsPlacesBind(P);
  if (typeof csBind === 'function') csBind();
  const zs = $('#ls-zone'); if (zs){ const S_ = P.layers[LM.sel]; zs.onchange = () => { S_.p.zone = zs.value; lsChanged(true); }; }
  if (P.layers.some(L => L.kind === 'town' && !(LM.towns && LM.towns[L.id]))) lsTownsSoon();
  root.querySelectorAll('[data-add]').forEach(b => b.onclick = () => lsStart(b.dataset.add));
  root.querySelectorAll('.ls-row').forEach(r => r.onclick = e => { if (e.target.closest('button,input')) return; LM.sel = +r.dataset.i; renderWside(); drawMap(); });
  root.querySelectorAll('[data-on]').forEach(c => c.onchange = () => { P.layers[+c.dataset.on].on = c.checked; lsChanged(); });
  root.querySelectorAll('[data-up]').forEach(b => b.onclick = () => lsMove(+b.dataset.up, -1));
  root.querySelectorAll('[data-dn]').forEach(b => b.onclick = () => lsMove(+b.dataset.dn, 1));
  root.querySelectorAll('[data-del]').forEach(b => b.onclick = () => { P.layers.splice(+b.dataset.del, 1); LM.sel = null; lsChanged(true); });
  root.querySelectorAll('[data-dup]').forEach(b => b.onclick = () => {
    // (a copy a quarter of a cell to the east, picked, to drag where it goes)
    const L0 = P.layers[+b.dataset.dup], L = JSON.parse(JSON.stringify(L0));
    L.id = String(Date.now()); L.pts = L.pts.map(p => [p[0] + 2048, p[1]]);
    P.layers.splice(+b.dataset.dup + 1, 0, L); LM.sel = +b.dataset.dup + 1; lsChanged(true);
  });
  const ps = $('#ls-preset'); if (ps) ps.onchange = () => { const v = ps.value; ps.value = ''; if (v) lsPreset(v); };
  const un = $('#ls-undo'); if (un) un.onclick = () => lsHistGo(true);
  const re = $('#ls-redo'); if (re) re.onclick = () => lsHistGo(false);
  const sel = P.layers[LM.sel];
  root.querySelectorAll('[data-p]').forEach(r => r.oninput = () => { sel.p[r.dataset.p] = +r.value; r.nextElementSibling.textContent = r.value; lsChanged(); });
  root.querySelectorAll('[data-g]').forEach(r => r.oninput = () => { P[r.dataset.g] = +r.value; r.nextElementSibling.textContent = r.value; lsChanged(); });
  root.querySelectorAll('[data-src]').forEach(r => r.onchange = () => { sel.p.src = sel.p.src || [0, 0, 0, 0]; sel.p.src[+r.dataset.src] = +r.value; lsChanged(); });
  const sh = $('#ls-shape'); if (sh) sh.onchange = () => { sel.p.shape = sh.value; if (sh.value === 'game'){ sel.p.height = 0; } lsChanged(true); };
  const here = $('#ls-src-here'); if (here) here.onclick = () => { const i = W.info || {}; sel.p.src = [i.gx - 1, i.gy - 1, i.gx + 1, i.gy + 1]; lsChanged(true); };
  const cs = $('#ls-cside'); if (cs) cs.onchange = () => { sel.p.side = +cs.value; lsChanged(); };
  const cp = $('#ls-cpick'); if (cp) cp.onchange = () => { sel.p.pick = cp.checked ? 1 : 0; lsChanged(); };
  const cr = $('#ls-craise'); if (cr) cr.onchange = () => { sel.p.raise = cr.checked ? 1 : 0; lsChanged(); };
  const cc = $('#ls-cclad'); if (cc) cc.onchange = () => { sel.p.clad = cc.checked ? 1 : 0; lsChanged(); };
  const cl = $('#ls-clay'); if (cl) cl.onclick = () => lsLayCliff(sel, cl);
  const cy = $('#ls-canyon'); if (cy) cy.onchange = () => { sel.p.canyon = cy.checked ? 1 : 0; lsChanged(); };
  const se = $('#ls-sea'); if (se) se.onchange = () => { sel.p.sea = se.checked ? 1 : 0; lsChanged(); };
  const mi = $('#ls-markit'); if (mi) mi.onclick = async e => {
    if (!await needProject()) return;
    const all = lsShapeCells(sel).filter(k => !LM.data.marked.has(k));
    // (settled cells, towns, only with Shift, as when marking by hand)
    const town = all.filter(k => { const c = lmCell(k); return c && c[0] === 'settled'; });
    const add = e.shiftKey ? all : all.filter(k => !town.includes(k));
    try {
      await lmMarksPost({add});
      toast(`Marked ${add.length} cell${add.length === 1 ? '' : 's'}${town.length && !e.shiftKey ? `; ${town.length} settled left out (Shift+click to mark them too)` : ''}.`);
    } catch (err){ toast(err.message, true); }
    renderWside(); lsPreviewSoon(); drawMap();
  };
  const on1 = $('#ls-only'); if (on1) on1.onchange = () => { sel.only = on1.value ? [on1.value] : []; lsChanged(); };
  const lk = $('#ls-like'); if (lk) lk.onchange = () => { sel.like = lk.value; lsChanged(); };
  const po = $('#ls-ponly'); if (po) po.onchange = () => { P.only = po.value ? [po.value] : []; lsChanged(); };
  const pa = $('#ls-paint'); if (pa) pa.onchange = () => { P.paint = pa.checked; lsChanged(); };
  const pv = $('#ls-prev'); if (pv) pv.onchange = () => { LM.prevOn = pv.checked; if (pv.checked) lsPreviewSoon(); drawMap(); };
  const sd = $('#ls-seed'); if (sd) sd.onclick = () => { P.seed = (P.seed || 1) + 1; lsChanged(); };
  const ap = $('#ls-apply'); if (ap) ap.onclick = () => lsApply(ap);
  const at = $('#ls-apply-top'); if (at) at.onclick = () => lsDoAll(at);
  const to = $('#ls-texonly'); if (to) to.onclick = () => lsTexOnly(to);
  // (all the shapes off the map: a plan isn't in Undo, so it asks first)
  // (all the shapes off the map; ↶ brings them back)
  const ca = $('#ls-clearall'); if (ca) ca.onclick = () => {
    const n = P.layers.length;
    P.layers = []; LM.sel = null; LM.prev = null; LM.prevData = null; LM.prevInfo = {}; lsChanged(true);
    toast(`Took ${n} shape${n === 1 ? '' : 's'} off the map. ↶ (by Shapes) brings them back.`);
  };
  if (P.passes && P.dress) lsPassesBind(P);
  // (the region pass)
  const T = P.terrain || (P.terrain = Object.assign({}, LS_TERRAIN));
  const ton = $('#lst-on'); if (ton) ton.onchange = () => { T.on = ton.checked; lsChanged(true); };
  const tlk = $('#lst-like'); if (tlk) tlk.onchange = () => { T.like = tlk.value; lsChanged(); };
  const tpa = $('#lst-paint'); if (tpa) tpa.onchange = () => { T.paint = tpa.checked; lsChanged(true); };
  const tro = $('#lst-rocks'); if (tro) tro.onchange = () => { T.rocks = tro.checked; lsChanged(true); };
  const ttr = $('#lst-trees'); if (ttr) ttr.onchange = () => { T.trees = ttr.checked; lsChanged(); };
  const tpl = $('#lst-plants'); if (tpl) tpl.onchange = () => { T.plants = tpl.checked; lsChanged(); };
  const tfa = $('#lst-falls'); if (tfa) tfa.onchange = () => { T.falls = tfa.checked; lsChanged(); };
  const trf = $('#lst-rockfrom'); if (trf) trf.onchange = () => { T.rockfrom = trf.value; lsChanged(); };
  root.querySelectorAll('[data-tr]').forEach(r => r.oninput = () => {
    const was = T[r.dataset.tr]; T[r.dataset.tr] = +r.value; r.nextElementSibling.textContent = r.value;
    // (Cliffs to or from 0 shows or hides Rock the cliffs)
    lsChanged(r.dataset.tr === 'cliffs' && (!was) !== (!T.cliffs));
  });
}
function lsMove(i, d){
  const P = LM.plan, j = i + d; if (j < 0 || j >= P.layers.length) return;
  [P.layers[i], P.layers[j]] = [P.layers[j], P.layers[i]]; LM.sel = j; lsChanged(true);
}
// a change: saved into the project and previewed, a moment after the last one
function lsChanged(rerender){
  if (!LM.histSkip){ lsHistNote(); LM.editAt = Date.now(); }
  // (a change to the plan shows its preview again: after Shape them the map showed the land as it was, and every edit
  // after, a merged point or a removed shape, seemed to do nothing, PIN2 2026-10-29)
  if (LM.prevOn === false){ LM.prevOn = true; const pv = $('#ls-prev'); if (pv) pv.checked = true; }
  if (rerender) renderWside();
  clearTimeout(LM.saveT);
  // (the server's cleaned settings taken back only when nothing changed meanwhile: a second change made while the
  // first was saving was put back by its answer, a town's Streets reset as its Which buildings saved, 2026-11-01)
  const n = LM.planN = (LM.planN || 0) + 1;
  LM.saveT = setTimeout(async () => { try { const r = await post('/api/land/plan', {plan: LM.plan}); if (n === LM.planN) LM.plan.layers.forEach((L, i) => { L.p = r.layers[i] ? r.layers[i].p : L.p; }); } catch (e){ toast(e.message, true); } lsAutoMark(); }, 500);
  lsPreviewSoon();
  lmFlowSoon();                                       // (the water follows the plan's land, and Stream beds' brightness)
  lsTownsSoon();
  if (typeof csSoon === 'function') csSoon();
  drawMap();
}

// ---------- farms and orchards (storydress.lay_field): an outline laid as fields of the region's own crop in the
// culture's farm fence, or as a loose grid of its fruit tree, the way the game's farms and orchards are; the outline's
// longest edge is the gate side. Make it lays it as one Undo; the card remembers what it laid (LM.fields, by shape id)
function lsLongEdge(pts){
  if (!pts || pts.length < 2) return null;
  let best = null;
  for (let k = 0; k < pts.length; k++){
    const a = pts[k], b = pts[(k + 1) % pts.length], L = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (!best || L > best[0]) best = [L, a, b];
  }
  return [best[1], best[2]];
}
function lsFieldKey(L){ return JSON.stringify([L.pts, (L.p || {}).culture || '', (L.p || {}).seed || 1]); }
function lsFieldHash(s){ let h = 0; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0; return (h >>> 0).toString(36); }
// (what Make it laid, kept in the plan as p.built 'things/plants/culture/hash': built while the outline, Like and seed
// are as they were; a change to any of them offers Make it again)
function lsFieldBuilt(L){
  const b = String((L.p || {}).built || '').split('/');
  if (b.length < 4 || b[b.length - 1] !== lsFieldHash(lsFieldKey(L))) return null;
  return {things: +b[0] || 0, plants: +b[1] || 0, culture: b.slice(2, -1).join('/')};
}
function lsFieldHtml(sel){
  const p = sel.p || (sel.p = {}), K = LS_KINDS[sel.kind], farm = sel.kind === 'farm';
  const F = (LM.fields = LM.fields || {})[sel.id] || (LM.fields[sel.id] = {});
  const cs = (LM.cultures || []).filter(c => !c.own);
  if (!LM.cultures && !LM.culturesAsked) lsCultures().then(c => { if (c && PNL.isShown('world', 'land')) renderWside(); });
  if (!p.culture) lsFieldNear(sel, F);
  const B = lsFieldBuilt(sel), built = !!B;
  const near = !p.culture && F.near ? ' (' + esc(F.near) + ')' : '';
  return `<label title="${farm ? 'Whose farm fence, and whose crop where the region grows none of its own. Blank: the nearest game town\'s' : 'Whose orchards it is planted like where the region grows no fruit tree of its own. Blank: the nearest game town\'s'}">Like <select class="inp" id="ls-fcult"><option value="">the nearest town's${near}</option>${cs.map(c => `<option value="${esc(c.id)}" ${p.culture === c.id ? 'selected' : ''} title="${esc((c.examples || []).join(', '))}">${esc(c.id)}</option>`).join('')}</select></label>
    <label title="The same outline laid another way"><span style="white-space:nowrap">Seed <input class="inp" id="ls-fseed" type="number" min="1" max="999999" value="${p.seed || 1}" style="width:76px"> <button class="btn sm" id="ls-freroll" title="Another seed">🎲</button></span></label>
    <div class="actions"><button class="btn sm primary" id="ls-fmake" ${built ? 'disabled title="Built. Change the outline, Like or the seed to lay it anew; Undo takes it back"' : `title="${farm ? 'Fields of the region\'s own crop at the game\'s spacing, the culture\'s farm fence round them, the gate in the longest side' : 'A loose grid of the region\'s fruit tree at the game\'s spacing'}. One Undo takes it back"`}>${built ? '✓ Built' : K.icon + ' Make it'}</button>${lsGuide('Towns')}</div>
    ${built ? `<div class="msg" style="font-size:11.5px">${B.plants} ${farm ? 'plants' : 'trees'}${B.things > B.plants ? `, ${B.things - B.plants} fence pieces` : ''}${B.culture ? ' · ' + esc(B.culture) : ''}</div>` : ''}`;
}
// (which culture a blank Like means here: the nearest game town's, asked once per outline. While the towns are still
// being learnt the answer is blank: asked again at a render half a minute later, never by a render of its own)
async function lsFieldNear(L, F){
  const key = JSON.stringify(L.pts);
  if (F.nearKey === key && (F.near || Date.now() - (F.nearAt || 0) < 30000)) return;
  F.nearKey = key; F.nearAt = Date.now();
  try {
    const r = await post('/api/land/field', {pts: L.pts, look: true});
    if (F.nearKey !== key) return;
    F.near = r.culture || '';
    if (F.near && PNL.isShown('world', 'land')) renderWside();
  } catch (e){ F.near = ''; }
}
function lsFieldBind(){
  const P = LM.plan, sel = P && P.layers[LM.sel]; if (!sel || !lsIsField(sel.kind)) return;
  const c = $('#ls-fcult'); if (c) c.onchange = () => { sel.p.culture = c.value; lsChanged(true); };
  const s = $('#ls-fseed'); if (s) s.onchange = () => { sel.p.seed = Math.max(1, Math.round(+s.value) || 1); lsChanged(true); };
  const r = $('#ls-freroll'); if (r) r.onclick = () => { sel.p.seed = ((sel.p.seed || 1) % 100000) + 1 + Math.floor(Math.random() * 1000); lsChanged(true); };
  const mk = $('#ls-fmake'); if (mk) mk.onclick = () => lsLayField(sel, mk);
}
async function lsLayField(L, btn){
  if (!await needProject()) return;
  const p = L.p || (L.p = {}), farm = L.kind === 'farm';
  if (btn){ btn.disabled = true; btn.innerHTML = '<span class="spin"></span>Laying…'; }
  try {
    const r = await post('/api/land/field', {pts: L.pts, culture: p.culture || '', what: L.kind, seed: p.seed || 1});
    p.built = r.things ? [r.things, r.plants, String(r.culture || '').replace(/\//g, ' '), lsFieldHash(lsFieldKey(L))].join('/') : '';
    lsChanged();                                   // (the plan keeps what was laid: Built after a reload too)
    if (!r.things) toast(`Nothing laid: no room for ${farm ? 'a field' : 'a tree'} here.`, true);
    else toast(`Laid ${farm ? 'a farm' : 'an orchard'}: ${r.plants} ${farm ? 'plants' : 'trees'}${r.things > r.plants ? `, ${r.things - r.plants} fence pieces` : ''}${r.culture ? ' (' + esc(r.culture) + ')' : ''}. Undo takes it back.`);
    await afterChange();
    for (const k of Object.keys(W.cells)) if (W.cells[k] && W.cells[k].exists) await worldReloadCell(k);
    drawMap(); renderWside(); if (typeof v3Refresh === 'function' && V3.on) v3Refresh();
  } catch (err){ toast(err.message, true); renderWside(); }
}

// ---------- towns (townplan.py): a town shape's streets and buildings, planned in a culture's way and drawn on the map
// (the user, 2026-10-30: "learn to plan and build towns with previews, at least as nice as the dungeon generator")
const LS_TOWN_COL = {house: '#c9a878', shop: '#5aa0dc', tavern: '#e6783c', temple: '#dcdc5a', guild: '#a06edc', manor: '#c85a8c', guard: '#8c8c8c'};
const LS_TOWN_KIND = {house: ['house', 'houses'], shop: ['shop', 'shops'], tavern: ['tavern', 'taverns'], temple: ['temple', 'temples'], guild: ['guild hall', 'guild halls'],
  manor: ['manor', 'manors'], guard: ['guard post', 'guard posts']};
async function lsCultures(){
  if (!LM.cultures && !LM.culturesAsked){
    LM.culturesAsked = true;
    // (still learning on a fresh install: asked again on a later look, so the lists fill in once learnt)
    try { const r = await api('/api/town/cultures'); if (!r.learning){ LM.cultures = r.cultures; LM.walls = r.walls || []; } } catch (e){ LM.cultures = []; LM.walls = []; }
    setTimeout(() => { LM.culturesAsked = false; }, 5000);
  }
  return LM.cultures;
}
function lsTownHtml(sel){
  const p = sel.p || {}, T = (LM.towns || {})[sel.id], cs = LM.cultures || [];
  if (!LM.cultures && !LM.culturesAsked) lsCultures().then(c => { if (c && PNL.isShown('world', 'land')) renderWside(); });
  const cult = p.culture || (T && T.plan && T.plan.culture) || '';
  let info = '<div class="msg" style="font-size:11.5px"><span class="spin"></span>Planning…</div>';
  if (T && T.err) info = `<div class="msg warn" style="font-size:11.5px">${esc(T.err)}</div>`;
  else if (T && T.learning && !T.plan) info = `<div class="msg" style="font-size:11.5px"><span class="spin"></span>Learning ${esc(T.learning.join(', '))} first (once)…</div>`;
  else if (T && T.plan){
    const c = {};
    T.plan.plots.forEach(q => { c[q.kind] = (c[q.kind] || 0) + 1; });
    const kinds = Object.entries(c).sort((a, b) => b[1] - a[1]).map(([k, n]) => `<span style="color:${LS_TOWN_COL[k] || '#ccc'}">■</span> ${n} ${esc((LS_TOWN_KIND[k] || [k, k])[n === 1 ? 0 : 1])}`).join(' · ');
    const Wl = T.plan.walls;
    const wtxt = !Wl ? '' : !Wl.pieces.length ? `<div class="msg warn" style="font-size:11.5px" title="${esc(Wl.faults.join('; '))}">No wall fits here</div>` :
      `<div class="msg" style="font-size:11.5px" title="${esc(Wl.family + (Wl.faults.length ? ': ' + Wl.faults.join('; ') : ''))}">Wall: ${Wl.pieces.length} pieces, ${Wl.gates} way${Wl.gates === 1 ? '' : 's'} in${(Wl.faults.find(f => /game's own buildings/.test(f)) || '').replace(/^(\d+) of the game's own buildings stand inside the wall$/, ' · $1 game buildings inside')}</div>`;
    info = `<div class="msg" style="font-size:11.5px;line-height:1.5">${T.plan.plots.length} buildings${T.plan.streets.length ? `, ${T.plan.streets.length} street${T.plan.streets.length === 1 ? '' : 's'}` : ''}${T.plan.square ? ', a square' : ''}: ${kinds}</div>${wtxt}`;
    // (a look with big buildings, Anvil's, in an outline too small for any: say so rather than show an empty town)
    if (!T.plan.plots.length) info = `<div class="msg" style="font-size:11.5px">No room for ${esc(T.plan.culture || 'its')} buildings here: draw the town bigger.</div>`;
  }
  const ws = LM.walls || [];
  return `<label title="Whose towns it is planned like: their streets, how close their buildings stand, how many shops and taverns. Blank: the nearest game town's">Like <select class="inp" id="ls-tcult"><option value="">the nearest town's${!p.culture && cult ? ' (' + esc(cult) + ')' : ''}</option>${cs.map(c => `<option value="${esc(c.id)}" ${p.culture === c.id ? 'selected' : ''} title="${esc((c.examples || []).join(', '))}">${esc(c.id)} (${c.towns} towns)</option>`).join('')}</select></label>${lsLookHtml(p, cult, cs)}
    <label title="A wall round it, the game's own pieces joined as its walls are, with gates where the streets go out">Wall <select class="inp" id="ls-twall"><option value="">none</option><option value="auto" ${p.walls === 'auto' ? 'selected' : ''}>its culture's</option>${ws.map(w => `<option value="${esc(w.id)}" ${p.walls === w.id ? 'selected' : ''} title="${esc((w.towns || []).join(', '))}">${esc(lsWallName(w.id))}</option>`).join('')}</select></label>
    <label title="The town's name: its interiors are called after it (Balmora, …). Blank: the one shown">Name <input class="inp" id="ls-tname" value="${esc(p.name || '')}" placeholder="${esc((T && T.plan && T.plan.name) || '')}" maxlength="40" spellcheck="false"></label>
    <label title="How many buildings, against the culture's own towns of this size (1). Up for a city, down for a hamlet. A walled town fills its wall at 1 and over">Density <input type="range" id="ls-tdens" min="0.3" max="4" step="0.1" value="${p.density || 1}"><span>${p.density || 1}</span></label>
    <label title="How wide its streets are. A street is painted in whole ground squares, 512 across">Streets <select class="inp" id="ls-tstreets"><option value="">as its towns'</option><option value="narrow" ${p.streets === 'narrow' ? 'selected' : ''}>narrower</option><option value="lanes" ${p.streets === 'lanes' ? 'selected' : ''}>lanes</option></select></label>
    <label title="What its people live by, as the game's towns of that trade: fishers and sailors, farmers and herders or miners in its homes and streets, the goods on its stalls, and its mix of shops, taverns and guard posts">Trade <select class="inp" id="ls-ttrade"><option value="">any</option>${[['harbour', 'fishing'], ['farm', 'farming'], ['mine', 'mining'], ['trade', 'trading']].map(([v, t]) => `<option value="${v}" ${p.trade === v ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
    <div class="v3lrow" style="display:flex;gap:4px;flex-wrap:wrap;align-items:center" title="Draw the town's own streets, quarters, wall or gates: the town follows them">Draw ${['street', 'zone', 'wall', 'gate'].map(k => `<button class="btn sm" data-add="${k}" title="${esc(LS_KINDS[k].how)}">${LS_KINDS[k].icon} ${LS_KINDS[k].label}</button>`).join('')}</div>
    ${lsTownCountsHtml(sel, T)}${lsTownChoicesHtml(sel, T)}
    <div class="v3lrow" style="display:flex;gap:10px;flex-wrap:wrap"><label title="Set out what the culture's towns set out: benches, signs, lamps, crates, a smith's forge, its own scenes"><input type="checkbox" id="ls-tdress" ${p.bare ? '' : 'checked'}> Dressed</label>
      <label title="Behind every door: none; the game building's own rooms and doors, empty, for you to furnish; or those rooms furnished by the Workshop">Inside <select class="inp" id="ls-tins"><option value="">furnished</option><option value="shells" ${lsInside(p) === 'shells' ? 'selected' : ''}>empty shells</option><option value="none" ${lsInside(p) === 'none' ? 'selected' : ''}>none</option></select></label>
      <label title="Guards, sellers at their stalls and townsfolk in the streets, as many as the culture's towns have; and a household in each furnished house, owning its beds and chests. Takes a minute or two"><input type="checkbox" id="ls-tppl" ${p.nopeople ? '' : 'checked'}> People</label></div>
    <div class="actions"><label title="The same outline and seed give the same town; another seed, another town">Seed <input class="inp" id="ls-tseed" type="number" min="1" max="999999" value="${p.seed || 1}" style="width:76px"></label><button class="btn sm" id="ls-treroll" title="Another layout of the same town">🎲 Another</button>
      <button class="btn sm" id="ls-tremove" title="Take away what Make it built here: its buildings, wall, dressing and interiors. What you added later and the ground stay. One Undo">✕ Remove the town</button>
      <button class="btn sm primary" id="ls-tmake" ${T && T.built ? 'disabled title="Built. Change the outline or a setting to plan it anew; ✕ Remove the town takes it away"' : `${T && T.plan && T.plan.plots.length ? '' : 'disabled'} title="Build it: the game's own buildings of this culture on every plot, as shown. One Undo takes it back"`}>${T && T.built ? '✓ Built' : '🏘 Make it'}</button>${lsGuide('Towns')}</div>${info}`;
}
// (what goes behind a town's doors: '' furnished, 'shells' or 'none'; a town planned before kept noinside)
function lsInside(p){ return p.inside || (p.noinside ? 'none' : ''); }
// (a wall family's name as the panel shows it: the kit ids read "imp", "hlaalu", "stronghold", 2026-11-04)
function lsWallName(id){
  const n = String(id).replace(/^ex_|^t_/i, '').replace(/_/g, ' ');
  const names = {imp: 'Imperial', hlaalu: 'Hlaalu', stronghold: 'Stronghold', velothi: 'Velothi', redoran: 'Redoran', nord: 'Nord', de: 'Dunmer', com: 'Common', telvanni: 'Telvanni'};
  return names[n.toLowerCase()] || n.charAt(0).toUpperCase() + n.slice(1);
}
// (the Look: which of the culture's building families leads the town, Balmora's or Narsis's; shown when the culture
// has two or more; the style review, 2026-11-07)
function lsLookHtml(p, cult, cs){
  const c = cs.find(x => x.id === cult), looks = (c && c.looks) || [];
  if (looks.length < 2) return '';
  return `<label title="Which of its building families the town is built of: each is named for the game town it is known by. Blank: as the game mixes them">Look <select class="inp" id="ls-tlook"><option value="">as the game mixes them</option>${looks.map(l => `<option value="${esc(l.id)}" ${p.look === l.id ? 'selected' : ''} title="${esc(l.buildings + ' buildings, leads ' + l.towns + ' town' + (l.towns === 1 ? '' : 's'))}">${esc(l.label)}</option>`).join('')}</select></label>`;
}
function lsTownBind(){
  const P = LM.plan, sel = P && P.layers[LM.sel]; if (!sel || sel.kind !== 'town') return;
  const c = $('#ls-tcult'); if (c) c.onchange = () => { sel.p.culture = c.value; delete sel.p.look; lsChanged(true); };
  const lk = $('#ls-tlook'); if (lk) lk.onchange = () => { if (lk.value) sel.p.look = lk.value; else delete sel.p.look; lsChanged(true); };
  const wl = $('#ls-twall'); if (wl) wl.onchange = () => { sel.p.walls = wl.value; lsChanged(true); };
  const stw = $('#ls-tstreets'); if (stw) stw.onchange = () => { sel.p.streets = stw.value; lsChanged(true); };
  const ttr = $('#ls-ttrade'); if (ttr) ttr.onchange = () => { sel.p.trade = ttr.value; lsChanged(true); };
  const tdn = $('#ls-tdens'); if (tdn){ tdn.oninput = () => { tdn.nextElementSibling.textContent = tdn.value; }; tdn.onchange = () => { sel.p.density = +tdn.value; lsChanged(true); }; }
  const cd = $('#ls-tcounts'); if (cd) cd.ontoggle = () => { LM.countsOpen = cd.open; };
  document.querySelectorAll('[data-tcount]').forEach(i => i.onchange = () => {
    const k = i.dataset.tcount, c = Object.assign({}, sel.p.counts || {});
    if (i.value === '') delete c[k]; else c[k] = Math.max(0, Math.min(99, Math.round(+i.value) || 0));
    sel.p.counts = c; lsChanged(true);
  });
  const cr = $('#ls-tcreset'); if (cr) cr.onclick = () => { sel.p.counts = {}; lsChanged(true); };
  const chd = $('#ls-tchoice'); if (chd){ chd.ontoggle = () => { LM.choiceOpen = chd.open; if (chd.open && typeof v3ThumbScan === 'function') v3ThumbScan(chd); }; if (chd.open && typeof v3ThumbScan === 'function') v3ThumbScan(chd); }
  document.querySelectorAll('[data-tskip]').forEach(i => i.onchange = () => {
    const k = i.dataset.tskip.toLowerCase(), sk = new Set((sel.p.skip || []).map(x => x.toLowerCase()));
    if (i.checked) sk.delete(k); else sk.add(k);
    sel.p.skip = [...sk]; lsChanged(true);
  });
  const sc = $('#ls-tskipclear'); if (sc) sc.onclick = () => { sel.p.skip = []; lsChanged(true); };
  const dr = $('#ls-tdress'); if (dr) dr.onchange = () => { sel.p.bare = !dr.checked; lsChanged(false); };
  const nm = $('#ls-tname'); if (nm) nm.onchange = () => { sel.p.name = nm.value.trim(); lsChanged(false); };
  const ins = $('#ls-tins'); if (ins) ins.onchange = () => { sel.p.inside = ins.value; delete sel.p.noinside; lsChanged(false); renderWside(); };
  const pp = $('#ls-tppl'); if (pp) pp.onchange = () => { sel.p.nopeople = !pp.checked; lsChanged(false); };
  const r = $('#ls-treroll'); if (r) r.onclick = () => { sel.p.seed = ((sel.p.seed || 1) % 100000) + 1 + Math.floor(Math.random() * 1000); lsChanged(true); };
  const sd = $('#ls-tseed'); if (sd) sd.onchange = () => { sel.p.seed = Math.max(1, parseInt(sd.value, 10) || 1); lsChanged(true); };
  const rm = $('#ls-tremove'); if (rm) rm.onclick = async () => {
    if (!await needProject()) return;
    let n; try { n = await post('/api/town/remove', {outline: sel.pts, look: true}); } catch (e){ return toast(e.message, true); }
    if (!confirm(`Remove ${n.name}: ${n.things} things it built and its ${n.interiors} interiors? What you added later and the ground stay. One Undo brings it back.`)) return;
    try {
      const r = await post('/api/town/remove', {outline: sel.pts});
      toast(`Removed ${r.name}: ${r.things} things and ${r.interiors} interiors. Make it builds it again.`);
      { const Tb = (LM.towns || {})[sel.id]; if (Tb) Tb.built = false; }
      if (typeof afterChange === 'function') await afterChange();
      for (const k of Object.keys(W.cells)) if (W.cells[k] && W.cells[k].exists) await worldReloadCell(k);
      drawMap(); if (typeof v3Refresh === 'function' && V3.on) v3Refresh();
    } catch (e){ toast(e.message, true); }
  };
  const mk = $('#ls-tmake'); if (mk) mk.onclick = () => lsMakeTown(sel, '#ls-tmake');
}
async function lsMakeTown(sel, bsel){
    if (!await needProject()) return false;
    const mk = $(bsel); let ok = false;
    if (mk){ mk.disabled = true; mk.innerHTML = `<span class="spin"></span>Building…${lsInside(sel.p) === 'none' ? '' : ' (a minute or two)'}`; }
    // (a bar on the button, filled as the server says how far it has got: PIN2 2026-11-01, "It takes a bit for the town
    // to appear. you think you can do a progress bar?" townbuild.PROGRESS)
    const bar = (what, pct) => {
      const b = $(bsel); if (!b) return;
      b.disabled = true; b.textContent = `${what}… ${pct}%`; b.title = 'Building: ' + what;
      b.style.background = `linear-gradient(90deg, var(--gold) ${pct}%, transparent ${pct}%)`; b.classList.add('pbar');
    };
    const poll = setInterval(async () => {
      let p; try { p = await api('/api/town/progress'); } catch (e){ return; }
      if (p && p.on) bar(p.what, Math.round(p.frac * 100));
    }, 600);
    try {
      const T = (LM.towns || {})[sel.id];
      let r_;
      try {
        r_ = await post('/api/town/make', {outline: sel.pts, culture: sel.p.culture || (T && T.plan && T.plan.culture) || '', seed: sel.p.seed || 1, walls: lsTownWalls(sel), opts: lsTownOpts(sel), dress: !sel.p.bare,
          interiors: lsInside(sel.p) || 'furnished', people: !sel.p.nopeople, name: sel.p.name || ''});
      } finally { clearInterval(poll); }
      if (r_.learning) throw new Error('Still learning ' + r_.learning.join(', ') + ': try again in a minute.');
      bar('Showing it', 100);
      toast(`Built ${esc(r_.name || 'the town')}: ${r_.buildings} buildings${r_.wall ? ' and a wall' : ''}${r_.interiors ? `, ${r_.interiors} interiors` : ''}${r_.people ? `, ${r_.people} people` : ''}${r_.dressed ? `, ${r_.dressed} things set out` : ''}. One Undo takes it back.`);
      // (the cells it went into and their ground read again, in 3D too: only the flat map was redrawn, and the 3D view
      // went on showing the bare land until the place was opened again, the user's "where's the town I built?", 2026-10-31)
      if (typeof afterChange === 'function') await afterChange();
      for (const k of Object.keys(W.cells)) if (W.cells[k] && W.cells[k].exists) await worldReloadCell(k);
      W.lands = {}; if (typeof v3LandsReload === 'function') v3LandsReload();
      ok = true;
      const Tb = (LM.towns || {})[sel.id]; if (Tb) Tb.built = true;
      // (the map centres on the town: built from a cell opened elsewhere, the view stayed there and 3D showed no town, 2026-11-04)
      if (sel.pts && sel.pts.length && !V3.on && W.cam){ W.cam.x = sel.pts.reduce((a, p) => a + p[0], 0) / sel.pts.length; W.cam.y = sel.pts.reduce((a, p) => a + p[1], 0) / sel.pts.length; }
      drawMap(); renderWside(); if (typeof v3Refresh === 'function' && V3.on) v3Refresh();
    } catch (e){ toast(e.message, true); }
    const b = $(bsel);
    if (b && bsel === '#ls-tmake' && !ok){ b.disabled = false; b.textContent = '🏘 Make it'; b.style.background = ''; b.title = 'Build it: the game\'s own buildings of this culture on every plot, as shown. One Undo takes it back'; }
    return ok;
}
// ----- a town's own streets, zones and wall (PIN2, 2026-11-01): shapes drawn from its panel, each belonging to the
// town it lies in (else the nearest), sent with its plan as townplan's opts
function lsInPoly(pts, x, y){
  let c = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++){
    const [xi, yi] = pts[i], [xj, yj] = pts[j];
    if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) c = !c;
  }
  return c;
}
function lsTownOf(L){
  const towns = ((LM.plan && LM.plan.layers) || []).filter(t => t.kind === 'town' && t.pts && t.pts.length >= 3);
  if (!towns.length || !L.pts || !L.pts.length) return null;
  const mid = P_ => [P_.reduce((a, p) => a + p[0], 0) / P_.length, P_.reduce((a, p) => a + p[1], 0) / P_.length];
  const m = mid(L.pts);
  let best = null, bd = Infinity;
  for (const t of towns){
    const n = L.pts.filter(p => lsInPoly(t.pts, p[0], p[1])).length, tm = mid(t.pts);
    const d = n ? -n : Math.hypot(tm[0] - m[0], tm[1] - m[1]);
    if (d < bd){ bd = d; best = t; }
  }
  return best;
}
function lsTownOpts(T){
  const o = {}, p = T.p || {};
  if (p.streets) o.streets = p.streets;
  if (p.look) o.family = p.look;
  if (p.density && +p.density !== 1) o.density = +p.density;
  if (p.trade) o.trade = p.trade;
  if (p.counts && Object.keys(p.counts).length) o.counts = p.counts;
  if (p.skip && p.skip.length) o.skip = p.skip;
  for (const L of LM.plan.layers){
    if (L.on === false || !LS_KINDS[L.kind] || !LS_KINDS[L.kind].town || lsTownOf(L) !== T) continue;
    if (L.kind === 'street') (o.roads = o.roads || []).push(L.pts);
    else if (L.kind === 'zone') (o.zones = o.zones || []).push({kind: (L.p && L.p.zone) || 'residential', pts: L.pts});
    else if (L.kind === 'wall' && !o.wall) o.wall = L.pts;
    else if (L.kind === 'gate') (o.gates = o.gates || []).push(L.pts[0]);
  }
  return o;
}
// (a wall drawn and none chosen: the culture's own)
function lsTownWalls(T){ return (T.p && T.p.walls) || (lsTownOpts(T).wall ? 'auto' : ''); }
function lsTownCountsHtml(sel, T){
  const p = sel.p || {}, got = {};
  if (T && T.plan) T.plan.plots.forEach(q => { got[q.kind] = (got[q.kind] || 0) + 1; });
  const set = p.counts || {}, n = Object.keys(set).length;
  return `<details id="ls-tcounts" ${LM.countsOpen ? 'open' : ''}><summary title="How many of each: blank as its towns have them">How many${n ? ` (${n} set)` : ''}</summary>
    <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:3px 10px;margin:4px 0">${['shop', 'tavern', 'temple', 'guild', 'manor', 'guard'].map(k =>
      `<label style="display:flex;align-items:center;gap:4px;font-size:12px" title="${esc(LS_TOWN_KIND[k][1])}: blank as its towns have them"><span style="color:${LS_TOWN_COL[k]}">■</span><span style="flex:1">${esc(LS_TOWN_KIND[k][1][0].toUpperCase() + LS_TOWN_KIND[k][1].slice(1))}</span><input class="inp" type="number" min="0" max="99" data-tcount="${k}" value="${set[k] != null ? set[k] : ''}" placeholder="${got[k] || 0}" style="width:48px"></label>`).join('')}</div>
    ${n ? '<button class="btn sm" id="ls-tcreset" title="Back to its towns\' own mix">As its towns</button>' : ''}</details>`;
}
// (the buildings the plan picks from, with how often it used each; untick one and it is left out: PIN2 2026-11-01,
// "give you a selection of buildings that would be used in the generation ... remove lets say certain chapels")
function lsTownChoicesHtml(sel, T){
  const ch = (T && T.plan && T.plan.choices) || [], off = new Set((sel.p.skip || []).map(k => k.toLowerCase()));
  if (!ch.length && !off.size) return '';
  const used = ch.filter(c => c.n).length;
  return `<details id="ls-tchoice" ${LM.choiceOpen ? 'open' : ''}><summary title="The game's buildings this town picks from. Untick one to leave it out">Which buildings (${used} of ${ch.length} used${off.size ? `, ${off.size} left out` : ''})</summary>
    <div class="ls-tch">${ch.map(c => `<label class="${off.has(c.key.toLowerCase()) ? 'off' : ''}" title="${esc(c.key)}: ${esc((LS_TOWN_KIND[c.kind] || [c.kind])[0])}, ${c.w} × ${c.d}${c.n ? `, used ${c.n} time${c.n === 1 ? '' : 's'}` : ''}"><input type="checkbox" data-tskip="${esc(c.key)}" ${off.has(c.key.toLowerCase()) ? '' : 'checked'}>${typeof thumbImg === 'function' && !c.key.startsWith('prefab:') ? thumbImg(c.key, 'STAT', 48, 'sm') : ''}<span><span style="color:${LS_TOWN_COL[c.kind] || '#ccc'}">■</span> ${esc(c.key.replace(/^prefab:/, '★ ').replace(/^ex_|^t_/i, ''))}</span><b>${c.n || ''}</b></label>`).join('')}</div>
    ${off.size ? '<button class="btn sm" id="ls-tskipclear" title="Use all of them again">Use them all</button>' : ''}</details>`;
}
function lsTownPartHtml(sel){
  const T = lsTownOf(sel);
  let h = `<div class="msg" style="font-size:11.5px">${T ? `Part of ${esc(T.name || 'the town')}.` : 'Draw a town round it first.'}</div>`;
  if (sel.kind === 'zone') h += `<label title="Houses keep shops, taverns and halls out; business draws shops, taverns and guilds; noble draws manors and temples">Zone <select class="inp" id="ls-zone">${Object.entries(LS_ZONES).map(([k, [lab]]) => `<option value="${k}" ${(sel.p.zone || 'residential') === k ? 'selected' : ''}>${lab}</option>`).join('')}</select></label>`;
  return h;
}
// (a wall's points on a grid of its pieces' step from its first point, the second turned in 15° steps, each side
// square to the last: "like ridges that lock into a grid once you put down your first point", PIN2)
function lsWallStep(L){
  const T = lsTownOf(L), t = T && LM.towns && LM.towns[T.id];
  if (t && t.plan && t.plan.walls && t.plan.walls.step) return t.plan.walls.step;
  const w = T && (LM.walls || []).find(x => x.id === T.p.walls);
  return (w && w.step) || 512;
}
function lsWallSnap(pts, i, x, y, step){
  if (!i || !pts.length) return [Math.round(x), Math.round(y)];
  const [x0, y0] = pts[0];
  if (i === 1){
    const a = Math.round(Math.atan2(y - y0, x - x0) / (Math.PI / 12)) * Math.PI / 12;
    const d = Math.max(1, Math.round(Math.hypot(x - x0, y - y0) / step)) * step;
    return [Math.round(x0 + Math.cos(a) * d), Math.round(y0 + Math.sin(a) * d)];
  }
  const a = Math.atan2(pts[1][1] - y0, pts[1][0] - x0), c = Math.cos(a), s = Math.sin(a);
  const loc = p => [Math.round(((p[0] - x0) * c + (p[1] - y0) * s) / step), Math.round((-(p[0] - x0) * s + (p[1] - y0) * c) / step)];
  let [u, v] = loc([x, y]);
  const [pu, pv] = loc(pts[i - 1]);
  if (Math.abs(u - pu) >= Math.abs(v - pv)) v = pv; else u = pu;
  return [Math.round(x0 + (u * c - v * s) * step), Math.round(y0 + (u * s + v * c) * step)];
}
function lsTownsSoon(){ clearTimeout(LM.townT); LM.townT = setTimeout(lsTowns, 350); }
// (one plan asked at a time: every change asked for its own, each ran to the end on the server one after another, and
// a few edits and 🎲 Another left the town on "Planning…" for minutes, the user and PIN2 2026-11-01. A change while one
// is on its way asks again once it is back, for the plan as it is then)
async function lsTowns(){
  if (LM.townBusy){ LM.townAgain = true; return; }
  LM.townBusy = true;
  try { await lsTownsOnce(); }
  finally {
    LM.townBusy = false;
    if (LM.townAgain){ LM.townAgain = false; lsTownsSoon(); }
  }
}
async function lsTownsOnce(){
  const P = LM.plan; if (!P) return;
  LM.towns = LM.towns || {};
  for (const L of P.layers){
    if (L.kind !== 'town' || !L.pts || L.pts.length < 3) continue;
    const opts = lsTownOpts(L), walls = lsTownWalls(L);
    const key = JSON.stringify([L.pts, L.p.culture || '', L.p.seed || 1, walls, opts]);
    const T = LM.towns[L.id];
    if (T && T.key === key) continue;
    LM.towns[L.id] = {key, plan: T && T.plan, busy: true};
    try {
      let plan;
      for (;;){
        plan = await post('/api/town/plan', {outline: L.pts, culture: L.p.culture || '', seed: L.p.seed || 1, walls, opts});
        if (!plan.learning || LM.towns[L.id].key !== key) break;
        // (a fresh install learns the game's towns first, once, in the survey process)
        LM.towns[L.id].learning = plan.learning;
        if (P.layers[LM.sel] === L && PNL.isShown('world', 'land')) renderWside();
        await new Promise(res => setTimeout(res, 2500));
      }
      if (LM.towns[L.id].key === key && !plan.learning) LM.towns[L.id] = {key, plan};
    } catch (e){ if (LM.towns[L.id].key === key) LM.towns[L.id] = {key, err: e.message}; }
    drawMap();
    // (and with another shape selected, for the pinned Build button, unless something there is being typed in)
    const typing = document.activeElement && /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName) && document.activeElement.type !== 'checkbox';
    if (PNL.isShown('world', 'land') && (P.layers[LM.sel] === L || !typing)) renderWside();
  }
}
function lsTownDraw(g, P){
  for (const L of P.layers){
    const T = L.kind === 'town' && L.on !== false && LM.towns && LM.towns[L.id];
    if (!T || !T.plan) continue;
    const z = W.cam.z, pl = T.plan;
    g.fillStyle = 'rgba(120,112,100,0.75)';
    for (const [px, py] of (pl.paint || pl.roads)){ const [sx, sy] = toScreen(px * 512, (py + 1) * 512); g.fillRect(sx, sy, 512 * z + 0.5, 512 * z + 0.5); }
    if (pl.walls){
      // (the wall's own pieces, as laid: gates green, towers and corners darker)
      g.lineWidth = Math.max(1, 30 * z); g.strokeStyle = 'rgba(120,112,100,0.75)';
      for (const [a, b, w] of pl.walls.roads){ const A = toScreen(a[0], a[1]), B = toScreen(b[0], b[1]); g.lineWidth = Math.max(2, w * z); g.beginPath(); g.moveTo(A[0], A[1]); g.lineTo(B[0], B[1]); g.stroke(); }
      for (const [k, cs] of pl.walls.pieces){
        g.beginPath(); cs.forEach((p, i) => { const [sx, sy] = toScreen(p[0], p[1]); if (i) g.lineTo(sx, sy); else g.moveTo(sx, sy); });
        g.closePath(); g.fillStyle = k === 'gate' ? '#4caf50' : k === 'tower' || k === 'corner' || k === 'bigtower' || k === 'keep' ? '#5a4a3a' : '#8a7a66'; g.fill();
      }
    }
    for (const q of pl.plots){
      g.beginPath(); q.rect.forEach((p, i) => { const [sx, sy] = toScreen(p[0], p[1]); if (i) g.lineTo(sx, sy); else g.moveTo(sx, sy); });
      g.closePath(); g.fillStyle = (LS_TOWN_COL[q.kind] || '#c9a878') + 'dd'; g.fill(); g.strokeStyle = 'rgba(30,20,10,0.9)'; g.lineWidth = 1; g.stroke();
      if (z > 0.02){ const [dx, dy] = toScreen(q.door[0], q.door[1]); g.fillStyle = '#ff3c3c'; g.beginPath(); g.arc(dx, dy, Math.max(1.5, Math.min(4, 40 * z)), 0, Math.PI * 2); g.fill(); }
      if (z > 0.06 && q.b){ const [tx, ty] = toScreen(q.x, q.y); g.font = '10px sans-serif'; g.fillStyle = 'rgba(20,14,8,0.9)'; g.textAlign = 'center'; g.fillText(q.b.key.replace(/^ex_|^t_/i, ''), tx, ty); g.textAlign = 'start'; }
    }
  }
}
// Shapes mark the cells they reach (the user, 2026-10-30: "Shapes mark own cells"): after every change to the plan,
// the cells any shape now reaches are marked, towns left out (as marking by hand; ⛰ Mark its cells with Shift takes
// them). Marks are only ever added here: a moved shape's old cells stay marked, so Start from the land under my mod
// clears its old land there. Dress areas change no ground and mark nothing.
async function lsAutoMark(){
  if (!LM.data || !LM.plan || !(S.summary && S.summary.project)) return;
  const want = new Set();
  for (const L of LM.plan.layers) if (L.on !== false && !lsNoShape(L.kind) && L.pts && L.pts.length) lsShapeCells(L).forEach(k => want.add(k));
  const add = [...want].filter(k => !LM.data.marked.has(k) && !(lmCell(k) && lmCell(k)[0] === 'settled'));
  if (!add.length) return;
  try {
    await lmMarksPost({add});
    toast(`Marked ${add.length} more cell${add.length === 1 ? '' : 's'} the shapes reach.`);
    renderWside(); drawMap();
  } catch (e){ toast(e.message, true); }
}
function lsPreviewSoon(){
  clearTimeout(LM.prevT);
  LM.prevStale = true;                                // (the one shown is out of date: drawn dimmed till the new one)
  LM.prevT = setTimeout(lsPreview, 350);
}
async function lsPreview(){
  if (!LM.data || !LM.plan || LM.prevOn === false){ LM.prevStale = false; return; }
  // (nothing to preview: also stops one still on its way from painting the old plan back. With no shapes left, the
  // map shows the land as it is: after a Shape them, Clear shapes and a town drawn, the preview of "what Shape would
  // make now", the land under the mod, was painted over the marked cells and the ridge just shaped vanished from the
  // 2D map while the 3D view had it, the user 2026-11-07)
  // (towns, streets, zones and walls shape nothing: with only those, no preview; and a change to them alone previews
  // nothing again. Every change to a town re-ran the ground's preview, 3 seconds on 4 cells, the user's "so slow", 2026-11-01)
  const gl = LM.plan.layers.filter(L => !lsNoShape(L.kind));
  if (!LM.data.marks.length || (!gl.length && !lsTerrOn())){ ++LM.prevN; LM.prev = null; LM.prevSig = null; LM.prevStale = false; drawMap(); return; }
  const sig = JSON.stringify([LM.data.marks, gl, Object.entries(LM.plan).filter(([k]) => k !== 'layers')]);
  if (sig === LM.prevSig && LM.prevData && !LM.prevBusy){ LM.prevStale = false; drawMap(); return; }
  // (one preview at a time: changes made while it works are previewed once it's back, the latest only. Each edit
  // sent its own, and on a big plan with rock layers they queued up on the server: 30 seconds behind, PIN2 2026-10-30)
  if (LM.prevBusy){ LM.prevAgain = true; return; }
  const ask = ++LM.prevN;
  LM.prevBusy = true; LM.prevT = Date.now();
  // (the seconds on "Updating the preview…" count up: a big coast takes a minute or two, PIN2 2026-11-02)
  const tick = setInterval(() => { if (LM.prevStale) drawMap(); }, 1000);
  try {
    const r = await post('/api/land/plan/preview', {cells: LM.data.marks, plan: LM.plan});
    if (r.stopped){
      // (stopped from the busy chip: the old preview stays, and the next change to a shape previews again)
      LM.prevAgain = false;
      if (ask === LM.prevN){ LM.prevStale = false; drawMap(); const n = $('#ls-note'); if (n) n.textContent = 'Preview stopped. It runs again when you change a shape.'; }
      return;
    }
    if (ask !== LM.prevN || LM.prevAgain) return;     // (a newer one is on its way, or wanted)
    LM.prevStale = false; LM.prevSig = sig;
    LM.prevData = r; LM.prevTex = r.textures; LM.prevInfo = r.info || {};
    lsBuildPrev(); drawMap();
    const lg = $('#ls-texlegend'); if (lg) lg.innerHTML = lsLegend();
    const st = $('#ls-settle-t'); if (st && LM.prevInfo.settle_angle){ st.textContent = lsSettleText(LM.prevInfo.settle_angle); st.title = lsSettleTip(LM.prevInfo.settle_angle); }
    // (the marked cells' regions arrived: the "Only in" choices follow them)
    const hk = lsHereRegions().join('|') + JSON.stringify((LM.prevInfo.terrain || {}).like || {});
    if (hk !== LM.hereKey){ LM.hereKey = hk; renderWside(); }
    const ht = $('#ls-held-t'); if (ht && LM.prevInfo.held != null) ht.textContent = `(${LM.prevInfo.held} here, outlined on the map)`;
  } catch (e){ if (ask === LM.prevN){ LM.prevStale = false; drawMap(); } const n = $('#ls-note'); if (n) n.textContent = e.message; }
  finally {
    LM.prevBusy = false; clearInterval(tick);
    if (LM.prevAgain){ LM.prevAgain = false; lsPreview(); }
  }
}
LM.prevN = 0;

// ----- drawing a new shape: click points, double-click (or Enter) to finish; a stamp is one click
async function lsStart(kind){
  if (!LS_KINDS[kind]) return;                       // (only the Land panel's own shapes)
  if (!await needProject()) return;
  if (V3.on) await v3Enable(false);
  LM.show = true;
  LM.drawing = {kind, pts: []};
  $('#maptip').style.display = 'none';
  lsHook();
  setMode('landshape'); cv.classList.add('place');
  setBanner(`${LS_KINDS[kind].icon} ${esc(LS_KINDS[kind].how)} <kbd>Backspace</kbd> takes the last point back, <kbd>Esc</kbd> cancels. <button class="btn sm" id="ls-done">Done</button>`);
  $('#ls-done').onclick = lsFinish;
  drawMap();
}
// (an outline closes when its first point is clicked again, as a pen tool's does: the user's coast left a second
// point lying on the first, PIN2 2026-10-29)
function lsOnFirst(D, x, y){
  if (!D || !LS_KINDS[D.kind].closed || D.pts.length < 3) return false;
  const [sx, sy] = toScreen(D.pts[0][0], D.pts[0][1]);
  return Math.hypot(sx - x, sy - y) <= LS_GRAB;
}
function lsDown(e){
  const D = LM.drawing; if (!D) return;
  if (lsOnFirst(D, e.offsetX, e.offsetY)) return lsFinish();
  const [wx, wy] = toWorld(e.offsetX, e.offsetY);
  D.pts.push(D.kind === 'wall' ? lsWallSnap(D.pts, D.pts.length, wx, wy, lsWallStep(D)) : [Math.round(wx), Math.round(wy)]);
  if (LS_KINDS[D.kind].point || D.kind === 'stamp') return lsFinish();
  drawMap();
}
function lsMoveMouse(e){
  if (!LM.drawing) return;
  LM.mouse = toWorld(e.offsetX, e.offsetY);
  if (LM.drawing.kind === 'wall') LM.mouse = lsWallSnap(LM.drawing.pts, LM.drawing.pts.length, LM.mouse[0], LM.mouse[1], lsWallStep(LM.drawing));
  LM.closeHot = lsOnFirst(LM.drawing, e.offsetX, e.offsetY);
  cv.style.cursor = LM.closeHot ? 'pointer' : '';
  drawMap();
}
function lsFinish(){
  const D = LM.drawing; LM.drawing = null; LM.closeHot = false; cv.style.cursor = '';
  if (W.mode === 'landshape') setMode(null);
  if (!D) return;
  // (a double-click adds its point twice)
  const pts = D.pts.filter((p, i) => !i || Math.hypot(p[0] - D.pts[i - 1][0], p[1] - D.pts[i - 1][1]) > 64);
  const need = D.kind === 'stamp' || LS_KINDS[D.kind].point ? 1 : LS_KINDS[D.kind].closed ? 3 : 2;
  // (an outline's last point put down on its first: the same point, the outline closes there anyway)
  const near = (a, b) => { const [ax, ay] = toScreen(a[0], a[1]), [bx, by] = toScreen(b[0], b[1]); return Math.hypot(ax - bx, ay - by) <= LS_GRAB || Math.hypot(a[0] - b[0], a[1] - b[1]) <= 64; };
  while (LS_KINDS[D.kind].closed && pts.length > need && near(pts[pts.length - 1], pts[0])) pts.pop();
  if (pts.length < need){ toast(`A ${LS_KINDS[D.kind].label.toLowerCase()} needs ${need} point${need === 1 ? '' : 's'} at least.`, true); drawMap(); return; }
  const P = LM.plan;
  const L = {id: String(Date.now()), kind: D.kind, name: '', on: true, pts, p: lsFresh(Object.assign({}, LS_DEFAULTS[D.kind]))};
  P.layers.push(L);
  LM.sel = P.layers.length - 1;
  if (LS_KINDS[D.kind].town && !lsTownOf(L)) toast('Draw it inside a town: it belongs to the town it lies in.');
  lsChanged(true);
}
function lsHook(){
  if (LM.hooked) return;
  LM.hooked = true;
  cv.addEventListener('dblclick', e => { if (W.mode === 'landshape' && LM.drawing){ e.preventDefault(); lsFinish(); } });
}
document.addEventListener('keydown', e => {
  if (W.mode === 'landshape' && LM.drawing && e.key === 'Enter'){ e.preventDefault(); lsFinish(); }
  // (Backspace while drawing: the last point back off, and nothing else: it is also "Delete what's selected",
  // so it stops here, first, as Extend's does)
  if (W.mode === 'landshape' && LM.drawing && e.key === 'Backspace' && !(e.target && e.target.matches && e.target.matches('input,textarea'))){
    e.preventDefault(); e.stopImmediatePropagation(); LM.drawing.pts.pop(); drawMap(); return;
  }
  if (W.mode !== 'landshape' && LM.drawing){ LM.drawing = null; drawMap(); }
}, true);

// ----- the shapes on the map, the one picked with its points to drag
function lsDrawShapes(g){
  const P = LM.plan; if (!P) return;
  lsTownDraw(g, P);
  if (typeof csDraw === 'function') csDraw(g, P);
  const line = (pts, closed, color, width, dash) => {
    if (!pts.length) return;
    g.beginPath(); pts.forEach((p, i) => { const [sx, sy] = toScreen(p[0], p[1]); if (i) g.lineTo(sx, sy); else g.moveTo(sx, sy); });
    if (closed) g.closePath();
    g.setLineDash(dash || []); g.strokeStyle = color; g.lineWidth = width; g.stroke(); g.setLineDash([]);
  };
  P.layers.forEach((L, i) => {
    const K = LS_KINDS[L.kind], on = i === LM.sel, a = L.on === false ? '55' : 'ff';
    if (L.kind === 'stamp'){
      // (its reach: an oval when stretched, its long side the way Turn points; the map's y runs down, so the turn is mirrored)
      const [sx, sy] = toScreen(L.pts[0][0], L.pts[0][1]), r = (L.p.radius || 8192) * W.cam.z, st = Math.max(1, +(L.p.stretch || 1));
      g.beginPath(); g.ellipse(sx, sy, r * st, r, -(+(L.p.turn || 0)) * Math.PI / 180, 0, Math.PI * 2); g.setLineDash([5, 4]); g.strokeStyle = K.color + a; g.lineWidth = on ? 2.5 : 1.5; g.stroke(); g.setLineDash([]);
    } else if (K.point){
      // a spring: the way the water found from it, from the last preview
      const way = LM.prevInfo && LM.prevInfo.springs && LM.prevInfo.springs[L.id];
      if (way && L.on !== false) line(way, false, K.color + a, on ? 3 : 2);
      const [sx, sy] = toScreen(L.pts[0][0], L.pts[0][1]);
      g.beginPath(); g.arc(sx, sy, 6, 0, Math.PI * 2); g.fillStyle = K.color + a; g.fill();
      if (L.kind === 'label' && L.on !== false){ g.font = 'italic 12px serif'; g.fillStyle = '#f0e0c8' + a; g.fillText(L.name || (L.p || {}).name || '', sx + 9, sy + 4); }
      if (L.kind === 'dungeon'){
        // (a ring once built; its name when the map is close enough to read it)
        if ((L.p || {}).built){ g.beginPath(); g.arc(sx, sy, 9, 0, Math.PI * 2); g.strokeStyle = '#ffffff' + a; g.lineWidth = 1.5; g.stroke(); }
        // (a marker not built yet says so: a name alone read as a cave that stands there, the user, 2026-11-08: "the
        // workshop suggests there was a cave placed here, but I see no entrances")
        if (W.cam.z * 8192 > 90 && (L.name || (L.p || {}).name)){
          const built = !!(L.p || {}).built;
          g.font = built ? '11px sans-serif' : 'italic 11px sans-serif'; g.fillStyle = (built ? '#f0e0c8' : '#c8bca8') + a;
          g.fillText((L.name || L.p.name) + (built ? '' : ' · not built yet'), sx + 10, sy + 4);
        }
      }
    } else if (L.kind === 'zone'){
      const zc = (LS_ZONES[L.p && L.p.zone] || LS_ZONES.residential)[1];
      g.beginPath(); L.pts.forEach((p, k) => { const [sx, sy] = toScreen(p[0], p[1]); if (k) g.lineTo(sx, sy); else g.moveTo(sx, sy); });
      g.closePath(); g.fillStyle = zc + (L.on === false ? '10' : '30'); g.fill();
      line(L.pts, true, zc + a, on ? 3 : 2, [6, 4]);
    } else if (L.kind === 'street') line(L.pts, false, K.color + a, Math.max(on ? 4 : 3, 512 * W.cam.z));
    else if (L.kind === 'road'){
      line(L.pts, false, K.color + a, Math.max(on ? 4 : 2.5, 320 * W.cam.z), [10, 4]);
      // (its bridges: solid and wider, as wide as their decks)
      for (const b of (L.p || {}).bridges || []) line([[b[0], b[1]], [b[2], b[3]]], false, '#f4e8d0' + a, Math.max(on ? 6 : 4.5, 560 * W.cam.z));
    }
    else if (L.kind === 'wall') line(L.pts, true, K.color + a, Math.max(on ? 5 : 4, 200 * W.cam.z));
    else if (lsIsField(L.kind)){
      // (the longest edge is the gate's side, the field's near edge: drawn heavier)
      line(L.pts, true, K.color + a, on ? 3 : 2);
      const e = lsLongEdge(L.pts); if (e) line(e, false, K.color + a, on ? 7 : 5);
    }
    else line(L.pts, K.closed, K.color + a, on ? 3 : 2);
    const F = on && !LM.drawing ? lsFrame(L) : null;
    if (F){
      // (the frame: dashed box, corner squares to size, a knob to turn, a cross to move)
      g.setLineDash([4, 4]); g.strokeStyle = 'rgba(255,255,255,0.55)'; g.lineWidth = 1; g.strokeRect(F.x0, F.y0, F.x1 - F.x0, F.y1 - F.y0); g.setLineDash([]);
      g.beginPath(); g.moveTo((F.x0 + F.x1) / 2, F.y0); g.lineTo(F.knob[0], F.knob[1] + 7); g.stroke();
      g.fillStyle = '#fff'; g.strokeStyle = K.color; g.lineWidth = 2;
      for (const [cx, cy] of F.corners){ g.fillRect(cx - 5, cy - 5, 10, 10); g.strokeRect(cx - 5, cy - 5, 10, 10); }
      g.beginPath(); g.arc(F.knob[0], F.knob[1], 7, 0, Math.PI * 2); g.fill(); g.stroke();
      g.beginPath(); g.moveTo(F.cs[0] - 8, F.cs[1]); g.lineTo(F.cs[0] + 8, F.cs[1]); g.moveTo(F.cs[0], F.cs[1] - 8); g.lineTo(F.cs[0], F.cs[1] + 8); g.stroke();
    }
    if (on){
      const H = LM.hdrag, hot = H && !H.move && !H.xf ? H.i : (LM.hover ?? -1), onto = H && !H.move && !H.xf ? H.onto : -1;
      L.pts.forEach((p, k) => {
        const [sx, sy] = toScreen(p[0], p[1]), big = k === hot || k === onto;
        g.fillStyle = k === onto ? K.color : '#fff'; g.strokeStyle = K.color; g.lineWidth = 2;
        g.beginPath(); g.arc(sx, sy, big ? 7 : 5, 0, Math.PI * 2); g.fill(); g.stroke();
        // (the point it will join if let go here: a ring round it)
        if (k === onto){ g.beginPath(); g.arc(sx, sy, 11, 0, Math.PI * 2); g.strokeStyle = '#fff'; g.lineWidth = 1.5; g.stroke(); }
      });
    }
  });
  // the pieces the ground is held under (landshapes._holds), from the last preview
  const held = LM.prevOn !== false && LM.prevData && LM.prevData.held;
  if (held && held.length){
    g.fillStyle = 'rgba(255,160,60,0.35)'; g.strokeStyle = 'rgba(255,170,70,0.95)'; g.lineWidth = 1.2;
    for (const box of held){
      g.beginPath(); box.forEach((p, i) => { const [sx, sy] = toScreen(p[0], p[1]); if (i) g.lineTo(sx, sy); else g.moveTo(sx, sy); });
      g.closePath(); g.fill(); g.stroke();
    }
  }
  const D = LM.drawing;
  if (D){
    const pts = D.pts.concat(LM.mouse ? [LM.closeHot ? D.pts[0] : LM.mouse] : []);
    line(pts, false, LS_KINDS[D.kind].color, 2, [6, 4]);
    for (const p of D.pts){ const [sx, sy] = toScreen(p[0], p[1]); g.fillStyle = LS_KINDS[D.kind].color; g.beginPath(); g.arc(sx, sy, 4, 0, Math.PI * 2); g.fill(); }
    // (the first point, ringed while a click there would close the outline)
    if (LM.closeHot && D.pts.length){ const [sx, sy] = toScreen(D.pts[0][0], D.pts[0][1]); g.beginPath(); g.arc(sx, sy, 10, 0, Math.PI * 2); g.strokeStyle = '#fff'; g.lineWidth = 2; g.stroke(); }
  }
}
// editing shapes on the map (the map's own drag otherwise): click a shape's line to pick it; on the picked one,
// drag a point, Ctrl+click a point to take it out, click its line to add a point there, Shift+drag its line to move
// the whole shape. The user wanted the land tools easier: points could only be dragged, and a shape picked from the
// list alone
function lsSegHit(L, x, y){
  // (the nearest piece of the line within 7 pixels: [index of the point it starts from, distance])
  const K = LS_KINDS[L.kind], n = L.pts.length;
  if (K.point || L.kind === 'stamp' || n < 2) return null;
  let best = null;
  for (let i = 0; i < (K.closed ? n : n - 1); i++){
    const [ax, ay] = toScreen(L.pts[i][0], L.pts[i][1]), [bx, by] = toScreen(L.pts[(i + 1) % n][0], L.pts[(i + 1) % n][1]);
    const dx = bx - ax, dy = by - ay, t = Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / Math.max(1e-6, dx * dx + dy * dy)));
    const d = Math.hypot(ax + t * dx - x, ay + t * dy - y);
    if (d <= 7 && (!best || d < best[1])) best = [i, d];
  }
  return best;
}
function lsShapeAt(x, y){
  // (the shape under the mouse: its line, a stamp's ring, a spring's dot; the topmost first)
  const P = LM.plan; if (!P) return -1;
  for (let i = P.layers.length - 1; i >= 0; i--){
    const L = P.layers[i], [sx, sy] = toScreen(L.pts[0][0], L.pts[0][1]);
    if (L.kind === 'stamp'){
      // (the ring, an oval when stretched: the mouse's offset turned into the stamp's frame, the long way shrunk back)
      const st = Math.max(1, +(L.p.stretch || 1)), a = (+(L.p.turn || 0)) * Math.PI / 180, dx = x - sx, dy = -(y - sy);
      const lx = (dx * Math.cos(a) + dy * Math.sin(a)) / st, ly = -dx * Math.sin(a) + dy * Math.cos(a);
      if (Math.abs(Math.hypot(lx, ly) - (L.p.radius || 8192) * W.cam.z) <= 7) return i; continue;
    }
    if (LS_KINDS[L.kind].point){ if (Math.hypot(sx - x, sy - y) <= 8) return i; continue; }
    if (lsSegHit(L, x, y) || lsPointAt(L, x, y) >= 0) return i;
  }
  return -1;
}
// (a point under the mouse: the nearest within LS_GRAB pixels, not the first in the list, so of two points lying
// together the one nearer the mouse is taken; PIN2 found the points hard to get hold of)
const LS_GRAB = 11;
function lsPointAt(L, x, y, skip){
  let best = -1, bd = LS_GRAB;
  L.pts.forEach((p, i) => { if (i === skip) return; const [sx, sy] = toScreen(p[0], p[1]), d = Math.hypot(sx - x, sy - y); if (d <= bd){ bd = d; best = i; } });
  return best;
}
// (the picked shape's frame: a box round it in screen pixels, with corners that size it, a knob over it that turns it and a
// cross in its middle that moves it, all round its middle. PIN2 wanted to move, turn and resize a whole shape)
function lsFrame(L){
  if (!L || L.kind === 'stamp' || LS_KINDS[L.kind].point || L.pts.length < 2) return null;
  const s = L.pts.map(p => toScreen(p[0], p[1]));
  const x0 = Math.min(...s.map(p => p[0])) - 14, x1 = Math.max(...s.map(p => p[0])) + 14, y0 = Math.min(...s.map(p => p[1])) - 14, y1 = Math.max(...s.map(p => p[1])) + 14;
  const c = [L.pts.reduce((a, p) => a + p[0], 0) / L.pts.length, L.pts.reduce((a, p) => a + p[1], 0) / L.pts.length];
  return {x0, x1, y0, y1, c, cs: toScreen(c[0], c[1]), knob: [(x0 + x1) / 2, y0 - 26], corners: [[x0, y0], [x1, y0], [x0, y1], [x1, y1]]};
}
function lsFrameAt(L, x, y){
  const F = lsFrame(L); if (!F) return null;
  if (Math.hypot(F.knob[0] - x, F.knob[1] - y) <= 9) return {how: 'turn', F};
  if (F.corners.some(([cx, cy]) => Math.abs(cx - x) <= 7 && Math.abs(cy - y) <= 7)) return {how: 'size', F};
  if (Math.hypot(F.cs[0] - x, F.cs[1] - y) <= 10) return {how: 'move', F};
  return null;
}
const lsNeed = L => L.kind === 'stamp' || LS_KINDS[L.kind].point ? 1 : LS_KINDS[L.kind].closed ? 3 : 2;
function lsTakePoint(L, i){
  const need = lsNeed(L);
  if (L.pts.length <= need){ toast(`A ${LS_KINDS[L.kind].label.toLowerCase()} needs ${need} point${need === 1 ? '' : 's'} at least.`, true); return false; }
  L.pts.splice(i, 1); return true;
}
function lmHandleDown(e){
  const P = LM.plan, L = P && P.layers[LM.sel];
  if (!LM.show || !P || W.mode) return false;
  if (L){
    // (a castle's gate arrows: the gate to that side)
    const ga = typeof csGateAt === 'function' && csGateAt(L, e.offsetX, e.offsetY);
    if (ga){ csGatePick(L, ga.ang); return true; }
    const fr = lsFrameAt(L, e.offsetX, e.offsetY);
    if (fr){
      const [wx, wy] = toWorld(e.offsetX, e.offsetY);
      LM.hdrag = {L, xf: fr.how, c: fr.F.c, from: [wx, wy], orig: L.pts.map(p => p.slice())}; return true;
    }
    const i = lsPointAt(L, e.offsetX, e.offsetY);
    if (i >= 0){
      // (Ctrl+click or a double-click takes a point out)
      if (e.ctrlKey || e.detail >= 2){ if (lsTakePoint(L, i)){ LM.hover = -1; lsChanged(true); } return true; }
      LM.hdrag = {L, i}; return true;
    }
    const seg = lsSegHit(L, e.offsetX, e.offsetY);
    if (seg){
      const [wx, wy] = toWorld(e.offsetX, e.offsetY);
      if (e.shiftKey){ LM.hdrag = {L, move: true, from: [wx, wy], orig: L.pts.map(p => p.slice())}; return true; }
      L.pts.splice(seg[0] + 1, 0, [Math.round(wx), Math.round(wy)]);
      LM.hdrag = {L, i: seg[0] + 1, moved: true}; drawMap(); return true;
    }
  }
  const hit = lsShapeAt(e.offsetX, e.offsetY);
  if (hit >= 0 && hit !== LM.sel){ LM.sel = hit; renderWside(); drawMap(); return true; }
  return false;
}
function lmHandleMove(e){
  const H = LM.hdrag;
  if (!H){
    // (what the mouse is over on the picked shape, shown by the pointer and a ring: a point to drag, its line to
    // add one)
    const P = LM.plan, L = LM.show && P && !W.mode && P.layers[LM.sel];
    const fr = L ? lsFrameAt(L, e.offsetX, e.offsetY) : null;
    const pt = L && !fr ? lsPointAt(L, e.offsetX, e.offsetY) : -1, seg = L && !fr && pt < 0 ? lsSegHit(L, e.offsetX, e.offsetY) : null;
    const ga = L && typeof csGateAt === 'function' && csGateAt(L, e.offsetX, e.offsetY);
    const cur = ga ? 'pointer' : fr ? {turn: 'alias', size: 'nwse-resize', move: 'move'}[fr.how] : pt >= 0 ? 'grab' : seg ? (e.shiftKey ? 'move' : 'copy') : '';
    if (e.target && e.target.style && e.target.style.cursor !== cur && (cur || LM.hoverCur)) e.target.style.cursor = cur;
    LM.hoverCur = cur;
    if (pt !== (LM.hover ?? -1)){ LM.hover = pt; drawMap(); }
    return false;
  }
  const [wx, wy] = toWorld(e.offsetX, e.offsetY);
  if (H.xf){
    const [cx, cy] = H.c, [fx, fy] = H.from;
    if (H.xf === 'move') H.L.pts = H.orig.map(p => [Math.round(p[0] + wx - fx), Math.round(p[1] + wy - fy)]);
    else if (H.xf === 'size'){
      const k = Math.max(0.05, Math.hypot(wx - cx, wy - cy) / Math.max(1, Math.hypot(fx - cx, fy - cy)));
      H.L.pts = H.orig.map(p => [Math.round(cx + (p[0] - cx) * k), Math.round(cy + (p[1] - cy) * k)]);
    } else {
      // (Shift: in 15° steps)
      let a = Math.atan2(wy - cy, wx - cx) - Math.atan2(fy - cy, fx - cx);
      if (e.shiftKey) a = Math.round(a / (Math.PI / 12)) * Math.PI / 12;
      const c = Math.cos(a), s = Math.sin(a);
      H.L.pts = H.orig.map(p => [Math.round(cx + (p[0] - cx) * c - (p[1] - cy) * s), Math.round(cy + (p[0] - cx) * s + (p[1] - cy) * c)]);
    }
    if (e.target && e.target.style) e.target.style.cursor = 'grabbing';
    H.moved = true; drawMap(); return true;
  }
  if (H.move){
    const dx = wx - H.from[0], dy = wy - H.from[1];
    H.L.pts = H.orig.map(p => [Math.round(p[0] + dx), Math.round(p[1] + dy)]);
  } else {
    H.L.pts[H.i] = H.L.kind === 'wall' ? lsWallSnap(H.L.pts, H.i, wx, wy, lsWallStep(H.L)) : [Math.round(wx), Math.round(wy)];
    // (dropped on another point of the shape it joins it: PIN2 wanted points merged back by dragging one onto
    // its neighbour)
    H.onto = lsPointAt(H.L, e.offsetX, e.offsetY, H.i);
  }
  if (e.target && e.target.style) e.target.style.cursor = 'grabbing';
  H.moved = true; drawMap();
  return true;
}
function lmHandleUp(){
  const H = LM.hdrag; LM.hdrag = null;
  if (H && H.onto >= 0 && !H.move){
    if (lsTakePoint(H.L, H.i)) toast('Points joined.');
    else H.L.pts[H.i] = H.L.pts[H.onto].slice();
  }
  if (H && H.moved) lsChanged(true);
}

// ----- undo and redo for the plan's shapes and settings (the plan is kept outside the mod's Undo): the plan as it
// stood, saved a moment after each change settles, so a slider's drag is one step
LM.hist = []; LM.fut = [];
function lsHistNote(){
  clearTimeout(LM.histT);
  LM.histT = setTimeout(() => {
    const s = JSON.stringify(LM.plan);
    if (LM.histCur == null){ LM.histCur = s; return; }
    if (s === LM.histCur) return;
    LM.hist.push(LM.histCur); if (LM.hist.length > 60) LM.hist.shift();
    LM.histCur = s; LM.fut = [];
    lsHistButtons();
  }, 600);
}
function lsHistGo(back){
  clearTimeout(LM.histT);
  const now = JSON.stringify(LM.plan);
  if (back && LM.histCur != null && now !== LM.histCur){
    // (a change not settled yet, made just now: that is the step ↶ takes back, not the one before it)
    LM.fut = [now]; LM.plan = JSON.parse(LM.histCur);
  } else {
    const from = back ? LM.hist : LM.fut, to = back ? LM.fut : LM.hist;
    if (!from.length) return;
    to.push(now);
    LM.plan = JSON.parse(from.pop());
  }
  LM.histCur = JSON.stringify(LM.plan);
  if (LM.sel != null && LM.sel >= LM.plan.layers.length) LM.sel = null;
  LM.histSkip = true; lsChanged(true); LM.histSkip = false;
}
// Ctrl+Z / Ctrl+Y (Ctrl+Shift+Z) on the shapes while the Land panel shows them and a shape edit was the last thing
// done; after Shape them (or any change to the mod since) they are the mod's Undo as everywhere (PIN2: "Control Z
// doesn't work with the terrain layer tool")
function lsKey(e){
  const ctrl = e.ctrlKey || e.metaKey, k = (e.key || '').toLowerCase();
  if (!ctrl || (k !== 'z' && k !== 'y') || cfTyping(e) || document.querySelector('.modal-bg')) return false;
  if (!LM.plan || !(typeof PNL !== 'undefined' && PNL.isShown && PNL.isShown('world', 'land'))) return false;
  if (!(LM.editAt && LM.editAt > (LM.modAt || 0))) return false;
  const back = k === 'z' && !e.shiftKey;
  if (back ? !(LM.hist.length || (LM.histCur != null && JSON.stringify(LM.plan) !== LM.histCur)) : !LM.fut.length) return false;
  e.preventDefault(); e.stopPropagation();
  lsHistGo(back); LM.editAt = Date.now();
  toast(back ? 'Shapes: undone' : 'Shapes: redone');
  return true;
}
function lsHistButtons(){
  const u = $('#ls-undo'), r = $('#ls-redo');
  if (u) u.disabled = !LM.hist.length;
  if (r) r.disabled = !LM.fut.length;
}

// the objects of the cells already loaded read again after the ground changed: the rocks set and the things that
// followed the ground showed where they were until the place was opened again (2026-11-08); as Dress does
async function lmReloadObjects(){
  for (const k of Object.keys(W.cells)) if (W.cells[k] && W.cells[k].exists) await worldReloadCell(k);
}
async function lsApply(btn){
  if (!await needProject()) return;
  btn.disabled = true; btn.textContent = `Shaping ${LM.data.marks.length} cell${LM.data.marks.length === 1 ? '' : 's'}…`;
  await lmKeepBefore('shaping');
  // (a bar on the Shape buttons, filled as the server says how far it has got: PIN2 2026-10-30, "so I know it's
  // actually still shaping it and the program didn't break". landshapes.PROGRESS)
  const poll = setInterval(async () => {
    let p; try { p = await api('/api/land/progress'); } catch (e){ return; }
    if (!p || !p.on) return;
    const pct = Math.round(p.frac * 100);
    for (const b of document.querySelectorAll('#ls-apply, #ls-apply-top')){
      b.disabled = true; b.textContent = `${p.what}… ${pct}%`; b.title = 'Shaping: ' + p.what;
      b.style.background = `linear-gradient(90deg, var(--gold) ${pct}%, transparent ${pct}%)`; b.classList.add('pbar');
    }
  }, 600);
  try {
    const r = await post('/api/land/plan/apply', {cells: LM.data.marks, plan: LM.plan});
    clearInterval(poll);
    toast(`Shaped ${r.cells} cell${r.cells === 1 ? '' : 's'}${r.tiles ? ` in ${r.tiles} tiles` : ''}${r.new ? ` (${r.new} new)` : ''}${r.eased ? `; ${r.eased} steps too steep for the game eased` : ''}${r.moved ? `; ${r.moved} objects followed the ground` : ''}${r.shaded && r.shaded.length ? '; shaded' : ''}${r.rocks ? `; ${r.rocks} rocks set` : ''}${r.trees_out || r.trees_grown ? `; trees into groves (${r.trees_out} out, ${r.trees_grown} grown)` : ''}${r.plants ? `; ${r.plants} plants` : ''}${r.falls ? `; ${r.falls} waterfall${r.falls === 1 ? '' : 's'}` : ''}${r.roads ? `; ${r.roads} road${r.roads === 1 ? '' : 's'} laid` : ''}${r.clad_pending ? '; the cliff cladding is still learning the game\'s rocks, shape again later for it' : ''}${r.assigned ? `; ${r.assigned} put in the region` : ''}. Changes to the ground show in game after a restart.`);
    // (the land made, against the region's own figures from the land survey)
    const m = r.measured || {}, figs = Object.entries(r.region_figures || {});
    if (figs.length && m.slope){
      const [rn, f] = figs[0];
      LM.applyNote = `Made: slopes ${m.slope['50']}° / ${m.slope['90']}° / ${m.slope['99']}° (half, 90%, 99% under), ${Math.round(m.over45 * 100)}% over 45°, roughness ${m.rough['128']} / ${m.rough['1024']}${r.textures_a_cell ? `, ${r.textures_a_cell} textures a cell` : ''}. ` +
        `The ${rn.replace(/ region$/, '').replace(/\b\w/g, c => c.toUpperCase())} region's own land: ${f.slope['50']}° / ${f.slope['90']}° / ${f.slope['99']}°, ${Math.round((f.over45 || 0) * 100)}%, ${f.rough['128']} / ${f.rough['1024']}, ${f.tex_per_cell || '?'}.`;
    }
    LM.prev = null; LM.prevData = null;
    W.lands = {}; if (typeof v3LandsReload === 'function') v3LandsReload();
    await afterChange(); await lmLoad(true, true);
    await lmReloadObjects();
    await loadAround(Math.floor(W.cam.x / CELL), Math.floor(W.cam.y / CELL));
    LM.prevOn = false;                                 // (the land is shaped now: the map shows it as it is)
    LM.shapedOnce = true;
    lmFlowSoon(); drawMap(); renderWside();
    return true;
  } catch (err){ const n = $('#ls-note'); if (n) n.textContent = err.message; else toast(err.message, true); btn.disabled = false; btn.textContent = 'Shape the marked cells'; return false; }
  finally {
    clearInterval(poll);
    for (const b of document.querySelectorAll('#ls-apply, #ls-apply-top')) b.style.background = '';
  }
}
// (what the pinned button does: the ground shapes, and the towns, each drawn and ticked)
function lsPinWhat(){
  const on = LM.plan && LM.plan.layers ? LM.plan.layers.filter(L => L.on !== false && L.pts && L.pts.length) : [];
  return {ground: on.filter(L => !lsNoShape(L.kind) || L.kind === 'road').length + (lsTerrOn() ? 1 : 0), towns: on.filter(L => L.kind === 'town'), castles: on.filter(L => L.kind === 'castle')};
}
// (a town or castle the page knows it built this session)
function lsKnownBuilt(L){
  return !!((((L.kind === 'castle' ? LM.castles : LM.towns) || {})[L.id]) || {}).built;
}
// (whether the mod has a town or castle built at the layer's outline: asked of the mod, not the page, so a town built
// before a reload, or taken back by Undo or Remove since, counts as it stands; the remove's own count, look only)
async function lsBuiltAt(L){
  const C = L.kind === 'castle' ? (LM.castles || {})[L.id] : (LM.towns || {})[L.id];
  const out = L.kind === 'castle' && C && C.plan && C.plan.preview && C.plan.preview.outline && C.plan.preview.outline.length ? C.plan.preview.outline : L.pts;
  let n = null;
  try { n = await post(L.kind === 'castle' ? '/api/castle/remove' : '/api/town/remove', {outline: out, look: true}); } catch (e){ n = null; }
  const yes = !!(n && n.things > 0);
  if (C) C.built = yes;
  return yes;
}
async function lsDoAll(btn){
  const {ground, towns, castles} = lsPinWhat();
  // (a town or castle already built at its outline is left as it is: every press built each one again, a second copy
  // on top of the first, while the region pass or a proposed road kept the button live; the user's own towns built
  // before Propose places, 2026-11-08)
  const done = new Set(), left = [];
  for (const L of towns.concat(castles)) if (await lsBuiltAt(L)){ done.add(L.id); left.push(L.p.name || L.name || (L.kind === 'castle' ? 'a castle' : 'a town')); }
  if (ground && !await lsApply(btn)) return;
  for (const L of towns){
    if (done.has(L.id)) continue;
    const b = $('#ls-apply-top') || btn;
    if (!await lsMakeTown(L, '#ls-apply-top')) break;
    if (b) b.disabled = true;
  }
  // (then the castles, in the order drawn: a castle meeting a town's wall is laid against it, townwalls.drop_doubled)
  for (const L of castles){
    if (done.has(L.id)) continue;
    const b = $('#ls-apply-top') || btn;
    if (b){ b.disabled = true; b.innerHTML = '<span class="spin"></span>Building the castle…'; }
    if (typeof csMake !== 'function' || !await csMake(L)) break;
  }
  if (left.length) toast(`Left ${left.length === 1 ? esc(left[0]) : left.length + ' towns and castles'} as built: ✕ Remove the town (or castle) first to build it anew.`);
  renderWside();
}
async function lmRaise(btn){
  if (!await needProject()) return;
  const cells = LM.data.marks.slice(); if (!cells.length) return;
  btn.disabled = true; btn.textContent = `Raising ${cells.length} cell${cells.length === 1 ? '' : 's'}…`;
  try {
    const r = await post('/api/land/raise', {cells, height: LM.height, coast: LM.coast, rough: LM.rough, paint: LM.paint});
    toast(`Raised ${r.cells} cell${r.cells === 1 ? '' : 's'} into land${r.new ? ` (${r.new} new)` : ''}${r.painted_as.length ? ', textured like the ' + r.painted_as.map(s => s.replace(/ region$/, '')).join(' and ') : ''}${r.eased ? `; ${r.eased} steps too steep for the game eased` : ''}${r.moved ? `; ${r.moved} objects followed it` : ''}. Changes to the ground show in game after a restart.`);
    W.lands = {}; if (typeof v3LandsReload === 'function') v3LandsReload();
    await afterChange(); await lmLoad(true, true);
    await lmReloadObjects();
    await loadAround(Math.floor(W.cam.x / CELL), Math.floor(W.cam.y / CELL));
    drawMap(); renderWside();
  } catch (err){ toast(err.message, true); btn.disabled = false; btn.textContent = 'Raise the marked cells into land'; }
}

// ----- Dress: the marked cells' land dressed as the game dresses the region's (landdecor.dress_all): rocks and
// cliffs turned to their slopes, and the region's own squares of trees, plants, grass and logs
// shapes with an outline that dressing can keep to (not towns)
// a cliff along a drawn line (cliffline.py): the region's cliff rocks chained along it, facing the drop; one Undo
async function lsLayCliff(L, btn){
  if (!await needProject()) return;
  const p = L.p || {};
  const pieces = p.pick ? selectionRefs().map(([c, r]) => r.id).filter(id => /rock|stone|boulder|cliff|crag/i.test(id)) : [];
  p.seed = (p.seed || 0) + 1;
  if (btn){ btn.disabled = true; btn.innerHTML = '<span class="spin"></span>Laying…'; }
  try {
    const r = await post('/api/land/cliff', {pts: L.pts, side: p.side || 0, height: p.height || 600, amount: p.amount != null ? p.amount : 1, like: L.like || '', pieces, raise: !!p.raise, seed: p.seed, clad: p.clad !== 0});
    if (!r.rocks) toast(r.why ? `Nothing laid: ${r.why}.` : 'Nothing laid.', true);
    else toast(`Laid ${r.rocks} rocks (${r.parts.face} face, ${r.parts.foot} foot, ${r.parts.crest} crest${r.clad ? `, ${r.clad} on the slopes` : ''})${r.region ? ', like ' + r.region : ''}${r.raised ? ', land raised behind' : ''}. Undo takes them back.`);
    lsChanged();
    await afterChange();
    for (const k of Object.keys(W.cells)) if (W.cells[k] && W.cells[k].exists) await worldReloadCell(k);
    drawMap(); renderWside(); if (typeof v3Refresh === 'function' && V3.on) v3Refresh();
  } catch (err){ toast(err.message, true); if (btn){ btn.disabled = false; btn.textContent = '🪨 Lay the cliff'; } }
}
function lmDressRings(){
  return (LM.plan && LM.plan.layers || []).map((L, i) => ({L, i}))
    .filter(o => LS_KINDS[o.L.kind] && LS_KINDS[o.L.kind].closed && !LS_KINDS[o.L.kind].town && !lsIsField(o.L.kind) && o.L.pts && o.L.pts.length >= 3);   // (never inside a farm or orchard)
}
// the cells an outline reaches (the server keeps to the outline itself)
function lmRingCells(pts){
  const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]), out = [];
  for (let x = Math.floor(Math.min(...xs) / CELL); x <= Math.floor(Math.max(...xs) / CELL); x++)
    for (let y = Math.floor(Math.min(...ys) / CELL); y <= Math.floor(Math.max(...ys) / CELL); y++) out.push(x + ',' + y);
  return out;
}
async function lmDressAsk(){
  if (!await needProject()) return;
  // (a ▢ Dress area is enough on its own: it marks no cells, and Dress… stayed grey with only an area drawn, 2026-11-02)
  const cells = (LM.data && LM.data.marks || []).slice();
  if (!cells.length && !lmDressRings().length) return;
  let looks = [], mine = [];
  try { looks = (await api('/api/land/looks')).looks; } catch (e){}
  // (your own scatter brushes can be what grows, PIN2 on Discord 2026-11-01)
  try { mine = (await api('/api/scatter/sets?cell=')).sets.filter(s => s.mine); } catch (e){}
  // (shapes with an outline: dress only inside one; the picked one, else the first Dress area)
  const rings = lmDressRings();
  const pick = rings.find(o => o.i === LM.sel) || rings.find(o => o.L.kind === 'area');
  const D = LM.dress = LM.dress || {rocks: true, clad: true, growth: true, amt: 1, like: '', brush: ''};
  if (D.clad == null) D.clad = true;
  if (D.brush && !mine.some(s => s.key === D.brush)) D.brush = '';
  const bg = document.createElement('div'); bg.className = 'modal-bg';
  bg.innerHTML = `<div class="modal" style="width:min(440px,92vw)"><h3 style="margin-top:0">🪨 Dress ${cells.length ? cells.length + ' cell' + (cells.length === 1 ? '' : 's') : 'an area'}</h3>
    <div class="msg" style="display:flex;gap:14px">
      <label title="The region's rocks and cliffs, as thick as the game sets them on such ground, turned to their slopes"><input type="checkbox" id="lmd-rocks" ${D.rocks ? 'checked' : ''}> Rocks & cliffs</label>
      <label title="The steep ground clad the way the game's gorges and hilltops are: big faces, rocks on the lip and at the foot, banks, outcrops on knolls; no bottom edge left showing"><input type="checkbox" id="lmd-clad" ${D.clad ? 'checked' : ''}> Steep faces</label>
      <label title="Trees, plants, grass and logs: the region's own squares of land, laid where the ground is like theirs"><input type="checkbox" id="lmd-grow" ${D.growth ? 'checked' : ''}> Trees & plants</label></div>
    <label class="msg" style="display:flex;gap:8px;align-items:center;margin-top:8px" title="Whose look: the land nearest (each cell's own region, or for open sea the nearest region with land), or one region's for all">Like
      <select id="lmd-like" style="flex:1"><option value="">The land nearest</option>${looks.map(o => `<option value="${esc(o.region)}">${esc(o.name)}</option>`).join('')}</select></label>
    ${mine.length ? `<label class="msg" style="display:flex;gap:8px;align-items:center;margin-top:8px" title="What the trees and plants are: the region's own, or one of your scatter brushes, spread at its own spacing">Grow
      <select id="lmd-brush" style="flex:1"><option value="">The region's own</option>${mine.map(s => `<option value="${esc(s.key)}" ${s.key === D.brush ? 'selected' : ''}>★ ${esc(s.label)}</option>`).join('')}</select></label>` : ''}
    <label class="msg" style="display:flex;gap:8px;align-items:center;margin-top:8px" title="1: as thickly as the game dresses such land">Amount
      <input type="range" id="lmd-amt" min="0.25" max="2" step="0.25" value="${D.amt}" style="flex:1"><span id="lmd-amtv">${D.amt}</span></label>
    ${rings.length ? `<label class="msg" style="display:flex;gap:8px;align-items:center;margin-top:8px" title="Only the land inside a shape's outline, or all the marked cells">Where
      <select id="lmd-ring" style="flex:1">${cells.length ? '<option value="">All marked cells</option>' : ''}${rings.map(o => `<option value="${o.i}" ${pick === o ? 'selected' : ''}>Inside ${esc(o.L.name || LS_KINDS[o.L.kind].label)}</option>`).join('')}</select></label>` : ''}
    <div class="msg" style="font-size:11.5px;margin-top:6px">The first time with a region takes a few seconds.</div>
    <div class="foot"><button class="btn" id="lmd-no">Cancel</button><button class="btn primary" id="lmd-ok">Dress</button></div></div>`;
  document.body.appendChild(bg);
  const close = () => bg.remove();
  bg.querySelector('#lmd-no').onclick = close;
  bg.onclick = e => { if (e.target === bg) close(); };
  const amt = bg.querySelector('#lmd-amt');
  amt.oninput = () => { bg.querySelector('#lmd-amtv').textContent = amt.value; };
  bg.querySelector('#lmd-like').value = D.like || '';
  bg.querySelector('#lmd-ok').onclick = async () => {
    const ok = bg.querySelector('#lmd-ok');
    D.rocks = bg.querySelector('#lmd-rocks').checked; D.growth = bg.querySelector('#lmd-grow').checked; D.clad = bg.querySelector('#lmd-clad').checked;
    D.like = bg.querySelector('#lmd-like').value; D.amt = +amt.value;
    const bs = bg.querySelector('#lmd-brush'); D.brush = bs ? bs.value : '';
    if (!D.rocks && !D.growth) return toast('Pick rocks, trees and plants, or both.', true);
    const rs = bg.querySelector('#lmd-ring'), ring = rs && rs.value !== '' ? LM.plan.layers[+rs.value].pts : null;
    const send = ring ? lmRingCells(ring) : cells;
    ok.disabled = true; ok.innerHTML = '<span class="spin"></span>Dressing…';
    try {
      const r = await post('/api/land/dress', {cells: send, like: D.like, parts: {rocks: D.rocks ? D.amt : 0, clad: D.rocks && D.clad ? D.amt : 0, growth: D.growth ? D.amt : 0}, outline: ring, brush: D.growth ? D.brush : ''});
      close();
      const what = [r.growth ? `${r.growth} trees and plants` : '', r.rocks ? `${r.rocks} rocks` : ''].filter(Boolean).join(' and ');
      toast(what ? `Set ${what} in ${r.cells} cell${r.cells === 1 ? '' : 's'}${r.looks.length ? ', like ' + r.looks.join(', ') : ''}. Undo takes them back.`
                 : 'Nothing to set: the land is flat, bare in that region, or under water there.');
      await afterChange();
      for (const k of Object.keys(W.cells)) if (W.cells[k] && W.cells[k].exists) await worldReloadCell(k);
      drawMap(); renderWside(); if (typeof v3Refresh === 'function' && V3.on) v3Refresh();
    } catch (err){ toast(err.message, true); ok.disabled = false; ok.textContent = 'Dress'; }
  };
}
