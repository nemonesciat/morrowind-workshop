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
  return {label: '🏠 An interior for this building…', act: () => fbOpen(ck, r.k)};
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
    <div style="margin-top:8px"><button class="btn sm" id="fb-again">Check again</button> <button class="btn sm" id="fb-inside" title="Copy one of the game's interiors for it, or make a new one to fit">🏠 An interior for it…</button></div>`, '🔍 Check this building');
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

async function fbOpen(cell, ref, door, keep){
  // (keep: the same window again with a choice changed, the door, the floors or the cellar; the copy search kept)
  if (!keep){ FB.cellar = null; FB.floors = null; FB.copyOpen = false; FB.q = ''; FB.gamePick = null; FB.cname = null; }
  const games = keep && FB.cell === cell && FB.ref === ref && (FB.door || null) === (door || null) ? FB.games : null;
  FB.on = true; FB.cell = cell; FB.ref = ref; FB.door = door || null; FB.res = null; FB.floor = null; FB.games = games;
  if (!keep) fbPanel('<div class="msg">Reading the building…</div>');
  let r;
  try { r = await api('/api/build/from_building?cell=' + encodeURIComponent(cell) + '&ref=' + encodeURIComponent(ref) + (door ? '&door=' + encodeURIComponent(door) : '') +
                      (FB.cellar ? '&cellar=' + FB.cellar : '') + (FB.floors ? '&floors=' + FB.floors : '')); }
  catch (e){ fbPanel(`<div class="msg" style="color:#e25a4a">${esc(e.message)}</div>`); return; }
  FB.res = r;
  fbRender();
  if (!V3.on && typeof drawMap === 'function') drawMap();
  // (and the game's own interiors behind buildings of the same shell: each a valid interior for this one)
  if (!games){
    try { FB.games = await api('/api/build/game_interiors?cell=' + encodeURIComponent(cell) + '&ref=' + encodeURIComponent(ref) + (door ? '&door=' + encodeURIComponent(door) : '')); }
    catch (e){ FB.games = null; }
    if (FB.res === r) fbRender();
  }
}

// The game's interiors behind buildings of the same shell, to copy whole and link to this building's door (the
// user, 2026-10-27: each one the game made for that shell "constitutes another valid form for the interior"), as a
// search under the new one, closed at first (the user, 2026-10-28: "copy interior should just be a search")
function fbGamesHtml(){
  const G = FB.games; if (!G || !G.interiors || !G.interiors.length) return '';
  const rows = G.interiors;
  if (!FB.copyOpen) return `<div style="margin-top:10px"><button class="btn sm" id="fb-copyopen" title="Interiors the game put behind buildings made from ${esc(G.shell)}: copy one whole, its door linked with this building's">📋 Or copy one of the game's (${rows.length})…</button></div>`;
  const q = (FB.q || '').trim().toLowerCase();
  const hits = rows.map((x, n) => [x, n]).filter(([x]) => !q || (x.name + ' ' + (x.style || '')).toLowerCase().includes(q));
  const pick = FB.gamePick != null && hits.some(([, n]) => n === FB.gamePick) ? FB.gamePick : (hits[0] ? hits[0][1] : null);
  FB.gamePick = pick;
  return `<div style="margin-top:10px;padding-top:6px;border-top:1px solid #fff2">
    <div style="display:flex;gap:6px;align-items:center"><b style="flex:1">📋 Copy one of the game's</b><button class="btn sm" id="fb-copyclose" title="Close the search">✕</button></div>
    <input id="fb-q" placeholder="Search ${rows.length} interiors…" value="${esc(FB.q || '')}" style="width:100%;margin:4px 0">
    <div style="max-height:140px;overflow:auto">${hits.slice(0, 40).map(([x, n]) => `<label style="display:block;cursor:pointer;margin:1px 0" title="${esc(x.style || '')}${x.floors > 1 ? ', ' + x.floors + ' floors' : ''}${x.area ? ', ' + x.area + ' m²' : ''}${x.own ? ', this building\'s own' : x.same ? '' : ', round a piece of it'}"><input type="radio" name="fb-game" value="${n}" ${n === pick ? 'checked' : ''}> ${esc(x.name)}</label>`).join('') || '<div class="msg">None by that name.</div>'}</div>
    <div style="display:flex;gap:6px;align-items:center;margin-top:4px"><select id="fb-keep" title="What comes with it"><option value="furnished">Everything</option><option value="lights">Walls and lights</option><option value="empty">Bare walls</option></select>
      <button class="btn" id="fb-copy" ${pick == null ? 'disabled' : ''} title="Copy it whole under the name above (people and creatures are left out), its door linked with this building's both ways (one Undo)">Copy it</button></div></div>`;
}
async function fbCopy(){
  const P = FB.panel, G = FB.games; if (!P || !G || FB.gamePick == null) return;
  const t = G.interiors[FB.gamePick];
  const name = ((P.querySelector('#fb-name') || {}).value || '').trim();
  if (!name) return toast('Give the new place a name.', true);
  const b = P.querySelector('#fb-copy'); b.disabled = true; b.textContent = 'Copying…';
  let o;
  try { o = await post('/api/build/copy_interior', {cell: FB.cell, ref: FB.ref, door: FB.res && FB.res.door, template: t.key, name, contents: P.querySelector('#fb-keep').value}); }
  catch (e){ b.disabled = false; b.textContent = 'Copy it'; return toast(e.message, true); }
  FB.res.built = `<div style="margin-top:8px;padding-top:6px;border-top:1px solid #fff2"><div><b>Copied ${esc(t.name)} as ${esc(o.name)}</b>; its door and the building's lead to each other.</div>
    <button class="btn" id="fb-open" data-key="${esc(o.key)}">Open it</button></div>`;
  FB.games = null; FB.res.ok = false;
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
  fb3d();
}

