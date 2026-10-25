// ---------- Regions on the World map: coloured cells, painting cells into a region, weather preview ----------
const REG = {data: null, show: false, paint: null, drag: null, loading: null};

async function regLoad(force){
  if (REG.data && !force) return REG.data;
  if (!REG.loading) REG.loading = api('/api/regions').then(d => {
    d.byId = {}; for (const r of d.regions) d.byId[r.id.toLowerCase()] = r;
    REG.data = d; REG.loading = null; return d;
  }).catch(e => { REG.loading = null; throw e; });
  return REG.loading;
}

// open the World map outdoors with the regions shown; with an id, start painting that region
async function regionsOnMap(id){
  const d = await regLoad(true);
  REG.show = true;
  showView('world');
  const cells = id ? Object.entries(d.map).filter(([, r]) => r === id.toLowerCase()).map(([k]) => k.split(',').map(Number)) : [];
  let gx = 0, gy = 0;
  if (cells.length){ gx = Math.round(cells.reduce((a, c) => a + c[0], 0) / cells.length); gy = Math.round(cells.reduce((a, c) => a + c[1], 0) / cells.length); }
  else if (W.ext){ gx = Math.floor(W.cam.x / CELL); gy = Math.floor(W.cam.y / CELL); }
  if (V3.on) await v3Enable(false);              // regions are painted on the flat map
  if (!W.ext || !cells.length || Math.floor(W.cam.x / CELL) !== gx){
    await worldOpen(extKey(gx, gy));
  }
  // zoom out so the whole region (or the area around) fits
  if (cells.length){
    const xs = cells.map(c => c[0]), ys = cells.map(c => c[1]);
    W.cam.x = (Math.min(...xs) + Math.max(...xs) + 1) / 2 * CELL; W.cam.y = (Math.min(...ys) + Math.max(...ys) + 1) / 2 * CELL;
    const span = Math.max(Math.max(...xs) - Math.min(...xs) + 3, Math.max(...ys) - Math.min(...ys) + 3) * CELL;
    W.cam.z = Math.max(0.004, Math.min(0.05, Math.min(W.w, W.h) / span));
  } else W.cam.z = Math.min(W.cam.z, 0.02);
  if (id) regPaint(id);
  W.tab = 'view'; renderWside(); drawMap();
}

function regColor(id, a){
  const r = REG.data && REG.data.byId[(id || '').toLowerCase()];
  const c = r ? r.color : [128, 128, 128];
  return `rgba(${c[0]},${c[1]},${c[2]},${a})`;
}

// called by drawMap outdoors, after the ground is drawn
function regDraw(g){
  if (!REG.show || !REG.data || !W.ext) return;
  const z = W.cam.z, M = REG.data.map, sz = CELL * z;
  const [wx0, wy1] = toWorld(0, 0), [wx1, wy0] = toWorld(W.w, W.h);
  const gx0 = Math.floor(wx0 / CELL) - 1, gx1 = Math.floor(wx1 / CELL) + 1, gy0 = Math.floor(wy0 / CELL) - 1, gy1 = Math.floor(wy1 / CELL) + 1;
  if ((gx1 - gx0) * (gy1 - gy0) > 40000) return;
  g.save();
  const seen = {};
  for (let x = gx0; x <= gx1; x++) for (let y = gy0; y <= gy1; y++){
    const reg = M[x + ',' + y]; if (!reg) continue;
    const [sx, sy] = toScreen(x * CELL, (y + 1) * CELL);
    g.fillStyle = regColor(reg, REG.paint != null && reg === (REG.paint || '').toLowerCase() ? 0.55 : 0.38);
    g.fillRect(sx, sy, sz + 0.5, sz + 0.5);
    // borders between regions
    g.strokeStyle = 'rgba(255,255,255,0.75)'; g.lineWidth = 1.5;
    if (M[(x + 1) + ',' + y] !== reg){ g.beginPath(); g.moveTo(sx + sz, sy); g.lineTo(sx + sz, sy + sz); g.stroke(); }
    if (M[x + ',' + (y + 1)] !== reg){ g.beginPath(); g.moveTo(sx, sy); g.lineTo(sx + sz, sy); g.stroke(); }
    if (M[(x - 1) + ',' + y] !== reg){ g.beginPath(); g.moveTo(sx, sy); g.lineTo(sx, sy + sz); g.stroke(); }
    if (M[x + ',' + (y - 1)] !== reg){ g.beginPath(); g.moveTo(sx, sy + sz); g.lineTo(sx + sz, sy + sz); g.stroke(); }
    const s = seen[reg] || (seen[reg] = {n: 0, x: 0, y: 0}); s.n++; s.x += sx + sz / 2; s.y += sy + sz / 2;
  }
  // a name in the middle of each region on screen
  g.font = '600 13px Inter, sans-serif'; g.textAlign = 'center';
  for (const [reg, s] of Object.entries(seen)){
    if (s.n < 2 && sz < 60) continue;
    const r = REG.data.byId[reg], name = r ? r.name : reg;
    g.fillStyle = '#000a'; g.fillText(name, s.x / s.n + 1, s.y / s.n + 1);
    g.fillStyle = '#fff'; g.fillText(name, s.x / s.n, s.y / s.n);
  }
  g.restore();
}

