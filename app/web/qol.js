// Comforts for modders, in the spirit of the Construction Set Extender: your changes marked on the
// map (and a panel listing them), hiding things to get at what's behind, where something is used
// (F1), going through doors and back, reopening the last place, scaling a group, search and replace,
// and test setups for Play (what you start with: items, spells, quest stages, variables).
const QOL = {back: [], marks3d: null, marksSig: ''};

function qolCss(){
  if ($('#qol-css')) return;
  const c = document.createElement('style'); c.id = 'qol-css';
  c.textContent = `
  .qol-key{display:inline-block;width:10px;height:10px;border-radius:2px;margin:0 4px 0 8px;vertical-align:-1px;border:1.5px dashed}
  .qol-list > div{display:flex;align-items:center;gap:8px;padding:5px 2px;border-bottom:1px solid var(--line);cursor:pointer;font-size:13px}
  .qol-list > div:hover{background:#ffffff08}
  .qol-list > div > span{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .qol-list small{color:var(--faint)}
  .qol-list > div > .qol-tag{font-size:10.5px;padding:1px 6px;border-radius:8px;flex:none}
  .qol-tag.new{background:#2a4a2a;color:#a6eea6}.qol-tag.changed{background:#4a3c20;color:var(--gold2)}.qol-tag.gone{background:#4a2420;color:#ffb0a2}
  .qol-uses h3{margin:14px 0 6px}
  .qol-uses .qol-list{max-height:220px;overflow:auto}
  .qol-setups{display:grid;grid-template-columns:190px 1fr;gap:16px}
  .qol-setups .side > div{padding:6px 8px;border-radius:7px;cursor:pointer;font-size:13px;display:flex;gap:6px;align-items:center}
  .qol-setups .side > div.on{background:#ffffff12}
  .qol-setups textarea{width:100%;box-sizing:border-box;min-height:62px;font-family:var(--mono);font-size:12px}
  .qol-setups label{margin-top:8px}
  @media (max-width:640px){.qol-setups{grid-template-columns:1fr}}`;
  document.head.appendChild(c);
}

// ---------------------------------------------------------------- your changes
function qolChanges(){
  const out = [];
  for (const [ck, c] of Object.entries(W.cells)){
    if (!c.exists || (!W.ext && ck !== W.key)) continue;
    for (const r of c.refs) if (r.mine) out.push({ck, r, kind: r.new ? 'new' : 'changed'});
    for (const r of c.gone || []) out.push({ck, r, kind: 'gone'});
  }
  return out;
}
const QOL_KIND = {new: 'new', changed: 'changed', gone: 'removed'};