function fbLine(l){
  const mark = l.sev === 'ok' ? '✓' : l.sev === 'warning' ? '⚠' : '✗', col = l.sev === 'ok' ? '#8fc98f' : l.sev === 'warning' ? '#e8b85a' : '#e25a4a';
  return `<div style="margin:2px 0"><span style="color:${col};display:inline-block;width:16px">${mark}</span>${esc(l.text)}${l.at ? ` <button class="btn sm" data-at="${esc(JSON.stringify(l.at[0]))}" title="Show it on the map">⌖</button>` : ''}</div>`;
}
// the building's check in one line ("Sound"), the whole check in its tooltip; only what is wrong is spelled out
function fbCheckSummary(lines){
  const bad = (lines || []).filter(l => l.sev !== 'ok');
  const tip = (lines || []).map(l => (l.sev === 'ok' ? '✓ ' : l.sev === 'warning' ? '⚠ ' : '✗ ') + l.text).join('\n');
  return `<div class="msg" title="${esc(tip)}" style="margin-bottom:4px">${bad.length ? '' : '<span style="color:#8fc98f">✓</span> The building is sound'}</div>${bad.map(fbLine).join('')}`;
}

// A new interior first, the one way most want, and plain (the user, 2026-10-28: "build a new interior should be the
// default choice, and it should be better and more obvious"): its name, its floors (as many as asked, up to the
// building's height), a cellar, Make it; what the plan says in tooltips. Copying one of the game's is a search under it.
function fbRender(){
  const r = FB.res; if (!r) return;
  let h = fbCheckSummary(r.check);
  if (r.doors && r.doors.length > 1)
    h += `<div class="msg" title="The building's door the new interior is linked to">Door <select id="fb-door">${r.doors.map(d => `<option value="${esc(d.k)}" ${d.k === r.door ? 'selected' : ''}>${esc(d.id)} (${Math.round(d.p[2])} up)</option>`).join('')}</select></div>`;
  const pl = r.plan, live = r.ok && pl && !pl.problem && !r.built;
  h += `<div style="margin:6px 0 2px">Name <input id="fb-name" style="width:calc(100% - 50px)" value="${esc(FB.cname != null ? FB.cname : (r.name || ''))}" maxlength="63" title="The new place's name"></div>`;
  if (r.error && !pl) h += `<div class="msg" style="color:#e25a4a">${esc(r.error)}</div>`;
  if (pl && pl.style === 'pods') h += `<div style="margin:6px 0" title="${esc((pl.notes || []).join('\n'))}"><b>Ready-made interiors</b>: a place for each shell with a door, as the game's own</div>`;
  else if (pl){
    const up = r.floors_up || pl.floors.filter(f => f >= 0).length, mx = Math.max(r.floors_max || up, up), C = r.cellar;
    h += `<div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:4px 0">
      <label title="Floors above ground: the game's way for this building is ${r.floors_chosen ? 'what it planned before you chose' : up}; up to as many as the building is tall">Floors <select id="fb-floors">${Array.from({length: mx}, (_, i) => i + 1).map(n => `<option value="${n}" ${n === up ? 'selected' : ''}>${n}</option>`).join('')}</select></label>
      ${C ? `<label title="${esc(`${Math.round(C.share * 100)}% of the game's ${C.style || ''} houses have one: usually ${C.usual}× the ground floor, a big one ${C.big}×`)}">Cellar <select id="fb-cellar">
        <option value="" ${!FB.cellar ? 'selected' : ''}>None</option><option value="usual" ${FB.cellar === 'usual' ? 'selected' : ''}>Usual</option><option value="big" ${FB.cellar === 'big' ? 'selected' : ''}>Big</option></select></label>` : ''}</div>`;
    const tip = pl.rooms.map(x => `${x.name} ${x.w}×${x.h}${x.cut ? ' less ' + x.cut.length : ''}`).join(', ') + '\n' + (pl.notes || []).concat(pl.dry || []).join('\n');
    h += `<div class="msg" style="margin:2px 0" title="${esc(tip)}">${esc(pl.style_name)} · ${pl.rooms.length} room${pl.rooms.length === 1 ? '' : 's'} ⓘ</div>`;
    h += `<div class="msg" title="Shows that floor's planned rooms in the building, on the map and in 3D. Every floor is made.">Show ${pl.floors.map(f => `<label style="margin-right:6px;cursor:pointer"><input type="radio" name="fb-fl" value="${f}" ${FB.floor === f || (FB.floor == null && f === 0) ? 'checked' : ''}><span style="color:${FB_COL[f] || '#ddd'}">■</span>${f === 0 ? 'Ground' : f < 0 ? 'Cellar' : f + 1}</label>`).join('')}</div>`;
    if (pl.problem) h += `<div class="msg" style="color:#e25a4a">${esc(pl.problem)}</div>`;
  }
  if (live) h += `<button class="btn primary" id="fb-build" style="width:100%;margin-top:8px" title="Make it, link its door with the building's both ways and put the northmarker in (Undo takes it back)">🛠 Make the interior</button>`;
  if (r.built) h += r.built;
  else h += fbGamesHtml();
  fbPanel(h);
  const P = FB.panel;
  P.querySelectorAll('[data-at]').forEach(b => b.onclick = () => { const a = JSON.parse(b.dataset.at); W.cam.x = a[0]; W.cam.y = a[1]; if (W.cam.z < 1.5) W.cam.z = 1.5; drawMap(); });
  P.querySelectorAll('input[name=fb-fl]').forEach(b => b.onchange = () => { FB.floor = +b.value; drawMap(); fb3d(); });
  fb3d();
  const ds = P.querySelector('#fb-door'); if (ds) ds.onchange = () => fbOpen(FB.cell, FB.ref, ds.value, true);
  const fs = P.querySelector('#fb-floors'); if (fs) fs.onchange = () => { FB.floors = +fs.value; fbOpen(FB.cell, FB.ref, FB.res && FB.res.door, true); };
  const cs = P.querySelector('#fb-cellar'); if (cs) cs.onchange = () => { FB.cellar = cs.value || null; fbOpen(FB.cell, FB.ref, FB.res && FB.res.door, true); };
  const nm = P.querySelector('#fb-name'); if (nm) nm.oninput = () => { FB.cname = nm.value; };
  const bb = P.querySelector('#fb-build'); if (bb) bb.onclick = fbBuild;
  const co = P.querySelector('#fb-copyopen'); if (co) co.onclick = () => { FB.copyOpen = true; fbRender(); const q = FB.panel.querySelector('#fb-q'); if (q) q.focus(); };
  const cx = P.querySelector('#fb-copyclose'); if (cx) cx.onclick = () => { FB.copyOpen = false; fbRender(); };
  const qi = P.querySelector('#fb-q'); if (qi) qi.oninput = () => { FB.q = qi.value; const at = qi.selectionStart; fbRender(); const q2 = FB.panel.querySelector('#fb-q'); if (q2){ q2.focus(); q2.setSelectionRange(at, at); } };
  const cb = P.querySelector('#fb-copy'); if (cb) cb.onclick = fbCopy;
  P.querySelectorAll('input[name=fb-game]').forEach(x => x.onchange = () => { FB.gamePick = +x.value; });
  const op = P.querySelector('#fb-open'); if (op) op.onclick = () => { const k = op.dataset.key; fbClose(); worldOpen(k); };
}

