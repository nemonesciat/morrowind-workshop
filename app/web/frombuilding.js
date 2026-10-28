// Build an interior from a building (frombuilding.py): right-click a building's piece or door outdoors,
// see whether it is closed and sound and the floors the interior would have drawn over it, then Build.
// The planned tiles are drawn on the map, floor by floor; the new interior's door and the building's
// door are linked both ways and the northmarker put in; the fit (the reviewers' test) is shown after.
const FB = {on: false, cell: null, ref: null, door: null, res: null, panel: null, floor: null};
const FB_COL = ['#f0cd87', '#7fd1c7', '#c79bf0'];

// (the land's own big pieces count as architecture but are no building: a rock got "Build an interior inside
// this building" and "Fit the ground", both refused, in the crawl test)
const FB_NOT_BUILDING = /terrain|rock|boulder|cliff|mount|flora|tree|stump|log_|kelp|grass|lava|_dune|shore|cave_ent/i;
// (outdoors, or a place that behaves like outdoors: Mournhold's districts are interiors with buildings in them)
function fbOutside(ck){ return !!ck && (ck.startsWith('#') || !!(W.info && W.info.key === ck && W.info.like_exterior)); }
function fbMenuItem(ck, r){
  // (outdoors only: a building piece or a door)
  if (!fbOutside(ck) || !(r.arch || r.type === 'DOOR') || FB_NOT_BUILDING.test(r.id)) return null;
  return {label: '🏠 Build an interior inside this building…', act: () => fbOpen(ck, r.k)};
}