function qolPanels(){
  PNL.define('world', 'changes', {title: 'My changes', icon: '✎', cls: 'wside', render: qolRenderChanges, onShow: it => qolRenderChanges(it)});
}
function qolRenderChanges(it){
  qolCss();
  const all = qolChanges(), n = k => all.filter(x => x.kind === k).length;
  if (!W.key){ it.el.innerHTML = '<div class="msg">Open a place to see what your mod changed in it.</div>'; return; }
  it.el.innerHTML = `<div class="msg" style="margin-bottom:8px">${all.length ? `Here your mod has <b>${n('new')}</b> new, <b>${n('changed')}</b> changed and <b>${n('gone')}</b> removed object${all.length === 1 ? '' : 's'}.` : 'Your mod hasn\'t changed anything here yet.'}</div>
    <label class="msg" style="display:flex;gap:6px;align-items:center"><input type="checkbox" class="qol-only" ${W.onlyMine ? 'checked' : ''}> Show only what your mod changed</label>
    ${n('gone') ? '<button class="btn sm" data-q="backall" style="margin-top:6px">↶ Bring back everything removed</button>' : ''}
    <div class="qol-list" style="margin-top:8px">${all.slice(0, 400).map((x, i) => `<div data-qi="${i}"><span class="qol-tag ${x.kind}">${QOL_KIND[x.kind]}</span><span>${esc(x.r.name || x.r.id)} <small>${esc(x.r.name ? x.r.id : '')}</small></span>
      <button class="btn sm" data-qr="${i}" title="${x.kind === 'gone' ? 'Bring it back' : x.kind === 'new' ? 'Take it out again' : 'Put it back as it was'}">↶</button></div>`).join('')}</div>
    ${all.length > 400 ? `<div class="msg">…and ${all.length - 400} more</div>` : ''}`;
  it.el.querySelector('.qol-only').onchange = e => { W.onlyMine = e.target.checked; drawMap(); renderWside(); };
  const ba = it.el.querySelector('[data-q=backall]');
  if (ba) ba.onclick = () => qolRestore(all.filter(x => x.kind === 'gone'));
  it.el.querySelectorAll('[data-qi]').forEach(d => d.onclick = e => {
    const x = all[+d.dataset.qi];
    const rb = e.target.closest('[data-qr]'); if (rb){ e.stopPropagation(); qolRestore([x]); return; }
    if (x.kind === 'gone'){ qolLookAt(x.r.p); toast('It stood where the red cross is. ↶ brings it back.'); }
    else { selectRef(x.ck, x.r.k); centerOn(x.r); }
  });
}
async function qolRestore(list){
  if (!list.length || !await needProject()) return;
  const what = list.length === 1 ? (list[0].r.name || list[0].r.id) : list.length + ' objects';
  await groupAction('/api/group/restore', {refs: list.map(x => ({cell: x.ck, ref: x.r.k}))},
    list.every(x => x.kind === 'gone') ? 'Brought back ' + what : 'Put back ' + what + ' as before your mod');
  W.sel = null; renderWside(); drawMap();
}
function qolLookAt(p){
  if (V3.on){ V3.pos.set(p[0] - V3.origin[0], p[1] - V3.origin[1], p[2] - V3.origin[2]).addScaledVector(v3Dir(), -400); return; }
  W.cam.x = p[0]; W.cam.y = p[1]; if (W.cam.z < 0.15) W.cam.z = 0.3; drawMap();
}

// after the sidebar panels are drawn: the View panel's extras, the test setup by Play, My changes
function qolAfterRender(){
  qolCss();
  const view = PNL.body('world', 'view'), pane = view && view.querySelector('.wpane');
  if (pane && W.info && !pane.querySelector('#qol-view')){
    const d = document.createElement('div'); d.id = 'qol-view';
    d.innerHTML = `<h3>Your changes</h3>
      <label class="msg" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="q-marks" ${W.marks ? 'checked' : ''}> Mark them:
        <i class="qol-key" style="border-color:${MARK_NEW}"></i>new <i class="qol-key" style="border-color:${MARK_CHANGED}"></i>changed <b style="color:var(--red);margin-left:8px">✕</b> removed</label>
      ${W.info.own ? '<div class="msg" style="color:var(--faint)">Your mod made this place, so everything here is new: no marks here.</div>' : ''}
      <label class="msg" style="display:flex;gap:6px;align-items:center;margin-top:4px"><input type="checkbox" id="q-only" ${W.onlyMine ? 'checked' : ''}> Show only what your mod changed</label>
      <button class="btn sm" id="q-changes" style="margin-top:6px">✎ List them (My changes)</button>
      <h3>Hidden for now</h3>
      <div class="msg">${W.hide.size ? `<b>${W.hide.size}</b> hidden. ` : 'Nothing hidden. '}<kbd class="cf">H</kbd> hides what's selected, <kbd class="cf">Shift+H</kbd> everything else, <kbd class="cf">Alt+H</kbd> shows it all again. Hiding only changes what you see here, not the game.</div>
      ${W.hide.size ? '<button class="btn sm" id="q-unhide" style="margin-top:6px">Show them all again</button>' : ''}`;
    pane.appendChild(d);
    d.querySelector('#q-marks').onchange = e => { setMarks(e.target.checked); drawMap(); };
    d.querySelector('#q-only').onchange = e => { W.onlyMine = e.target.checked; drawMap(); renderWside(); };
    d.querySelector('#q-changes').onclick = () => PNL.show('world', 'changes');
    const u = d.querySelector('#q-unhide'); if (u) u.onclick = () => cfRun('unhide');
  }
  // the test setup used by Play, beside God mode
  const god = $('#w-god');
  if (god && !$('#q-setup')){
    const b = document.createElement('button'); b.className = 'btn sm'; b.id = 'q-setup';
    b.title = 'What you start with when Play starts the game: items, spells, quest stages, variables';
    b.textContent = '🧪 ' + (QOL.setupOn || 'Test setup…');
    b.onclick = () => qolSetups();
    god.closest('label').after(b);
    // who you play as: a new character, or one of yours from their latest save
    const a = document.createElement('button'); a.className = 'btn sm'; a.id = 'q-playas';
    a.title = 'Play here as a new character, or as one of yours (from their latest save)';
    a.onclick = () => qsPlayAs();
    b.before(a);
    if (typeof qsPlayAsLabel === 'function') qsPlayAsLabel(); else a.textContent = '👤 New character';
  }
  if (PNL.spaces.world && PNL.isOpen('world', 'changes')) qolRenderChanges(PNL.spaces.world.inst.changes);
}