async function fbBuild(){
  const name = (FB.panel.querySelector('#fb-name').value || '').trim();
  if (!name) return toast('Give the new place a name.', true);
  const b = FB.panel.querySelector('#fb-build'); b.disabled = true; b.textContent = 'Making…';
  let o;
  try { o = await post('/api/build/from_building', {cell: FB.cell, ref: FB.ref, door: FB.res.door, name, cellar: FB.cellar, floors: FB.floors}); }
  catch (e){ b.disabled = false; b.textContent = '🛠 Make the interior'; return toast(e.message, true); }
  const f = o.fits;
  FB.res.built = `<div style="margin-top:8px;padding-top:6px;border-top:1px solid #fff2">
    <div><b>Made ${esc(o.name)}</b>${(o.cells || []).length > 1 ? ` (${o.cells.length} places, one a floor)` : ''}; its door and the building's lead to each other.</div>
    ${f ? `<div class="msg" style="margin:4px 0;color:${f.ok ? '#8fc98f' : '#e8b85a'}" title="${esc(f.text)}">${f.ok ? '✓ Fits the building' : '⚠ Stands out of the building in places'}</div>` : ''}
    <button class="btn" id="fb-open" data-key="${esc(o.key)}">Open it</button></div>`;
  FB.res.plan = Object.assign({}, FB.res.plan, {problem: null});
  FB.res.ok = false;                            // (made once: no second Make from this window)
  fbRender();
  toast('Made ' + o.name);
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
  fb3d();
  if (FB.panel){ FB.panel.remove(); FB.panel = null; }
  if (!V3.on && typeof drawMap === 'function') drawMap();
}

