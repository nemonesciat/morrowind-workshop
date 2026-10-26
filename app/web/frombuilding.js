// Build an interior from a building (frombuilding.py): right-click a building's piece or door outdoors,
// see whether it is closed and sound and the floors the interior would have drawn over it, then Build.
// The planned tiles are drawn on the map, floor by floor; the new interior's door and the building's
// door are linked both ways and the northmarker put in; the fit (the reviewers' test) is shown after.
const FB = {on: false, cell: null, ref: null, door: null, res: null, panel: null, floor: null};
const FB_COL = ['#f0cd87', '#7fd1c7', '#c79bf0'];

// (the land's own big pieces count as architecture but are no building: a rock got "Build an interior inside
// this building" and "Fit the ground", both refused, in the crawl test)
const FB_NOT_BUILDING = /terrain|rock|boulder|cliff|mount|flora|tree|stump|log_|kelp|grass|lava|_dune|shore|cave_ent/i;
function fbMenuItem(ck, r){
  // (outdoors only: a building piece or a door)
  if (!ck || !ck.startsWith('#') || !(r.arch || r.type === 'DOOR') || FB_NOT_BUILDING.test(r.id)) return null;
  return {label: '🏠 Build an interior inside this building…', act: () => fbOpen(ck, r.k)};
}

// the ground fitted to the building: raised round its foot where it stands over it, a landing at its door
// (groundfit.py); the building itself stays put, one Undo
function gfMenuItem(ck, r){
  return {label: '⛰ Fit the ground to this building', act: () => gfFit(ck, r.k)};
}
async function gfFit(cell, ref){
  let o;
  try { o = await post('/api/build/groundfit', {cell, ref}); }
  catch (e){ return toast(e.message, true); }
  toast(o.text);
  if (o.changed){
    // (the ground and what followed it, read again, as the ground brush does)
    W.lands = {};
    for (const k of Object.keys(W.cells)) if (W.cells[k] && W.cells[k].exists) await worldReloadCell(k);
    if (typeof v3LandsReload === 'function') v3LandsReload();
    if (typeof afterChange === 'function') afterChange();
    drawMap(); if (V3.on) v3Refresh();
  }
  return o;
}

async function fbOpen(cell, ref, door){
  FB.on = true; FB.cell = cell; FB.ref = ref; FB.door = door || null; FB.res = null; FB.floor = null;
  fbPanel('<div class="msg">Reading the building…</div>');
  let r;
  try { r = await api('/api/build/from_building?cell=' + encodeURIComponent(cell) + '&ref=' + encodeURIComponent(ref) + (door ? '&door=' + encodeURIComponent(door) : '')); }
  catch (e){ fbPanel(`<div class="msg" style="color:#e25a4a">${esc(e.message)}</div>`); return; }
  FB.res = r;
  fbRender();
  if (!V3.on && typeof drawMap === 'function') drawMap();
}

function fbPanel(html){
  if (!FB.panel){
    const p = document.createElement('div'); p.className = 'modal'; p.id = 'fb-panel';
    p.style.cssText = 'position:fixed;right:16px;top:90px;width:320px;max-height:calc(100% - 120px);overflow:auto;z-index:60;box-shadow:0 6px 24px #0008;padding:10px';
    document.body.appendChild(p);
    FB.panel = p;
  }
  FB.panel.innerHTML = `<h2 style="margin:0 0 6px;font-size:15px;display:flex;align-items:center;gap:6px">🏠 <span style="flex:1">An interior for this building</span><button class="btn sm" id="fb-close" title="Close (nothing is changed)">✕</button></h2>${html}`;
  FB.panel.querySelector('#fb-close').onclick = fbClose;
}

function fbLine(l){
  const mark = l.sev === 'ok' ? '✓' : l.sev === 'warning' ? '⚠' : '✗', col = l.sev === 'ok' ? '#8fc98f' : l.sev === 'warning' ? '#e8b85a' : '#e25a4a';
  return `<div style="margin:2px 0"><span style="color:${col};display:inline-block;width:16px">${mark}</span>${esc(l.text)}${l.at ? ` <button class="btn sm" data-at="${esc(JSON.stringify(l.at[0]))}" title="Show it on the map">⌖</button>` : ''}</div>`;
}