// your changes in the 3D view: a box around each (green new, gold changed), a red cross where one was taken out
function qolMarks3D(){
  if (typeof THREE === 'undefined' || !V3.on || !V3.scene) return;
  const T = THREE, mine = [];
  if (W.marks) for (const [key, o] of V3.objs) if (o.r && o.g && o.r.mine && o.g.visible !== false && marksIn(o.ck)) mine.push([key, o]);
  const gone = W.marks ? qolChanges().filter(x => x.kind === 'gone' && marksIn(x.ck)) : [];
  const sig = mine.map(m => m[0]).join(',') + '|' + gone.map(x => x.r.k).join(',') + '|' + V3.origin.join(',');
  if (sig !== QOL.marksSig){
    QOL.marksSig = sig;
    if (QOL.marks3d){ V3.scene.remove(QOL.marks3d); QOL.marks3d.traverse(x => x.geometry && x.geometry.dispose()); }
    const grp = new T.Group(); grp.name = 'qol-marks';
    QOL.boxes = [];
    for (const [, o] of mine.slice(0, 400)){ const bh = new T.BoxHelper(o.g, o.r.new ? 0x8fe08f : 0xf0cd87); bh.material.transparent = true; bh.material.opacity = 0.75; grp.add(bh); QOL.boxes.push(bh); }
    if (gone.length){
      const pts = [];
      for (const x of gone){
        const [px, py, pz] = [x.r.p[0] - V3.origin[0], x.r.p[1] - V3.origin[1], x.r.p[2] - V3.origin[2] + 4], s = 18;
        pts.push(px - s, py - s, pz, px + s, py + s, pz, px + s, py - s, pz, px - s, py + s, pz, px, py, pz, px, py, pz + 40);
      }
      const geo = new T.BufferGeometry(); geo.setAttribute('position', new T.Float32BufferAttribute(pts, 3));
      grp.add(new T.LineSegments(geo, new T.LineBasicMaterial({color: 0xff7d6b})));
    }
    QOL.marks3d = grp; V3.scene.add(grp);
  } else for (const bh of QOL.boxes || []) bh.update();
}
setInterval(qolMarks3D, 400);

// ---------------------------------------------------------------- hiding
function qolHide(){
  const sel = selectionRefs(); if (!sel.length) return false;
  for (const [ck, r] of sel) W.hide.add(mkey(ck, r.k));
  W.sel = null; W.multi.clear(); renderWside(); drawMap();
  toast(`Hid ${sel.length === 1 ? sel[0][1].name || sel[0][1].id : sel.length + ' objects'}. Alt+H shows ${sel.length === 1 ? 'it' : 'them'} again.`);
}
function qolIsolate(){
  const sel = selectionRefs(); if (!sel.length) return false;
  const keep = new Set(sel.map(([ck, r]) => mkey(ck, r.k)));
  let n = 0;
  for (const [ck, r] of visibleRefs()){ const k = mkey(ck, r.k); if (!keep.has(k)){ W.hide.add(k); n++; } }
  renderWside(); drawMap(); toast(`Hid everything else (${n}). Alt+H shows it all again.`);
}
function qolUnhide(){ if (!W.hide.size) return false; const n = W.hide.size; W.hide.clear(); renderWside(); drawMap(); toast(`Showing the ${n} hidden again.`); }