// the same in the 3D view: the planned floor's tiles at its height inside the building (a storey 256 up, as
// shellsurvey.STOREY), seen through the walls, the floors under it faint; the floor buttons pick which
const FB_STOREY = 256;
function fb3d(){
  if (typeof V3 === 'undefined' || !V3.scene) return;
  if (FB.g3){ V3.scene.remove(FB.g3); FB.g3.traverse(o => { if (o.geometry) o.geometry.dispose(); }); FB.g3 = null; }
  if (!FB.on || !FB.res || !FB.res.tiles || !FB.res.tiles.length || !V3.on) return;
  const T = THREE, want = FB.floor == null ? 0 : FB.floor, g = new T.Group(), z0 = FB.res.sill || 0;
  for (const t of FB.res.tiles){
    if (t.f > want) continue;
    const top = t.f === want, z = z0 + t.f * FB_STOREY + 6, col = new T.Color(FB_COL[t.f] || '#dddddd');
    const sh = new T.Shape(t.c.map(p => new T.Vector2(p[0], p[1])));
    const fill = new T.Mesh(new T.ShapeGeometry(sh), new T.MeshBasicMaterial({color: col, transparent: true, opacity: top ? 0.35 : 0.1, depthTest: false, depthWrite: false, side: T.DoubleSide}));
    fill.position.z = z; fill.renderOrder = 30; g.add(fill);
    const edge = new T.LineLoop(new T.BufferGeometry().setFromPoints(t.c.map(p => new T.Vector3(p[0], p[1], z))), new T.LineBasicMaterial({color: col, transparent: true, opacity: top ? 0.9 : 0.3, depthTest: false}));
    edge.renderOrder = 31; g.add(edge);
  }
  V3.scene.add(g); FB.g3 = g;
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