// ----- painting cells into a region
function regPaint(id){
  REG.paint = id == null ? null : id;
  if (id == null){ setMode(null); return; }
  REG.show = true;
  W.mode = 'region'; cv.classList.add('place');
  regBanner(); drawMap();
}
function regBanner(){
  const regs = REG.data ? REG.data.regions : [];
  setBanner(`🖌 Painting <select class="inp" id="reg-pick" style="max-width:240px;display:inline-block;padding:2px 6px;height:auto">
      <option value="">(no region: erase)</option>${regs.map(r => `<option value="${esc(r.id)}" ${r.id.toLowerCase() === (REG.paint || '').toLowerCase() ? 'selected' : ''}>${esc(r.name)}</option>`).join('')}</select>
    Click or drag over cells to put them in it. <button class="btn sm" id="reg-done">Done</button>`);
  $('#reg-pick').onchange = e => { REG.paint = e.target.value; drawMap(); };
  $('#reg-done').onclick = () => { REG.paint = null; setMode(null); drawMap(); renderWside(); };
}
function regCellAt(sx, sy){ const [wx, wy] = toWorld(sx, sy); return Math.floor(wx / CELL) + ',' + Math.floor(wy / CELL); }
function regDown(e){
  REG.drag = {cells: new Set([regCellAt(e.offsetX, e.offsetY)]), before: {}};
  regMark(REG.drag, regCellAt(e.offsetX, e.offsetY));
}
function regMove(e){ if (REG.drag){ regMark(REG.drag, regCellAt(e.offsetX, e.offsetY)); } }
function regMark(D, k){
  D.cells.add(k);
  if (!(k in D.before)) D.before[k] = REG.data.map[k];
  if (REG.paint) REG.data.map[k] = REG.paint.toLowerCase(); else delete REG.data.map[k];
  drawMap();
}
async function regUp(){
  const D = REG.drag; REG.drag = null; if (!D) return;
  const target = (REG.paint || '').toLowerCase();
  const cells = [...D.cells].filter(k => (D.before[k] || '') !== target);
  if (!cells.length) return;
  if (!await needProject()){ for (const k of cells){ if (D.before[k]) REG.data.map[k] = D.before[k]; else delete REG.data.map[k]; } drawMap(); return; }
  try {
    const r = await post('/api/region/assign', {id: REG.paint || '', cells});
    if (r.changed < cells.length) toast(`${r.changed} of ${cells.length} cells changed (cells with no land can't be in a region).`);
    await regLoad(true); afterChange(); drawMap();
  } catch (e){ toast(e.message, true); await regLoad(true); drawMap(); }
}