// ---------------------------------------------------------------- where it's used (F1)
function qolUsesKey(){
  if (cfWorldOn()){ const r = cfSelRef(); if (!r) return false; qolUses(r.id); return; }
  if ($('#browse').classList.contains('on') && S.sel != null){
    const row = S.rows.find(x => x.i === S.sel);
    if (row){ qolUses(row.id); return; }
    api('/api/record?i=' + S.sel).then(d => d && d.id && qolUses(d.id)).catch(() => {});
    return;
  }
  return false;
}
async function qolUses(id){
  qolCss();
  const bg = document.createElement('div'); bg.className = 'modal-bg';
  bg.innerHTML = `<div class="modal qol-uses" style="width:min(640px,94vw);max-height:88vh;overflow:auto"><h2>Where it's used</h2><div class="msg"><span class="spin"></span> Looking everywhere for ${esc(id)}…</div></div>`;
  const close = () => bg.remove();
  bg.onclick = e => { if (e.target === bg) close(); };
  document.body.appendChild(bg);
  let u;
  try { u = await api('/api/uses?id=' + encodeURIComponent(id)); }
  catch (e){ bg.querySelector('.modal').innerHTML = `<h2>Where it's used</h2><div class="msg err">${esc(e.message)}</div>`; return; }
  if (!bg.isConnected) return;
  const sec = (title, rows, empty) => `<h3>${title}</h3>${rows.length ? `<div class="qol-list">${rows.join('')}</div>` : `<div class="msg">${empty}</div>`}`;
  const places = u.places.map((p, n) => `<div data-up="${n}"><span>${p.interior ? '🏠' : '🌄'} ${esc(p.label)}</span>${p.n ? `<small>×${p.n}</small>` : ''}</div>`);
  const holders = u.holders.map((h, n) => `<div data-uh="${n}"><span>${esc(h.name || h.id)} <small>${esc(h.name ? h.id : '')}</small></span><small>${esc(h.type_label)}${h.mine ? ' · your mod' : ''}</small></div>`);
  const texts = u.texts.map((t, n) => `<div data-ut="${n}"><span>${t.kind === 'script' ? '📜 ' + esc(t.label) : '💬 ' + esc(t.label || '(a line)')}</span><small>${t.kind === 'script' ? 'script' : 'dialogue: ' + esc(t.topic)}</small></div>`);
  bg.querySelector('.modal').innerHTML = `<h2>Where it's used</h2>
    <div style="font-weight:600">${esc(u.name || u.id)}</div><div class="msg">${esc(u.id)}${u.type_label ? ' · ' + esc(u.type_label) : ''}</div>
    ${sec(`Placed in the world${!u.places.length ? '' : u.places_counted ? `: ${u.placed} time${u.placed === 1 ? '' : 's'} in ${u.places.length} place${u.places.length === 1 ? '' : 's'}`
      : `: in ${u.places.length} places <span class="msg" style="text-transform:none;letter-spacing:0">(counted in the first ${u.places.filter(p => p.n).length}: ${u.placed} times)</span>`}`, places, 'Not placed anywhere.')}
    ${sec('Carried by, or in a list', holders, 'No character, creature, container or levelled list has it.')}
    ${sec('Named in scripts and dialogue', texts, 'No script or dialogue line names it.')}
    ${u.texts_more ? '<div class="msg">(only the first ones are shown)</div>' : ''}
    <div class="foot">${u.i != null ? '<button class="btn" id="qu-rec">Open its record</button>' : ''}<button class="btn primary" id="qu-close">Close</button></div>`;
  bg.querySelector('#qu-close').onclick = close;
  const rec = bg.querySelector('#qu-rec'); if (rec) rec.onclick = () => { close(); showView('browse'); openRecord(u.i, true); };
  bg.querySelectorAll('[data-up]').forEach(d => d.onclick = async () => {
    const p = u.places[+d.dataset.up]; close();
    showView('world'); await worldOpen(p.key);
    const like = visibleRefs().filter(([, r]) => r.id.toLowerCase() === u.id.toLowerCase());
    if (like.length){ cfPickMany(like); centerOn(like[0][1]); }
  });
  bg.querySelectorAll('[data-uh]').forEach(d => d.onclick = () => { const h = u.holders[+d.dataset.uh]; close(); showView('browse'); openRecord(h.i, true); });
  bg.querySelectorAll('[data-ut]').forEach(d => d.onclick = () => { const t = u.texts[+d.dataset.ut]; close(); showView('browse'); openRecord(t.i, true); });
}

