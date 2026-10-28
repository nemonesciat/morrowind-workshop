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
    if (!LM.plan || (force && !keepPlan)) LM.plan = d.plan || {layers: [], rough: 1, fade: 1024, paint: true, seed: 1};
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
    if (LM.prevStale && D.marks.length){
      g.font = '12px sans-serif'; g.textAlign = 'center';
      const t = 'Updating the preview…', w = g.measureText(t).width + 16;
      g.fillStyle = 'rgba(0,0,0,0.6)'; g.fillRect(W.w / 2 - w / 2, 8, w, 22);
      g.fillStyle = '#fff'; g.fillText(t, W.w / 2, 23); g.textAlign = 'start';
    }
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
  try {
    lmMarksAre((await post('/api/land/marks', D.add ? {add: cells} : {remove: cells})).marks);
  } catch (err){ toast(err.message, true); await lmLoad(true, true); }
  drawMap(); if (PNL.isShown('world', 'land')) renderWside();
}
// the marks as the server now has them, and the plan's preview over them asked for again
function lmMarksAre(marks){
  LM.data.marks = marks; LM.data.marked = new Set(marks);
  if (LM.plan && LM.plan.layers.length) lsPreviewSoon();
}

// ----- the Land panel outdoors: the land map and shaping
function lmViewHtml(i){
  if (!i || i.interior) return '';
  const D = LM.data, n = D ? D.marks.length : 0;
  const counts = {};
  if (D) for (const k of D.marks){ const c = D.cells[k]; const lv = c ? c[0] : D.own[k] ? 'yours' : 'none'; counts[lv] = (counts[lv] || 0) + 1; }
  const what = Object.entries(counts).map(([lv, m]) => `${m} ${lv === 'none' ? 'with no land yet' : lv === 'yours' ? 'of your own land' : LM_LEVELS[lv].label.toLowerCase()}`).join(', ');
  // (the shapes' own Shape button, pinned at the top while there are shapes: at the bottom of the panel, under the
  // passes and the dressing, the user didn't find it and asked whether the sliders applied themselves, 2026-10-28)
  const nl = LM.plan && LM.plan.layers ? LM.plan.layers.filter(L => L.on !== false).length : 0;
  const bar = nl ? `<div class="ls-pin"><span class="msg">${nl} shape${nl === 1 ? '' : 's'} · ${n ? `${n} cell${n === 1 ? '' : 's'} marked` : 'no cells marked'}<br><span style="color:var(--faint)">Sliders change the preview only</span></span>
    <button class="btn sm primary" id="ls-apply-top" ${n ? '' : 'disabled'} title="Write the shapes into the marked cells: one Undo takes it back">Shape them</button></div>` : '';
  return `${bar}<h3>Land shaping${lsGuide('Land shaping: how it works')}</h3>
    <label class="msg" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="lm-show" ${LM.show ? 'checked' : ''}> Show the land map</label>
    ${D && D.learning ? '<div class="msg" style="font-size:11.5px">Still learning the game\'s land (about a minute)…</div>' : ''}
    <div class="lm-legend">${Object.entries(LM_LEVELS).map(([k, L]) => `<span title="${esc(L.note)}"><i style="background:${L.fill}"></i>${esc(L.label)}</span>`).join('')}
      <span title="Land from another mod (Project Tamriel's, say): your mod would override it"><i class="lm-hatch"></i>Another mod's</span>
      <span title="Land your mod made or changed"><i style="border:1px dashed rgba(190,130,255,0.9)"></i>Yours</span>
      <span title="No land in any plugin yet, next to land: room to grow"><i style="border:1px dashed rgba(140,200,255,0.8)"></i>Room to grow</span></div>
    <div class="actions" style="margin-top:6px"><button class="btn sm" id="lm-mark">⛰ Mark cells…</button><button class="btn sm" id="lm-clear" ${n ? '' : 'disabled'}>Clear marks</button></div>
    <div class="msg" style="font-size:11.5px">${n ? `${n} cell${n === 1 ? '' : 's'} marked${what ? ': ' + esc(what) : ''}.` : 'Mark the cells to shape on the map.'}</div>
    ${n ? `<div class="lm-raise">
      <label>Height <input type="range" id="lm-h" min="0" max="6000" step="50" value="${LM.height}"><span>${LM.height}</span></label>
      <label title="How far in from the edge of the marked cells the land reaches its height">Coast width <input type="range" id="lm-c" min="2048" max="16384" step="256" value="${LM.coast}"><span>${LM.coast}</span></label>
      <label title="Rolling ground on top, as rough as the game's land (1) or smoother or rougher">Roughness <input type="range" id="lm-r" min="0" max="2" step="0.1" value="${LM.rough}"><span>${LM.rough}</span></label>
      <label class="msg" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="lm-p" ${LM.paint ? 'checked' : ''}> Texture it the way the region's land is</label>
      <div class="actions"><button class="btn sm primary" id="lm-raise">Raise the marked cells into land</button></div>
      <div class="msg" style="font-size:11.5px">Cells with no land get some first (the sea bed). The edges with unmarked cells stay as they are. One Undo takes it back; then shape it further with ⛰ Ground in 3D.</div></div>` : ''}
    ${n || (LM.plan && LM.plan.layers && LM.plan.layers.length) ? lsHtml() : ''}
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
      await afterChange(); await lmLoad(true);
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
  const mk = $('#lm-mark'); if (mk) mk.onclick = async () => { if (V3.on) await v3Enable(false); lmMark(); };
  const cl = $('#lm-clear'); if (cl) cl.onclick = async () => {
    if (!await needProject()) return;
    lmMarksAre((await post('/api/land/marks', {clear: true})).marks); drawMap(); renderWside();
  };
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
  coast:   {icon: '🏝', label: 'Coast', color: '#7fd1ff', closed: true, how: 'Click along the shore all the way round the land; double-click to close it (the last point joins the first). The outline becomes the waterline: inside rises out of the sea.'},
  ridge:   {icon: '⛰', label: 'Ridge', color: '#e8d27a', how: 'Click along the crest, double-click to finish. A range rises along it.'},
  river:   {icon: '〰', label: 'River', color: '#4aa8ff', how: 'Click from the source down to the sea, double-click to finish. Its bed is dug under the water all along (the game has one water level).'},
  valley:  {icon: '⌄', label: 'Valley', color: '#b6e08a', how: 'Click along the valley floor, double-click to finish. A dry trough.'},
  plateau: {icon: '▭', label: 'Plateau', color: '#f0a060', closed: true, how: 'Click round the top, double-click to close. A level top with a cliff round it.'},
  lake:    {icon: '◍', label: 'Lake', color: '#58c8e8', closed: true, how: 'Click round the shore, double-click to close. A basin under the water line.'},
  stamp:   {icon: '◉', label: 'Stamp', color: '#ff8fb8', how: 'Click where it goes: a volcano, a crater, a dome, or a piece of the game\'s own land.'},
  spring:  {icon: '⇣', label: 'Spring', color: '#5fd0ff', point: true, how: 'Click where a river rises. It finds its own way down to the water.'},
};
// sliders per kind: [param, label, min, max, step, tip]
const LS_PARAMS = {
  coast: [['height', 'Height', 0, 6000, 50, 'How high the land stands a coast width in from the water'], ['width', 'Coast width', 1024, 16384, 256, 'How far it takes to rise out of the sea'], ['wander', 'Wander', 0, 2, 0.1, 'Small bays and headlands along the waterline (a few hundred units either side of the line drawn)']],
  ridge: [['height', 'Crest', 500, 12000, 100, 'The crest\'s height (lower at the ends)'], ['width', 'Width', 1024, 24576, 256, 'From the crest out to its foot'], ['sharp', 'Sharp', 0, 1, 0.05, '0 rounded hills, 1 a knife-edge crest'], ['spurs', 'Spurs', 0, 2, 0.1, 'How much its width wanders, in spurs and gullies'],
    ['crags', 'Crags', 0, 2, 0.1, 'Sharp crags and arêtes near the crest (0: smooth)']],
  river: [['depth', 'Bed depth', 64, 1024, 16, 'How far under the water its bed lies'], ['width', 'Bed width', 64, 1536, 32, 'Half the width of its bed'], ['banks', 'Banks', 256, 8192, 128, 'How far out its banks reach the ground']],
  valley: [['depth', 'Depth', 100, 4000, 50, 'How deep below the ground (it stays above the water)'], ['width', 'Width', 1024, 16384, 256, 'From its floor out to the rim'], ['round', 'U or V', 0, 1, 0.05, '1 a rounded U, 0 a V']],
  plateau: [['height', 'Top', 0, 8000, 50, 'The height of its top'], ['width', 'Cliff', 128, 4096, 64, 'How far in from its edge the top is reached'], ['terraces', 'Terraces', 0, 6, 1, 'Steps up its sides']],
  lake: [['depth', 'Depth', 64, 2000, 16, 'How deep its middle is'], ['width', 'Shore', 256, 6144, 128, 'How far its shore slopes']],
  spring: [['rise', 'Water from', 0, 4000, 50, 'Above this height it is a dry ravine; below it, a river'], ['wander', 'Winding', 0, 2, 0.1, 'How much it winds where the land is flat'],
    ['depth', 'Bed depth', 64, 1024, 16, 'How far under the water its bed lies'], ['width', 'Bed width', 64, 1536, 32, 'Half the width of its bed'], ['banks', 'Banks', 256, 8192, 128, 'How far out its banks reach the ground']],
  stamp: [['radius', 'Radius', 1024, 32768, 256, 'How far it reaches'], ['height', 'Height', -6000, 12000, 50, 'Its height (a crater: its depth); for the game\'s land, 0 keeps it as it is'], ['turn', 'Turn', 0, 359, 1, 'Its turn (the game\'s land only)']],
};
const LS_SHAPES = [['volcano', 'Volcano'], ['cone', 'Cone'], ['caldera', 'Caldera'], ['crater', 'Crater'], ['dome', 'Dome'], ['mesa', 'Mesa'], ['game', 'The game\'s own land']];
const LS_DEFAULTS = {coast: {height: 600, width: 6144, wander: 1, sea: 0}, ridge: {height: 3500, width: 3072, sharp: 0.5, spurs: 1, crags: 0.6}, river: {depth: 256, width: 256, banks: 2048, canyon: 0},
  valley: {depth: 900, width: 4096, round: 0.6}, plateau: {height: 2000, width: 768, terraces: 0}, lake: {depth: 400, width: 1536},
  stamp: {shape: 'volcano', radius: 8192, height: 4000, turn: 0, src: null}, spring: {rise: 800, wander: 1, depth: 256, width: 256, banks: 2048, canyon: 0}};

function lsHtml(){
  const P = LM.plan || {layers: []}, sel = P.layers[LM.sel];
  const row = (L, i) => `<div class="ls-row${i === LM.sel ? ' on' : ''}" data-i="${i}"><input type="checkbox" data-on="${i}" ${L.on !== false ? 'checked' : ''} title="Use this shape">
      <span style="color:${LS_KINDS[L.kind].color}">${LS_KINDS[L.kind].icon}</span><span class="ls-n">${esc(L.name || LS_KINDS[L.kind].label)}</span>
      <button class="xbtn" data-up="${i}" title="Earlier (later shapes act on what earlier ones made)">↑</button><button class="xbtn" data-dn="${i}" title="Later">↓</button><button class="xbtn" data-del="${i}" title="Remove">✕</button></div>`;
  let params = '';
  if (sel){
    const p = sel.p || {};
    if (sel.kind === 'stamp') params += `<label>Shape <select class="inp" id="ls-shape">${LS_SHAPES.map(([v, t]) => `<option value="${v}" ${p.shape === v ? 'selected' : ''}>${t}</option>`).join('')}</select></label>`;
    if (sel.kind === 'stamp' && p.shape === 'game'){
      const s = p.src || ['', '', '', ''];
      params += `<label title="The game's cells to copy (their shape over their own surroundings), at most 6 x 6">Cells <input class="inp" data-src="0" type="number" value="${s[0]}" style="width:52px"><input class="inp" data-src="1" type="number" value="${s[1]}" style="width:52px"> to <input class="inp" data-src="2" type="number" value="${s[2]}" style="width:52px"><input class="inp" data-src="3" type="number" value="${s[3]}" style="width:52px"></label>
        <div class="actions"><button class="btn sm" id="ls-src-here" title="Copy the cell open now (and the ones round it)">Use the cell open now</button></div>`;
    }
    for (const [k, lab, mn, mx, st, tip] of LS_PARAMS[sel.kind]) params += `<label title="${esc(tip)}">${lab} <input type="range" data-p="${k}" min="${mn}" max="${mx}" step="${st}" value="${p[k] != null ? p[k] : LS_DEFAULTS[sel.kind][k]}"><span>${p[k] != null ? p[k] : LS_DEFAULTS[sel.kind][k]}</span></label>`;
    if (sel.kind === 'river' || sel.kind === 'spring') params += `<label class="msg" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="ls-canyon" ${p.canyon ? 'checked' : ''}> A canyon (steep walls)</label>`;
    if (sel.kind === 'coast') params += `<label class="msg" style="display:flex;gap:6px;align-items:center" title="Off: only a strip just outside the outline goes under water, and other land further out stays. On: all the land outside every coast in the marked cells sinks to the sea bed."><input type="checkbox" id="ls-sea" ${p.sea ? 'checked' : ''}> Sea outside (sink all other land)</label>`;
    // (where it acts, and whose character its ground takes; coasts are worked out together, so not for them)
    if (sel.kind !== 'coast'){
      params += `<label title="Only in one region of the marked cells, fading out at its border" style="white-space:nowrap">Only in ${lsRegionSel('ls-only', (sel.only || [])[0] || '', 'everywhere', lsHereRegions())}</label>
        <label title="Its ground as rough and steep as another region's land; the textures stay the cell's own region's">Like ${lsRegionSel('ls-like', sel.like || '', 'its own region')}</label>`;
    }
    params += `<div class="msg" style="font-size:11.5px">Drag its points on the map to move them.${LS_KINDS[sel.kind].closed ? ' A closed outline: the last point joins the first.' : ''}</div>`;
    // (whether the marked cells cover it: a shape only changes the marked cells)
    const sc = lsShapeCells(sel), M = LM.data ? LM.data.marked : new Set(), inM = sc.filter(k => M.has(k)).length;
    if (inM < sc.length) params += `<div class="msg warn" style="font-size:11.5px;margin-top:4px">${inM ? 'Partly outside the marked cells: only the marked part changes.' : 'Outside the marked cells: it changes nothing until they\'re marked.'}
      <button class="btn sm" id="ls-markit" title="Mark every cell this shape reaches (towns left out; Shift+click: them too)">⛰ Mark its cells</button></div>`;
  }
  return `<h3>Shapes${lsGuide('Step 2: draw shapes')}</h3>
    <div class="ls-add">${Object.entries(LS_KINDS).map(([k, K]) => `<button class="btn sm" data-add="${k}" title="${esc(K.how)}"><span style="color:${K.color}">${K.icon}</span> ${K.label}</button>`).join('')}</div>
    ${P.layers.length ? `<div class="ls-list">${P.layers.map(row).join('')}</div>
      <div class="actions"><button class="btn sm" id="ls-clearall" title="Take every shape off the map (the land already shaped stays as it is)">Clear shapes</button></div>` : '<div class="msg" style="font-size:11.5px">Draw coasts, ridges, rivers, valleys, plateaus, lakes and stamps on the marked cells. Each acts on what the ones above it made.</div>'}
    ${sel ? `<div class="lm-raise">${params}</div>` : ''}
    ${P.layers.length ? lsPassesHtml(P) : ''}
    ${P.layers.length ? `<div class="lm-raise">
      <label title="Rolling ground on the new land, as rough as the region's (1)">Roughness <input type="range" data-g="rough" min="0" max="2" step="0.1" value="${P.rough}"><span>${P.rough}</span></label>
      <label title="How far in from the marked cells' edge the shapes fade in (the edges with other cells never move)">Edge fade <input type="range" data-g="fade" min="256" max="8192" step="256" value="${P.fade}"><span>${P.fade}</span></label>
      ${lsHereRegions().length > 1 || (P.only || []).length ? `<label title="Shape only the marked cells in one region; the rest stay as they are" style="white-space:nowrap">Only in ${lsRegionSel('ls-ponly', (P.only || [])[0] || '', 'all marked cells', lsHereRegions())}</label>` : ''}
      <label class="msg" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="ls-paint" ${P.paint !== false ? 'checked' : ''}> Texture it the way the region's land is</label>
      <label class="msg" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="ls-prev" ${LM.prevOn !== false ? 'checked' : ''}> Preview on the map</label>
      <div class="actions"><button class="btn sm" id="ls-seed" title="The same shapes with other rolling ground and shores">🎲 Re-roll</button><button class="btn sm primary" id="ls-apply" ${LM.data && LM.data.marks.length ? '' : 'disabled title="Mark the cells to shape first"'}>Shape the marked cells</button></div>
      <div class="msg" id="ls-note" style="font-size:11.5px">${LM.data && !LM.data.marks.length ? 'No cells marked: ⛰ Mark cells to shape them.' : `${LM.applyNote ? esc(LM.applyNote) + ' ' : ''}One Undo takes it back. The shapes stay, to change and shape again.`}</div></div>` : ''}`;
}
// stage 3 and 4 (landpasses.py, landdress.py): the natural passes and the dressing, with the plan's own defaults
const LS_PASSES = {detail: true, detail_k: 1, settle: true, angle: 0, gullies: 0, terraces: false, tstep: 256, tsharp: 0.6, tslope: 20, valleys: 0,
  rock: 0, rthick: 512, rdip: 0, rdir: 0, rshare: 0.45, ronly: ''};
const LS_DRESS = {variety: -1, tints: true, seams: true, hollows: true, shade: 1, region: '', assign: false, rocks: 1};
function lsPassesHtml(P){
  const A = P.passes = Object.assign({}, LS_PASSES, P.passes || {}), D = P.dress = Object.assign({}, LS_DRESS, P.dress || {});
  const regs = (typeof REG !== 'undefined' && REG.data) ? REG.data.regions : [];
  const info = LM.prevInfo || {};
  const chk = (id, on, text, tip) => `<label class="msg" style="display:flex;gap:6px;align-items:center" title="${esc(tip)}"><input type="checkbox" id="${id}" ${on ? 'checked' : ''}> <span style="flex:1;min-width:0;text-align:left">${text}</span></label>`;
  const sl = (key, grp, lab, mn, mx, st, v, tip) => `<label title="${esc(tip)}">${lab} <input type="range" data-${grp}="${key}" min="${mn}" max="${mx}" step="${st}" value="${v}"><span>${v}</span></label>`;
  const R = P.protect = Object.assign({hold: true, margin: 512}, P.protect || {});
  return `<h3>Protection${lsGuide('Protection')}</h3><div class="lm-raise">
      ${chk('lsr-hold', R.hold, `Hold the ground under buildings, ruins and doors <span id="ls-held-t">${info.held != null ? '(' + info.held + ' here, outlined on the map)' : ''}</span>`, 'Under each building piece, ruin wall and door the ground stays exactly as it is, fading back to the plan over the margin round it, so nothing is buried or left standing in the air')}
      ${R.hold ? sl('margin', 'pr', 'Margin', 128, 2048, 64, R.margin, 'How far round each held piece the ground fades back to the plan') : ''}
      <div class="msg" style="font-size:11.5px">Rocks, trees, plants, crates, people and creatures move up or down with the ground instead, and walking paths too.</div>
    </div>
    <h3>Natural passes${lsGuide('Natural passes')}</h3><div class="lm-raise">
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
    </div>
    <h3>Dressing${lsGuide('Dressing')}</h3><div class="lm-raise">
      <label title="The region whose land the plan takes after: its textures, its tints and shading, its roughness and slopes">Like <select class="inp" id="lsd-region"><option value="">the nearest region</option>${regs.map(r => `<option value="${esc(r.id.toLowerCase())}" ${r.id.toLowerCase() === D.region ? 'selected' : ''}>${esc(r.name)}</option>`).join('')}</select></label>
      ${D.region ? chk('lsd-assign', D.assign, 'Put the cells in this region (its weather, sounds, creatures)', 'The marked cells join the region in the same Undo') : ''}
      <label title="How many textures a cell: as the region's own cells have (the land survey's median), or fewer or more">Textures <select class="inp" id="lsd-var">${[[-1, 'as many a cell as the region'], [0.4, 'fewer'], [1, 'more'], [2, 'many']].map(([v, t]) => `<option value="${v}" ${+D.variety === v ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
      ${chk('lsd-tints', D.tints, 'Tint each texture as the game does', 'landshade "By texture": the colour the region\'s land gives each texture')}
      ${chk('lsd-seams', D.seams, 'Darken where textures meet', 'landshade "Where textures meet": the join tinted as the game tints it at that pair')}
      ${chk('lsd-hollows', D.hollows, 'Darker hollows, lighter crests', 'As the region\'s land is: the land survey measured hollows 6 to 14% darker than level ground, crests 1 to 5% lighter')}
      ${sl('shade', 'dr', 'Shading', 0, 1, 0.05, D.shade, 'How strongly the tints, seams and hollows are laid on')}
      ${sl('rocks', 'dr', 'Rocks', 0, 2, 0.1, D.rocks, 'The region\'s rocks on the new slopes and cliffs, as thickly as the game sets them on such ground (1), fewer or more (0: none). Set when you shape')}
      ${chk('lsd-tview', LM.texView, 'Show the textures in the preview', 'Each texture its own colour over the preview, as the plan would lay them')}
      <div class="ls-tex" id="ls-texlegend">${lsLegend()}</div>
    </div>`;
}
// a "?" beside a section, opening the land guide there (help.js)
function lsGuide(section){ return typeof guideLink === 'function' ? guideLink('shaping-the-land.md', section, 'How this works (the land guide)') : ''; }
// the cells a shape reaches (with its widths and the plan's edge fade): for "Mark its cells", and to say when a shape
// lies outside the marked cells and so changes nothing (the user drew a river with nothing marked, 2026-10-28)
function lsShapeCells(L){
  const C = 8192, p = Object.assign({}, LS_DEFAULTS[L.kind], L.p || {}), fade = (LM.plan && LM.plan.fade) || 1024;
  const reach = {coast: Math.min(1536, p.width * 0.25) + 1024, plateau: 1024, ridge: p.width * 1.5, river: p.width + p.banks,
    valley: p.width, lake: p.width + 512, stamp: p.radius, spring: 2 * C}[L.kind] + fade;
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
function lsPassesBind(P){
  const A = P.passes, D = P.dress, R = P.protect;
  const on = (id, f) => { const el = $('#' + id); if (el) el.onchange = () => f(el); };
  on('lsr-hold', el => { R.hold = el.checked; lsChanged(true); });
  document.querySelectorAll('[data-pr]').forEach(r => r.oninput = () => { R[r.dataset.pr] = +r.value; r.nextElementSibling.textContent = r.value; lsChanged(); });
  on('lsp-detail', el => { A.detail = el.checked; lsChanged(); });
  on('lsp-settle', el => { A.settle = el.checked; lsChanged(); });
  on('lsp-terr', el => { A.terraces = el.checked; lsChanged(true); });
  on('lsp-ronly', el => { A.ronly = el.value; lsChanged(); });
  // (Rock layers and Tilt show their own sliders when they go from 0 or back to it: drawn again then)
  document.querySelectorAll('[data-pa]').forEach(r => r.oninput = () => {
    const was = A[r.dataset.pa]; A[r.dataset.pa] = +r.value; r.nextElementSibling.textContent = r.value;
    lsChanged(['rock', 'rdip'].includes(r.dataset.pa) && (was > 0) !== (+r.value > 0));
  });
  document.querySelectorAll('[data-dr]').forEach(r => r.oninput = () => { D[r.dataset.dr] = +r.value; r.nextElementSibling.textContent = r.value; lsChanged(); });
  on('lsd-region', el => { D.region = el.value; if (!el.value) D.assign = false; lsChanged(true); });
  on('lsd-assign', el => { D.assign = el.checked; lsChanged(); });
  on('lsd-var', el => { D.variety = +el.value; lsChanged(); });
  on('lsd-tints', el => { D.tints = el.checked; lsChanged(); });
  on('lsd-seams', el => { D.seams = el.checked; lsChanged(); });
  on('lsd-hollows', el => { D.hollows = el.checked; lsChanged(); });
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
    .ls-pin{position:sticky;top:-14px;z-index:5;display:flex;align-items:center;justify-content:space-between;gap:8px;
      margin:-14px -14px 8px;padding:8px 14px;background:var(--panel);border-bottom:1px solid var(--line)}
    .ls-pin .msg{font-size:11.5px;line-height:1.35}.ls-pin .btn{flex:none}`;
  document.head.appendChild(c);
}
function lsBind(){
  lsCss();
  const P = LM.plan; if (!P) return;
  document.querySelectorAll('[data-add]').forEach(b => b.onclick = () => lsStart(b.dataset.add));
  document.querySelectorAll('.ls-row').forEach(r => r.onclick = e => { if (e.target.closest('button,input')) return; LM.sel = +r.dataset.i; renderWside(); drawMap(); });
  document.querySelectorAll('[data-on]').forEach(c => c.onchange = () => { P.layers[+c.dataset.on].on = c.checked; lsChanged(); });
  document.querySelectorAll('[data-up]').forEach(b => b.onclick = () => lsMove(+b.dataset.up, -1));
  document.querySelectorAll('[data-dn]').forEach(b => b.onclick = () => lsMove(+b.dataset.dn, 1));
  document.querySelectorAll('[data-del]').forEach(b => b.onclick = () => { P.layers.splice(+b.dataset.del, 1); LM.sel = null; lsChanged(true); });
  const sel = P.layers[LM.sel];
  document.querySelectorAll('[data-p]').forEach(r => r.oninput = () => { sel.p[r.dataset.p] = +r.value; r.nextElementSibling.textContent = r.value; lsChanged(); });
  document.querySelectorAll('[data-g]').forEach(r => r.oninput = () => { P[r.dataset.g] = +r.value; r.nextElementSibling.textContent = r.value; lsChanged(); });
  document.querySelectorAll('[data-src]').forEach(r => r.onchange = () => { sel.p.src = sel.p.src || [0, 0, 0, 0]; sel.p.src[+r.dataset.src] = +r.value; lsChanged(); });
  const sh = $('#ls-shape'); if (sh) sh.onchange = () => { sel.p.shape = sh.value; if (sh.value === 'game'){ sel.p.height = 0; } lsChanged(true); };
  const here = $('#ls-src-here'); if (here) here.onclick = () => { const i = W.info || {}; sel.p.src = [i.gx - 1, i.gy - 1, i.gx + 1, i.gy + 1]; lsChanged(true); };
  const cy = $('#ls-canyon'); if (cy) cy.onchange = () => { sel.p.canyon = cy.checked ? 1 : 0; lsChanged(); };
  const se = $('#ls-sea'); if (se) se.onchange = () => { sel.p.sea = se.checked ? 1 : 0; lsChanged(); };
  const mi = $('#ls-markit'); if (mi) mi.onclick = async e => {
    if (!await needProject()) return;
    const all = lsShapeCells(sel).filter(k => !LM.data.marked.has(k));
    // (settled cells, towns, only with Shift, as when marking by hand)
    const town = all.filter(k => { const c = lmCell(k); return c && c[0] === 'settled'; });
    const add = e.shiftKey ? all : all.filter(k => !town.includes(k));
    try {
      lmMarksAre((await post('/api/land/marks', {add})).marks);
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
  const at = $('#ls-apply-top'); if (at) at.onclick = () => lsApply(at);
  // (all the shapes off the map: a plan isn't in Undo, so it asks first)
  const ca = $('#ls-clearall'); if (ca) ca.onclick = () => {
    const n = P.layers.length;
    if (!confirm(`Take all ${n} shape${n === 1 ? '' : 's'} off the map?\n\nLand you already shaped stays as it is. This can't be undone.`)) return;
    P.layers = []; LM.sel = null; LM.prev = null; LM.prevData = null; LM.prevInfo = {}; lsChanged(true);
  };
  if (P.passes && P.dress) lsPassesBind(P);
}
function lsMove(i, d){
  const P = LM.plan, j = i + d; if (j < 0 || j >= P.layers.length) return;
  [P.layers[i], P.layers[j]] = [P.layers[j], P.layers[i]]; LM.sel = j; lsChanged(true);
}
// a change: saved into the project and previewed, a moment after the last one
function lsChanged(rerender){
  if (rerender) renderWside();
  clearTimeout(LM.saveT);
  LM.saveT = setTimeout(async () => { try { const r = await post('/api/land/plan', {plan: LM.plan}); LM.plan.layers.forEach((L, i) => { L.p = r.layers[i] ? r.layers[i].p : L.p; }); } catch (e){ toast(e.message, true); } }, 500);
  lsPreviewSoon();
  drawMap();
}
function lsPreviewSoon(){
  clearTimeout(LM.prevT);
  LM.prevStale = true;                                // (the one shown is out of date: drawn dimmed till the new one)
  LM.prevT = setTimeout(lsPreview, 350);
}
async function lsPreview(){
  if (!LM.data || !LM.plan || LM.prevOn === false){ LM.prevStale = false; return; }
  // (nothing to preview: also stops one still on its way from painting the old plan back)
  if (!LM.plan.layers.length || !LM.data.marks.length){ ++LM.prevN; LM.prev = null; LM.prevStale = false; drawMap(); return; }
  const ask = ++LM.prevN;
  try {
    const r = await post('/api/land/plan/preview', {cells: LM.data.marks, plan: LM.plan});
    if (ask !== LM.prevN) return;                     // (a newer one is on its way)
    LM.prevStale = false;
    LM.prevData = r; LM.prevTex = r.textures; LM.prevInfo = r.info || {};
    lsBuildPrev(); drawMap();
    const lg = $('#ls-texlegend'); if (lg) lg.innerHTML = lsLegend();
    const st = $('#ls-settle-t'); if (st && LM.prevInfo.settle_angle){ st.textContent = lsSettleText(LM.prevInfo.settle_angle); st.title = lsSettleTip(LM.prevInfo.settle_angle); }
    // (the marked cells' regions arrived: the "Only in" choices follow them)
    const hk = lsHereRegions().join('|'); if (hk !== LM.hereKey){ LM.hereKey = hk; renderWside(); }
    const ht = $('#ls-held-t'); if (ht && LM.prevInfo.held != null) ht.textContent = `(${LM.prevInfo.held} here, outlined on the map)`;
  } catch (e){ if (ask === LM.prevN){ LM.prevStale = false; drawMap(); } const n = $('#ls-note'); if (n) n.textContent = e.message; }
}
LM.prevN = 0;

// ----- drawing a new shape: click points, double-click (or Enter) to finish; a stamp is one click
async function lsStart(kind){
  if (!await needProject()) return;
  if (V3.on) await v3Enable(false);
  LM.show = true;
  LM.drawing = {kind, pts: []};
  $('#maptip').style.display = 'none';
  lsHook();
  setMode('landshape'); cv.classList.add('place');
  setBanner(`${LS_KINDS[kind].icon} ${esc(LS_KINDS[kind].how)} <kbd>Esc</kbd> cancels. <button class="btn sm" id="ls-done">Done</button>`);
  $('#ls-done').onclick = lsFinish;
  drawMap();
}
function lsDown(e){
  const D = LM.drawing; if (!D) return;
  const [wx, wy] = toWorld(e.offsetX, e.offsetY);
  D.pts.push([Math.round(wx), Math.round(wy)]);
  if (LS_KINDS[D.kind].point || D.kind === 'stamp') return lsFinish();
  drawMap();
}
function lsMoveMouse(e){ if (LM.drawing){ LM.mouse = toWorld(e.offsetX, e.offsetY); drawMap(); } }
function lsFinish(){
  const D = LM.drawing; LM.drawing = null;
  if (W.mode === 'landshape') setMode(null);
  if (!D) return;
  // (a double-click adds its point twice)
  const pts = D.pts.filter((p, i) => !i || Math.hypot(p[0] - D.pts[i - 1][0], p[1] - D.pts[i - 1][1]) > 64);
  const need = D.kind === 'stamp' || LS_KINDS[D.kind].point ? 1 : LS_KINDS[D.kind].closed ? 3 : 2;
  if (pts.length < need){ toast(`A ${LS_KINDS[D.kind].label.toLowerCase()} needs ${need} point${need === 1 ? '' : 's'} at least.`, true); drawMap(); return; }
  const P = LM.plan;
  P.layers.push({id: String(Date.now()), kind: D.kind, name: '', on: true, pts, p: Object.assign({}, LS_DEFAULTS[D.kind])});
  LM.sel = P.layers.length - 1; LM.prevOn = LM.prevOn === false ? false : true;
  lsChanged(true);
}
function lsHook(){
  if (LM.hooked) return;
  LM.hooked = true;
  cv.addEventListener('dblclick', e => { if (W.mode === 'landshape' && LM.drawing){ e.preventDefault(); lsFinish(); } });
}
document.addEventListener('keydown', e => {
  if (W.mode === 'landshape' && LM.drawing && e.key === 'Enter'){ e.preventDefault(); lsFinish(); }
  if (W.mode !== 'landshape' && LM.drawing){ LM.drawing = null; drawMap(); }
});

// ----- the shapes on the map, the one picked with its points to drag
function lsDrawShapes(g){
  const P = LM.plan; if (!P) return;
  const line = (pts, closed, color, width, dash) => {
    if (!pts.length) return;
    g.beginPath(); pts.forEach((p, i) => { const [sx, sy] = toScreen(p[0], p[1]); if (i) g.lineTo(sx, sy); else g.moveTo(sx, sy); });
    if (closed) g.closePath();
    g.setLineDash(dash || []); g.strokeStyle = color; g.lineWidth = width; g.stroke(); g.setLineDash([]);
  };
  P.layers.forEach((L, i) => {
    const K = LS_KINDS[L.kind], on = i === LM.sel, a = L.on === false ? '55' : 'ff';
    if (L.kind === 'stamp'){
      const [sx, sy] = toScreen(L.pts[0][0], L.pts[0][1]), r = (L.p.radius || 8192) * W.cam.z;
      g.beginPath(); g.arc(sx, sy, r, 0, Math.PI * 2); g.setLineDash([5, 4]); g.strokeStyle = K.color + a; g.lineWidth = on ? 2.5 : 1.5; g.stroke(); g.setLineDash([]);
    } else if (K.point){
      // a spring: the way the water found from it, from the last preview
      const way = LM.prevInfo && LM.prevInfo.springs && LM.prevInfo.springs[L.id];
      if (way && L.on !== false) line(way, false, K.color + a, on ? 3 : 2);
      const [sx, sy] = toScreen(L.pts[0][0], L.pts[0][1]);
      g.beginPath(); g.arc(sx, sy, 6, 0, Math.PI * 2); g.fillStyle = K.color + a; g.fill();
    } else line(L.pts, K.closed, K.color + a, on ? 3 : 2);
    if (on) for (const p of L.pts){ const [sx, sy] = toScreen(p[0], p[1]); g.fillStyle = '#fff'; g.strokeStyle = K.color; g.lineWidth = 2; g.beginPath(); g.arc(sx, sy, 5, 0, Math.PI * 2); g.fill(); g.stroke(); }
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
    const pts = D.pts.concat(LM.mouse ? [LM.mouse] : []);
    line(pts, false, LS_KINDS[D.kind].color, 2, [6, 4]);
    for (const p of D.pts){ const [sx, sy] = toScreen(p[0], p[1]); g.fillStyle = LS_KINDS[D.kind].color; g.beginPath(); g.arc(sx, sy, 4, 0, Math.PI * 2); g.fill(); }
  }
}
// dragging a point of the picked shape (the map's own drag otherwise)
function lmHandleDown(e){
  const P = LM.plan, L = P && P.layers[LM.sel];
  if (!LM.show || !L || W.mode) return false;
  for (let i = 0; i < L.pts.length; i++){
    const [sx, sy] = toScreen(L.pts[i][0], L.pts[i][1]);
    if (Math.hypot(sx - e.offsetX, sy - e.offsetY) <= 8){ LM.hdrag = {L, i}; return true; }
  }
  return false;
}
function lmHandleMove(e){
  const H = LM.hdrag; if (!H) return false;
  const [wx, wy] = toWorld(e.offsetX, e.offsetY); H.L.pts[H.i] = [Math.round(wx), Math.round(wy)]; H.moved = true; drawMap();
  return true;
}
function lmHandleUp(){ const H = LM.hdrag; LM.hdrag = null; if (H && H.moved) lsChanged(); }

async function lsApply(btn){
  if (!await needProject()) return;
  btn.disabled = true; btn.textContent = `Shaping ${LM.data.marks.length} cell${LM.data.marks.length === 1 ? '' : 's'}…`;
  try {
    const r = await post('/api/land/plan/apply', {cells: LM.data.marks, plan: LM.plan});
    toast(`Shaped ${r.cells} cell${r.cells === 1 ? '' : 's'}${r.new ? ` (${r.new} new)` : ''}${r.eased ? `; ${r.eased} steps too steep for the game eased` : ''}${r.moved ? `; ${r.moved} objects followed the ground` : ''}${r.shaded && r.shaded.length ? '; shaded' : ''}${r.rocks ? `; ${r.rocks} rocks set` : ''}${r.assigned ? `; ${r.assigned} put in the region` : ''}. Changes to the ground show in game after a restart.`);
    // (the land made, against the region's own figures from the land survey)
    const m = r.measured || {}, figs = Object.entries(r.region_figures || {});
    if (figs.length && m.slope){
      const [rn, f] = figs[0];
      LM.applyNote = `Made: slopes ${m.slope['50']}° / ${m.slope['90']}° / ${m.slope['99']}° (half, 90%, 99% under), ${Math.round(m.over45 * 100)}% over 45°, roughness ${m.rough['128']} / ${m.rough['1024']}${r.textures_a_cell ? `, ${r.textures_a_cell} textures a cell` : ''}. ` +
        `The ${rn.replace(/ region$/, '').replace(/\b\w/g, c => c.toUpperCase())} region's own land: ${f.slope['50']}° / ${f.slope['90']}° / ${f.slope['99']}°, ${Math.round((f.over45 || 0) * 100)}%, ${f.rough['128']} / ${f.rough['1024']}, ${f.tex_per_cell || '?'}.`;
    }
    LM.prev = null; LM.prevData = null;
    W.lands = {}; if (typeof v3LandsReload === 'function') v3LandsReload();
    await afterChange(); await lmLoad(true);
    await loadAround(Math.floor(W.cam.x / CELL), Math.floor(W.cam.y / CELL));
    LM.prevOn = false;                                 // (the land is shaped now: the map shows it as it is)
    drawMap(); renderWside();
  } catch (err){ const n = $('#ls-note'); if (n) n.textContent = err.message; btn.disabled = false; btn.textContent = 'Shape the marked cells'; }
}
async function lmRaise(btn){
  if (!await needProject()) return;
  const cells = LM.data.marks.slice(); if (!cells.length) return;
  btn.disabled = true; btn.textContent = `Raising ${cells.length} cell${cells.length === 1 ? '' : 's'}…`;
  try {
    const r = await post('/api/land/raise', {cells, height: LM.height, coast: LM.coast, rough: LM.rough, paint: LM.paint});
    toast(`Raised ${r.cells} cell${r.cells === 1 ? '' : 's'} into land${r.new ? ` (${r.new} new)` : ''}${r.painted_as.length ? ', textured like the ' + r.painted_as.map(s => s.replace(/ region$/, '')).join(' and ') : ''}${r.eased ? `; ${r.eased} steps too steep for the game eased` : ''}${r.moved ? `; ${r.moved} objects followed it` : ''}. Changes to the ground show in game after a restart.`);
    W.lands = {}; if (typeof v3LandsReload === 'function') v3LandsReload();
    await afterChange(); await lmLoad(true);
    await loadAround(Math.floor(W.cam.x / CELL), Math.floor(W.cam.y / CELL));
    drawMap(); renderWside();
  } catch (err){ toast(err.message, true); btn.disabled = false; btn.textContent = 'Raise the marked cells into land'; }
}