// ----- the View tab outdoors: this cell's region, the overlay and the weather preview
function regViewHtml(i){
  if (!i || i.interior) return '';
  const regs = REG.data ? REG.data.regions : [];
  const cur = (i.region || '').toLowerCase();
  return `<h3>Region &amp; weather</h3>
    <div class="msg">This cell (${i.gx}, ${i.gy}) is in:</div>
    <div style="display:flex;gap:6px;margin-top:4px"><select class="inp" id="reg-cell"><option value="">(no region)</option>${regs.map(r => `<option value="${esc(r.id)}" ${r.id.toLowerCase() === cur ? 'selected' : ''}>${esc(r.name)}</option>`).join('')}</select>
      ${cur ? `<button class="btn sm" id="reg-edit" title="Weather, sounds, sleep encounters">✎</button>` : ''}</div>
    <label class="msg" style="display:flex;gap:6px;align-items:center;margin-top:8px"><input type="checkbox" id="reg-show" ${REG.show ? 'checked' : ''}> Show regions on the map</label>
    <div class="actions" style="margin-top:6px"><button class="btn sm" id="reg-paint">🖌 Paint regions…</button><button class="btn sm" id="reg-all">🌦 All regions</button></div>
    <h3>Weather preview (3D)</h3>
    <select class="inp" id="reg-weather">${['auto', 'Clear', 'Cloudy', 'Foggy', 'Overcast', 'Rain', 'Thunderstorm', 'Ash storm', 'Blight', 'Snow', 'Blizzard'].map((w, n) => `<option value="${n - 1}" ${(V3.weather == null ? -1 : V3.weather) === n - 1 ? 'selected' : ''}>${n ? w : 'Plain daylight (no weather)'}</option>`).join('')}</select>
    <div class="msg" style="font-size:11.5px">How the sky, fog and falling rain, ash or snow look in the 3D view. The game picks the weather from the region's chances.</div>
    <h3>Time of day (3D)</h3>
    <div class="regday"><input type="range" id="reg-hour" min="0" max="24" step="0.25" value="${V3.hour == null ? 13 : V3.hour}" title="Drag through the day: the sky, fog, sun and light as the game has them at each hour, for the weather above">
      <span class="regday-t" id="reg-hour-t">${esc(typeof v3HourLabel === 'function' ? v3HourLabel(V3.hour) : '')}</span></div>
    <div class="actions" style="margin-top:4px"><button class="btn sm" id="reg-hour-x" ${V3.hour == null ? 'disabled' : ''} title="Back to the plain, even daylight">☀ Plain daylight</button></div>
    <div class="msg" style="font-size:11.5px">Sunrise, day, sunset and night in the game's own colours for the weather chosen above (from your openmw.cfg). Lamps and torches count for more as it gets dark.</div>`;
}
function regDayCss(){
  if ($('#regday-css')) return;
  const c = document.createElement('style'); c.id = 'regday-css';
  c.textContent = `.regday{display:flex;gap:8px;align-items:center}.regday input{flex:1;min-width:0}
    .regday-t{flex:none;width:96px;font-size:12px;color:var(--muted);text-align:right;white-space:nowrap}`;
  document.head.appendChild(c);
}
async function regViewBind(i){
  if (!i || i.interior) return;
  if (!REG.data){ try { await regLoad(); } catch (e){ return; } renderWside(); return; }
  const sel = $('#reg-cell');
  if (sel) sel.onchange = async () => {
    if (!await needProject()){ renderWside(); return; }
    try { await post('/api/region/assign', {id: sel.value, cells: [i.gx + ',' + i.gy]}); toast(sel.value ? 'Moved this cell into ' + sel.options[sel.selectedIndex].text : 'Took this cell out of its region'); await regLoad(true); afterChange(); await worldReloadCell(W.key); drawMap(); }
    catch (e){ toast(e.message, true); }
  };
  const ed = $('#reg-edit'); if (ed) ed.onclick = () => ruShow('region', i.region);
  const sh = $('#reg-show'); if (sh) sh.onchange = () => { REG.show = sh.checked; drawMap(); };
  const pa = $('#reg-paint'); if (pa) pa.onclick = async () => { if (V3.on) await v3Enable(false); regPaint(i.region || (REG.data.regions[0] || {}).id || ''); };
  const al = $('#reg-all'); if (al) al.onclick = () => ruShow('region');
  const we = $('#reg-weather'); if (we) we.onchange = () => { V3.weather = +we.value < 0 ? null : +we.value; if (typeof v3ApplyWeather === 'function') v3ApplyWeather(); };
  regDayCss();
  const hr = $('#reg-hour'), ht = $('#reg-hour-t'), hx = $('#reg-hour-x');
  if (hr) hr.oninput = async () => {
    if (typeof v3Daylight !== 'function') return;
    await v3Daylight();
    V3.hour = +hr.value;
    if (ht) ht.textContent = v3HourLabel(V3.hour);
    if (hx) hx.disabled = false;
    if (!V3.on && !regDayCss.told){ regDayCss.told = true; toast('Turn on the 3D view to see the time of day.'); }
    v3ApplyWeather();
  };
  if (hx) hx.onclick = () => { V3.hour = null; if (ht) ht.textContent = v3HourLabel(null); hx.disabled = true; v3ApplyWeather(); };
}