// ---------------------------------------------------------------- doors, and back again
function qolView(){
  const v = {key: W.key, cam: {...W.cam}, sel: W.sel ? {...W.sel} : null, in3d: V3.on,
             name: W.info ? (W.info.name || W.info.region || W.key) : W.key};
  if (V3.on && V3.pos){ v.v3 = v3CamWorld(); v.yaw = V3.yaw; v.pitch = V3.pitch; }
  return v;
}
async function qolWaitFor3D(key){
  for (let n = 0; n < 50 && V3.on && (!V3.scene || V3.homeFor !== key); n++) await new Promise(r => setTimeout(r, 100));
  await new Promise(r => setTimeout(r, 150));
}
async function qolRestoreView(v){
  if (V3.on && v.v3){
    await qolWaitFor3D(v.key);
    V3.pos.set(v.v3[0] - V3.origin[0], v.v3[1] - V3.origin[1], v.v3[2] - V3.origin[2]); V3.yaw = v.yaw; V3.pitch = v.pitch;
  } else if (v.cam){ W.cam = {...v.cam}; drawMap(); if (W.ext) recentre(); }
  if (v.sel && findRef(v.sel.cell, v.sel.k)) selectRef(v.sel.cell, v.sel.k);
}
async function qolThrough(ck, door){
  if (!door || !door.to) return false;
  const from = qolView();
  QOL.back.push(from); if (QOL.back.length > 30) QOL.back.shift();
  const to = door.to;
  await worldOpen(to.key);
  // the door at the other end that leads back here (the one nearest to where you arrive)
  const near = Object.entries(W.cells).flatMap(([k, c]) => (c.refs || []).filter(r => r.type === 'DOOR' && r.to && r.to.key === from.key).map(r => [k, r]))
    .sort((a, b) => Math.hypot(a[1].p[0] - to.x, a[1].p[1] - to.y) - Math.hypot(b[1].p[0] - to.x, b[1].p[1] - to.y))[0];
  if (V3.on) await qolWaitFor3D(to.key);
  if (near){ selectRef(near[0], near[1].k); centerOn(near[1]); }
  else qolLookAt([to.x, to.y, to.z || 0]);
  toast(`Through the door to ${W.info ? (W.info.name || W.info.region || 'outside') : 'the other side'}. Alt+← takes you back.`);
}
async function qolBack(){
  const v = QOL.back.pop(); if (!v) return false;
  await worldOpen(v.key);
  await qolRestoreView(v);
  toast('Back in ' + v.name + '.');
}
// the last place you worked on (and how you were looking at it), to pick up where you left off
setInterval(() => { if (W.key && cfWorldOn()) try { localStorage.setItem('ws-last', JSON.stringify(qolView())); } catch (e){} }, 2000);
function qolLast(){ try { return JSON.parse(localStorage.getItem('ws-last') || 'null'); } catch (e){ return null; } }
async function qolReopen(){
  const v = qolLast(); if (!v || !v.key) return toast('No place to go back to yet.', true);
  showView('world'); await worldOpen(v.key); await qolRestoreView(v);
}
(function qolEmptyMap(){
  const v = qolLast(), box = $('#mapempty > div');
  if (!v || !v.key || !box || $('#q-reopen')) return;
  const b = document.createElement('div'); b.style.marginTop = '14px';
  b.innerHTML = `<button class="btn primary" id="q-reopen">↺ Back to ${esc(v.name || v.key)}</button>`;
  box.appendChild(b);
  b.querySelector('button').onclick = e => { e.stopPropagation(); qolReopen(); };
})();