// Check a building outdoors by the game's own rules for its style (frombuilding.outdoor_check): pieces standing on
// nothing, walls round, the roof. Measured on 3,417 of the game's buildings first, so it flags only what is worse
// than the game's own (the prefab stage 2, 2026-10-27)
function fbCheckItem(ck, r){
  if (!fbOutside(ck) || !(r.arch || r.type === 'DOOR') || FB_NOT_BUILDING.test(r.id)) return null;
  return {label: '🔍 Check this building', act: () => fbCheck(ck, r.k)};
}
async function fbCheck(cell, ref){
  FB.on = true; FB.cell = cell; FB.ref = ref; FB.res = null;
  fbPanel('<div class="msg">Checking the building…</div>', '🔍 Check this building');
  let r;
  try { r = await api('/api/build/check?cell=' + encodeURIComponent(cell) + '&ref=' + encodeURIComponent(ref)); }
  catch (e){ return fbPanel(`<div class="msg" style="color:#e25a4a">${esc(e.message)}</div>`, '🔍 Check this building'); }
  const bad = r.lines.filter(l => l.sev === 'error').length, warn = r.lines.filter(l => l.sev === 'warning').length;
  fbPanel(`<div class="msg" style="margin-bottom:6px">${r.style ? esc(r.style) + ' building, ' : ''}checked by the game's own ${r.style ? esc(r.style) + ' ' : ''}buildings: ${
    bad ? `<b style="color:#e25a4a">${bad} fault${bad === 1 ? '' : 's'}</b>` : warn ? 'sound, with notes' : '<b style="color:#8fc98f">sound</b>'}.</div>
    ${r.lines.map(fbLine).join('')}
    <div style="margin-top:8px"><button class="btn sm" id="fb-again">Check again</button> <button class="btn sm" id="fb-inside" title="Build an interior that fits it">🏠 An interior for it…</button></div>`, '🔍 Check this building');
  const P = FB.panel;
  P.querySelectorAll('[data-at]').forEach(b => b.onclick = () => { const a = JSON.parse(b.dataset.at); if (V3.on && typeof v3Focus === 'function') v3Focus({k: null, p: [a[0], a[1], a[2] + 200]}); else { W.cam.x = a[0]; W.cam.y = a[1]; if (W.cam.z < 1.5) W.cam.z = 1.5; drawMap(); } });
  P.querySelector('#fb-again').onclick = () => fbCheck(cell, ref);
  P.querySelector('#fb-inside').onclick = () => fbOpen(cell, ref);
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

async function fbOpen(cell, ref, door, keepCellar){
  if (!keepCellar) FB.cellar = null;
  FB.on = true; FB.cell = cell; FB.ref = ref; FB.door = door || null; FB.res = null; FB.floor = null; FB.games = null; FB.gamePick = null; FB.cname = null;
  fbPanel('<div class="msg">Reading the building…</div>');
  let r;
  try { r = await api('/api/build/from_building?cell=' + encodeURIComponent(cell) + '&ref=' + encodeURIComponent(ref) + (door ? '&door=' + encodeURIComponent(door) : '') +
                      (FB.cellar ? '&cellar=' + FB.cellar : '')); }
  catch (e){ fbPanel(`<div class="msg" style="color:#e25a4a">${esc(e.message)}</div>`); return; }
  FB.res = r;
  fbRender();
  if (!V3.on && typeof drawMap === 'function') drawMap();
  // (and the game's own interiors behind buildings of the same shell: each a valid interior for this one)
  try { FB.games = await api('/api/build/game_interiors?cell=' + encodeURIComponent(cell) + '&ref=' + encodeURIComponent(ref) + (door ? '&door=' + encodeURIComponent(door) : '')); }
  catch (e){ FB.games = null; }
  if (FB.res === r) fbRender();
}

// The game's interiors behind buildings of the same shell, to copy whole and link to this building's door (the
// user, 2026-10-27: each one the game made for that shell "constitutes another valid form for the interior")
function fbGamesHtml(){
  const G = FB.games; if (!G || !G.interiors || !G.interiors.length) return '';
  const rows = G.interiors, pick = FB.gamePick != null && rows[FB.gamePick] ? FB.gamePick : 0;
  return `<div style="margin:8px 0;padding:6px 0;border-top:1px solid #fff2;border-bottom:1px solid #fff2">
    <b>The game's own interiors for ${esc(G.shell)}</b> <span class="msg">(${rows.length})</span>
    <div class="msg" style="margin:3px 0">Each is a place the game put behind a building made like this one. Copy one whole: its door and this building's lead to each other.</div>
    <div style="max-height:150px;overflow:auto;margin:4px 0">${rows.map((x, n) => `<label style="display:block;cursor:pointer;margin:1px 0"><input type="radio" name="fb-game" value="${n}" ${n === pick ? 'checked' : ''}>
      ${esc(x.name)} <span class="msg">· ${esc(x.style || '')}${x.floors > 1 ? ' · ' + x.floors + ' floors' : ''}${x.area ? ' · ' + x.area + ' m²' : ''}${x.own ? ' · this building\'s own' : x.same ? '' : ' · round a piece of it'}</span></label>`).join('')}</div>
    <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap"><input id="fb-cname" style="flex:1;min-width:120px" maxlength="63" placeholder="The new place's name" value="${esc(FB.cname || (FB.res && FB.res.name) || '')}">
      <select id="fb-keep" title="What comes with it"><option value="furnished">Everything</option><option value="lights">Walls and lights</option><option value="empty">Bare walls</option></select>
      <button class="btn" id="fb-copy" title="Copy it whole (people and creatures are left out), its door linked with this building's both ways (one Undo)">Copy it</button></div></div>`;
}
async function fbCopy(){
  const P = FB.panel, G = FB.games; if (!P || !G) return;
  const n = +((P.querySelector('input[name=fb-game]:checked') || {}).value || 0), t = G.interiors[n];
  const name = (P.querySelector('#fb-cname').value || '').trim();
  if (!name) return toast('Give the new place a name.', true);
  const b = P.querySelector('#fb-copy'); b.disabled = true; b.textContent = 'Copying…';
  let o;
  try { o = await post('/api/build/copy_interior', {cell: FB.cell, ref: FB.ref, door: FB.res && FB.res.door, template: t.key, name, contents: P.querySelector('#fb-keep').value}); }
  catch (e){ b.disabled = false; b.textContent = 'Copy it'; return toast(e.message, true); }
  FB.res.built = `<div style="margin-top:8px;padding-top:6px;border-top:1px solid #fff2"><div><b>Copied ${esc(t.name)} as ${esc(o.name)}</b>; its door and the building's lead to each other.</div>
    <button class="btn" id="fb-open" data-key="${esc(o.key)}">Open it</button></div>`;
  FB.games = null;
  fbRender();
  if (typeof afterChange === 'function') afterChange();
  toast('Copied ' + t.name + ' as ' + o.name);
}

function fbPanel(html, title){
  if (!FB.panel){
    const p = document.createElement('div'); p.className = 'modal'; p.id = 'fb-panel';
    p.style.cssText = 'position:fixed;right:16px;top:90px;width:320px;max-height:calc(100% - 120px);overflow:auto;z-index:60;box-shadow:0 6px 24px #0008;padding:10px';
    document.body.appendChild(p);
    FB.panel = p;
  }
  FB.panel.innerHTML = `<h2 style="margin:0 0 6px;font-size:15px;display:flex;align-items:center;gap:6px"><span style="flex:1">${esc(title || '🏠 An interior for this building')}</span><button class="btn sm" id="fb-close" title="Close (nothing is changed)">✕</button></h2>${html}`;
  FB.panel.querySelector('#fb-close').onclick = fbClose;
}

function fbLine(l){
  const mark = l.sev === 'ok' ? '✓' : l.sev === 'warning' ? '⚠' : '✗', col = l.sev === 'ok' ? '#8fc98f' : l.sev === 'warning' ? '#e8b85a' : '#e25a4a';
  return `<div style="margin:2px 0"><span style="color:${col};display:inline-block;width:16px">${mark}</span>${esc(l.text)}${l.at ? ` <button class="btn sm" data-at="${esc(JSON.stringify(l.at[0]))}" title="Show it on the map">⌖</button>` : ''}</div>`;
}

function fbRender(){
  const r = FB.res; if (!r) return;
  let h = `<div style="margin-bottom:6px">${(r.check || []).map(fbLine).join('')}</div>` + fbGamesHtml();
  if (r.doors && r.doors.length > 1)
    h += `<div class="msg">Doors: <select id="fb-door">${r.doors.map(d => `<option value="${esc(d.k)}" ${d.k === r.door ? 'selected' : ''}>${esc(d.id)} (${Math.round(d.p[2])} up)</option>`).join('')}</select></div>`;
  const pl = r.plan;
  if (r.error && !pl) h += `<div class="msg" style="color:#e25a4a">${esc(r.error)}</div>`;
  if (pl){
    const fl = pl.floors.length;
    if (pl.style === 'pods') h += `<div style="margin:6px 0"><b>Ready-made interiors</b>: a place for each shell with a door, the game's own interior piece for it, fitted out as one of the game's</div>`;
    else h += `<div style="margin:6px 0"><b>${esc(pl.style_name)}</b>, ${fl} floor${fl === 1 ? '' : 's'}, ${pl.rooms.length} room${pl.rooms.length === 1 ? '' : 's'} · tile ${pl.tile}</div>`;
    h += `<div class="msg">${pl.floors.map(f => `<label style="margin-right:8px;cursor:pointer"><input type="radio" name="fb-fl" value="${f}" ${FB.floor === f || (FB.floor == null && f === 0) ? 'checked' : ''}> <span style="color:${FB_COL[f] || '#ddd'}">■</span> ${f === 0 ? 'Ground' : f < 0 ? 'Cellar' : 'Floor ' + (f + 1)}</label>`).join('')}</div>`;
    // (a cellar below, as the game's own houses so often have: under the house, and out past its walls underground)
    const C = r.cellar;
    if (C) h += `<div class="msg" style="margin:4px 0">Cellar <select id="fb-cellar">
      <option value="" ${!FB.cellar ? 'selected' : ''}>None</option>
      <option value="usual" ${FB.cellar === 'usual' ? 'selected' : ''}>The game's usual (${C.usual}× the ground floor)</option>
      <option value="big" ${FB.cellar === 'big' ? 'selected' : ''}>A big one (${C.big}×)</option></select>
      <span title="Measured on the game's own interiors behind buildings">${Math.round(C.share * 100)}% of the game's ${esc(C.style || '')} houses have one</span></div>`;
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
  const cs = P.querySelector('#fb-cellar'); if (cs) cs.onchange = () => { FB.cellar = cs.value || null; fbOpen(FB.cell, FB.ref, FB.res && FB.res.door, true); };
  const bb = P.querySelector('#fb-build'); if (bb) bb.onclick = fbBuild;
  const cb = P.querySelector('#fb-copy'); if (cb) cb.onclick = fbCopy;
  P.querySelectorAll('input[name=fb-game]').forEach(x => x.onchange = () => { FB.gamePick = +x.value; });
  const cn = P.querySelector('#fb-cname'); if (cn) cn.oninput = () => { FB.cname = cn.value; };
  const op = P.querySelector('#fb-open'); if (op) op.onclick = () => { const k = op.dataset.key; fbClose(); worldOpen(k); };
}

async function fbBuild(){
  const name = (FB.panel.querySelector('#fb-name').value || '').trim();
  if (!name) return toast('Give the new place a name.', true);
  const b = FB.panel.querySelector('#fb-build'); b.disabled = true; b.textContent = 'Building…';
  let o;
  try { o = await post('/api/build/from_building', {cell: FB.cell, ref: FB.ref, door: FB.res.door, name, cellar: FB.cellar}); }
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

// ----- an outside for an interior: the game's buildings that fit its rooms (grown as the game grows its interiors
// past their buildings, Anvil's by a quarter), set down outdoors with the doors linked (frombuilding.outsides_for)
const GO = {interior: null, name: '', list: null, pick: 0};
function goMenuItem(){
  if (!W.info || !W.info.interior || W.info.like_exterior) return null;
  return {label: '🏛 Give this place an outside…', act: () => goOpen(W.info.key, W.info.name)};
}
async function goOpen(key, name){
  GO.interior = key; GO.name = name || key; GO.list = null; GO.pick = 0;
  fbPanel('<div class="msg">Finding the game\'s buildings that fit its rooms…</div>', '🏛 An outside for ' + GO.name);
  try { GO.list = await api('/api/build/outsides?key=' + encodeURIComponent(key)); }
  catch (e){ return fbPanel(`<div class="msg" style="color:#e25a4a">${esc(e.message)}</div>`, '🏛 An outside for ' + GO.name); }
  goRender();
}
function goRender(){
  const L = GO.list; if (!L) return;
  const I = L.interior;
  const outdoors = !!W.ext;
  fbPanel(`<div class="msg">Its ground floor is ${I.w} by ${I.d} units, ${I.floors} floor${I.floors === 1 ? '' : 's'} from the way out up. The game's ${esc(L.style)} interiors are bigger than their buildings, so these are the ones whose walls they would fit, the closest first.</div>
    <div style="max-height:220px;overflow:auto;margin:6px 0">${L.buildings.map((b, n) => `<label style="display:block;cursor:pointer;margin:2px 0"><input type="radio" name="go-b" value="${n}" ${n === GO.pick ? 'checked' : ''}>
      ${esc(b.name)} <span class="msg">· ${b.floors} floor${b.floors === 1 ? '' : 's'} · ${b.uses}× in the game · ${esc(b.text)}</span></label>`).join('') || '<div class="msg">None of the game\'s buildings of this style fits.</div>'}</div>
    <div class="msg" style="margin:4px 0">${outdoors ? 'It follows the mouse on the land, the wheel turns it, a click puts it down; its door and this place\'s lead to each other (one Undo).' :
      'Go to the outdoor place where it stands (Go to a place…, this window stays), then Place it.'}</div>
    <button class="btn" id="go-place" ${outdoors && L.buildings.length ? '' : 'disabled'}>⤓ Place it</button>`, '🏛 An outside for ' + GO.name);
  const P = FB.panel;
  P.querySelectorAll('input[name=go-b]').forEach(x => x.onchange = () => { GO.pick = +x.value; });
  P.querySelector('#go-place').onclick = goPlace;
}
async function goPlace(){
  const b = GO.list && GO.list.buildings[GO.pick]; if (!b || !W.ext) return;
  let r;
  try { r = await api('/api/build/outside_items?key=' + encodeURIComponent(b.key)); } catch (e){ return toast(e.message, true); }
  if (!V3.on && typeof v3Enable === 'function') await v3Enable(true);
  startGroupPlace(r.items, r.label + ' (an outside for ' + GO.name + ')');
  W.groupPlace.outside = {interior: GO.interior, key: b.key};
}
// (world3d.js: the click while it is being placed: put down where the ghost stands on the land, doors linked)
async function goPlaceClick(){
  const G = V3.ghost, P = W.groupPlace; if (!G || !G.hit || !P || !P.outside) return toast('Point at the ground first.', true);
  if (!await needProject()) return;
  const [x, y, z] = G.hit;
  const r = await groupAction('/api/build/give_outside', {interior: P.outside.interior, key: P.outside.key, cell: cellKeyAt(x, y), x, y, z, yaw: G.yaw}, `Gave ${GO.name} an outside`);
  if (!r) return;
  setMode(null);
  W.multi.clear(); r.placed.forEach(p => W.multi.set(mkey(p.cell, p.ref), {cell: p.cell, k: p.ref}));
  W.sel = {cell: r.door.cell, k: r.door.ref};
  renderWside(); drawMap(); if (V3.on) v3Refresh();
  fbPanel(`<div><b>Done.</b> ${esc(GO.name)} has an outside here; its door and the building's lead to each other.</div>
    <button class="btn" id="go-in">Go inside</button>`, '🏛 An outside for ' + GO.name);
  FB.panel.querySelector('#go-in').onclick = () => { const k = GO.interior; fbClose(); worldOpen(k); };
}
// (back outdoors with the window open: its Place it comes alive)
setInterval(() => {
  const btn = FB.panel && GO.list && FB.panel.querySelector('#go-place');
  if (btn && !!(W.ext && GO.list.buildings.length) === btn.disabled) goRender();
}, 1000);

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