function fbRender(){
  const r = FB.res; if (!r) return;
  let h = `<div style="margin-bottom:6px">${(r.check || []).map(fbLine).join('')}</div>`;
  if (r.doors && r.doors.length > 1)
    h += `<div class="msg">Doors: <select id="fb-door">${r.doors.map(d => `<option value="${esc(d.k)}" ${d.k === r.door ? 'selected' : ''}>${esc(d.id)} (${Math.round(d.p[2])} up)</option>`).join('')}</select></div>`;
  const pl = r.plan;
  if (r.error && !pl) h += `<div class="msg" style="color:#e25a4a">${esc(r.error)}</div>`;
  if (pl){
    const fl = pl.floors.length;
    if (pl.style === 'pods') h += `<div style="margin:6px 0"><b>Ready-made interiors</b>: a place for each shell with a door, the game's own interior piece for it, fitted out as one of the game's</div>`;
    else h += `<div style="margin:6px 0"><b>${esc(pl.style_name)}</b>, ${fl} floor${fl === 1 ? '' : 's'}, ${pl.rooms.length} room${pl.rooms.length === 1 ? '' : 's'} · tile ${pl.tile}</div>`;
    h += `<div class="msg">${pl.floors.map(f => `<label style="margin-right:8px;cursor:pointer"><input type="radio" name="fb-fl" value="${f}" ${FB.floor === f || (FB.floor == null && f === 0) ? 'checked' : ''}> <span style="color:${FB_COL[f] || '#ddd'}">■</span> ${f === 0 ? 'Ground' : 'Floor ' + (f + 1)}</label>`).join('')}</div>`;
    h += `<div class="msg" style="margin:4px 0">${pl.rooms.map(x => `${esc(x.name)} ${x.w}×${x.h}${x.cut ? ' less ' + x.cut.length : ''}`).join(' · ')}</div>`;
    for (const n of (pl.notes || []).concat(pl.dry || [])) h += `<div class="msg" style="margin:3px 0">${esc(n)}</div>`;
    if (pl.problem) h += `<div class="msg" style="color:#e25a4a">${esc(pl.problem)}</div>`;
    if (r.ok && !pl.problem){
      h += `<div style="margin-top:8px;display:flex;gap:6px;align-items:center"><input id="fb-name" style="flex:1" value="${esc(r.name || '')}" maxlength="63" title="The new place's name">
        <button class="btn" id="fb-build" title="Build it, link its door with the building's both ways and put the northmarker in (Undo takes it back)">Build</button></div>`;
    }
  }
  if (r.built) h += r.built;
  fbPanel(h);
  const P = FB.panel;
  P.querySelectorAll('[data-at]').forEach(b => b.onclick = () => { const a = JSON.parse(b.dataset.at); W.cam.x = a[0]; W.cam.y = a[1]; if (W.cam.z < 1.5) W.cam.z = 1.5; drawMap(); });
  P.querySelectorAll('input[name=fb-fl]').forEach(b => b.onchange = () => { FB.floor = +b.value; drawMap(); });
  const ds = P.querySelector('#fb-door'); if (ds) ds.onchange = () => fbOpen(FB.cell, FB.ref, ds.value);
  const bb = P.querySelector('#fb-build'); if (bb) bb.onclick = fbBuild;
  const op = P.querySelector('#fb-open'); if (op) op.onclick = () => { const k = op.dataset.key; fbClose(); worldOpen(k); };
}

async function fbBuild(){
  const name = (FB.panel.querySelector('#fb-name').value || '').trim();
  if (!name) return toast('Give the new place a name.', true);
  const b = FB.panel.querySelector('#fb-build'); b.disabled = true; b.textContent = 'Building…';
  let o;
  try { o = await post('/api/build/from_building', {cell: FB.cell, ref: FB.ref, door: FB.res.door, name}); }
  catch (e){ b.disabled = false; b.textContent = 'Build'; return toast(e.message, true); }
  const f = o.fits;
  FB.res.built = `<div style="margin-top:8px;padding-top:6px;border-top:1px solid #fff2">
    <div><b>Built ${esc(o.name)}</b>${(o.cells || []).length > 1 ? ` (${o.cells.length} places, one a floor)` : ''}${o.northmarker ? ', northmarker in' : ''}; its door and the building's lead to each other.</div>
    ${f ? `<div class="msg" style="margin:4px 0;color:${f.ok ? '#8fc98f' : '#e8b85a'}">${esc(f.text)}</div>` : ''}
    <button class="btn" id="fb-open" data-key="${esc(o.key)}">Open it</button></div>`;
  FB.res.plan = Object.assign({}, FB.res.plan, {problem: null});
  FB.res.ok = false;                            // (built once: no second Build from this panel)
  fbRender();
  toast('Built ' + o.name);
}

function fbClose(){
  FB.on = false; FB.res = null;
  if (FB.panel){ FB.panel.remove(); FB.panel = null; }
  if (!V3.on && typeof drawMap === 'function') drawMap();
}

// the planned floor's tiles over the building, and the doors
function frombuildingDraw(g){
  if (!FB.on || !FB.res || !FB.res.tiles || V3.on) return;
  const want = FB.floor == null ? 0 : FB.floor;
  for (const t of FB.res.tiles){
    if (t.f !== want && !(t.f < want)) continue;
    const col = FB_COL[t.f] || '#ddd', top = t.f === want;
    g.save(); g.beginPath();
    t.c.forEach((p, n) => { const [sx, sy] = toScreen(p[0], p[1]); if (n) g.lineTo(sx, sy); else g.moveTo(sx, sy); });
    g.closePath(); g.fillStyle = col + (top ? '44' : '14'); g.strokeStyle = col; g.lineWidth = top ? 1.6 : 0.6; g.globalAlpha = top ? 1 : 0.6;
    g.fill(); g.stroke(); g.restore();
  }
  for (const d of FB.res.doors || []){
    const [sx, sy] = toScreen(d.p[0], d.p[1]);
    g.save(); g.strokeStyle = d.k === FB.res.door ? '#fff0b0' : '#f0cd8788'; g.lineWidth = 2.5; g.beginPath(); g.arc(sx, sy, 9, 0, Math.PI * 2); g.stroke(); g.restore();
  }
}