// ---------------------------------------------------------------- scaling a group
async function qolScale(){
  const sel = selectionRefs(); if (!sel.length) return false;
  const a = prompt(`Make ${sel.length === 1 ? 'it' : 'these ' + sel.length} bigger or smaller by how much? (e.g. 1.5 for half as big again, 0.5 for half the size)`, '1.25');
  const f = parseFloat(a); if (!a || !isFinite(f) || f <= 0) return;
  if (!await needProject()) return;
  const xs = sel.map(s => s[1].p[0]), ys = sel.map(s => s[1].p[1]);
  const cx = (Math.min(...xs) + Math.max(...xs)) / 2, cy = (Math.min(...ys) + Math.max(...ys)) / 2, cz = Math.min(...sel.map(s => s[1].p[2]));
  let clamped = 0;
  const moves = sel.map(([cell, r]) => {
    const p = r.p.slice();
    if (sel.length > 1){ p[0] = cx + (p[0] - cx) * f; p[1] = cy + (p[1] - cy) * f; p[2] = cz + (p[2] - cz) * f; }
    let s = Math.round((r.s || 1) * f * 1000) / 1000;
    if (s < 0.5 || s > 2){ s = Math.max(0.5, Math.min(2, s)); clamped++; }      // (the game allows 0.5 to 2)
    return {cell, ref: r.k, p, s};
  });
  await groupAction('/api/group/move', {moves}, `Scaled ${sel.length === 1 ? sel[0][1].name || sel[0][1].id : sel.length + ' objects'} by ${f}` + (clamped ? ` (${clamped} stopped at the game's limit of 0.5 to 2)` : ''));
}

// ---------------------------------------------------------------- search and replace objects
function qolReplace(from){
  const bg = document.createElement('div'); bg.className = 'modal-bg';
  const selN = W.multi.size > 1 ? W.multi.size : 0;
  bg.innerHTML = `<div class="modal" style="width:min(520px,94vw)"><h2>Search and replace</h2>
    <div class="msg">Swap every one of an object for another, keeping where each stands, its turn and its size (and where a door leads). One Undo takes it all back.</div>
    <label>Replace</label><div class="dd"><input class="inp" id="qr-from" placeholder="The object to replace (search)" autocomplete="off" value="${esc(from || '')}"><div class="ddlist" id="qr-from-l"></div></div>
    <label>With</label><div class="dd"><input class="inp" id="qr-to" placeholder="What to put there instead (search)" autocomplete="off"><div class="ddlist" id="qr-to-l"></div></div>
    <label>Where</label>
    <label class="msg" style="display:flex;gap:6px;margin:4px 0"><input type="radio" name="qr-w" value="place" checked> In ${esc(W.info ? (W.info.name || W.info.region || 'this place') : 'this place')}${W.ext ? ' and the cells loaded around it' : ''}</label>
    ${selN ? `<label class="msg" style="display:flex;gap:6px;margin:4px 0"><input type="radio" name="qr-w" value="sel"> Only among the ${selN} selected</label>` : ''}
    <div class="msg" id="qr-n" style="margin-top:8px"></div>
    <div class="foot"><button class="btn" id="qr-x">Cancel</button><button class="btn primary" id="qr-go">Replace</button></div></div>`;
  document.body.appendChild(bg);
  const close = () => bg.remove();
  bg.onclick = e => { if (e.target === bg) close(); };
  bg.querySelector('#qr-x').onclick = close;
  const pick = {from: from || '', to: ''};
  const scope = () => (bg.querySelector('[name=qr-w]:checked') || {}).value;
  const targets = () => {
    const low = pick.from.toLowerCase(); if (!low) return [];
    const pool = scope() === 'sel' ? multiRefs() : Object.entries(W.cells).filter(([k, c]) => c.exists && (W.ext || k === W.key)).flatMap(([k, c]) => c.refs.map(r => [k, r]));
    return pool.filter(([, r]) => r.id.toLowerCase() === low);
  };
  const count = () => { const n = targets().length; bg.querySelector('#qr-n').innerHTML = pick.from ? `<b>${n}</b> to replace.` : ''; };
  ddSearch('qr-from', PLACEABLE.join(','), r => { pick.from = r.id; count(); }, true);
  ddSearch('qr-to', PLACEABLE.join(','), r => { pick.to = r.id; }, true);
  bg.querySelector('#qr-from').addEventListener('change', e => { pick.from = e.target.value.trim(); count(); });
  bg.querySelectorAll('[name=qr-w]').forEach(r => r.onchange = count);
  count();
  bg.querySelector('#qr-go').onclick = async () => {
    const to = pick.to || bg.querySelector('#qr-to').value.trim(), list = targets();
    if (!list.length) return toast('Nothing to replace: pick the object to replace first.', true);
    if (!to) return toast('Pick what to put there instead.', true);
    if (!await needProject()) return;
    close();
    const r = await groupAction('/api/group/swap', {refs: list.map(([cell, x]) => ({cell, ref: x.k})), id: to}, `Replaced ${list.length} with ${to}. One Undo takes it back.`);
    if (r){ renderWside(); drawMap(); }
  };
}

// ---------------------------------------------------------------- test setups for Play
async function qolLoadSetups(){
  try { const s = await api('/api/testsetups'); QOL.setups = s; QOL.setupOn = s.on; const b = $('#q-setup'); if (b) b.textContent = '🧪 ' + (s.on || 'Test setup…'); return s; }
  catch (e){ return {list: [], on: ''}; }
}
// (the Test setups window itself: setups.js)
qolLoadSetups();

// ---------------------------------------------------------------- shortcuts and commands for all of this
CF_ACT.push(
  {id: 'uses', label: 'Where is it used? (Use report)', keys: ['F1'], run: () => qolUsesKey()},
  {id: 'hide', label: 'Hide what\'s selected (for now)', keys: ['H'], world: true, run: () => qolHide()},
  {id: 'isolate', label: 'Hide everything but what\'s selected', keys: ['Shift+H'], world: true, run: () => qolIsolate()},
  {id: 'unhide', label: 'Show everything hidden again', keys: ['Alt+H'], world: true, run: () => qolUnhide()},
  {id: 'onlymine', label: 'Show only my changes (on / off)', keys: [], world: true, run: () => { W.onlyMine = !W.onlyMine; drawMap(); renderWside(); toast(W.onlyMine ? 'Showing only what your mod changed.' : 'Showing everything.'); }},
  {id: 'paths', label: 'Edit walking paths by hand (path grid)', keys: [], world: true, run: () => { if (W.mode === 'paths') setMode(null); else peStart(); }},
  {id: 'marks', label: 'Mark my changes on the map (on / off)', keys: [], world: true, run: () => { setMarks(!W.marks); drawMap(); renderWside(); }},
  {id: 'changes', label: 'My changes (the list)', keys: [], world: true, run: () => PNL.show('world', 'changes')},
  {id: 'through', label: 'Go through the selected door', keys: ['Enter'], world: true, run: () => {
    const r = cfSelRef(); if (!r || !r.to || ['BUTTON', 'A'].includes((document.activeElement || {}).tagName)) return false;
    qolThrough(W.sel.cell, r);
  }},
  {id: 'back', label: 'Back through the door (the place before)', keys: ['Alt+ArrowLeft'], world: true, run: () => QOL.back.length ? qolBack() : false},
  {id: 'reopen', label: 'Reopen the last place you worked on', keys: [], run: () => qolReopen()},
  {id: 'scale', label: 'Scale what\'s selected…', keys: [], world: true, run: () => qolScale()},
  {id: 'replace', label: 'Search and replace objects…', keys: ['Ctrl+H'], world: true, run: () => qolReplace(cfSelRef() ? cfSelRef().id : '')},
  {id: 'setups', label: 'Test setups for Play…', keys: [], run: () => qolSetups()},
  {id: 'find', label: 'Find in the list (Objects, or the search box)', keys: ['Ctrl+F'], run: () => {
    if (cfWorldOn()){ PNL.show('world', 'objs'); setTimeout(() => { const f = $('#w-filter'); if (f){ f.focus(); f.select(); } }, 30); return; }
    if ($('#browse').classList.contains('on')){ $('#q').focus(); $('#q').select(); return; }
    return false;
  }},
);
