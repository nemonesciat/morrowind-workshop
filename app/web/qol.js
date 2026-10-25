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

// ---------------------------------------------------------------- a slider on the spot
// A small box where the pointer last was, in place of a dialog asking for a number: a slider to drag (the
// change shows as you drag), a field to type into, a few marks to click; Enter or a click elsewhere keeps
// it, Esc puts it back. o: {title, value, min, max, step, marks, fmt, input(v), keep(v), cancel()}.
const QOL_PT = {x: innerWidth / 2, y: innerHeight / 2};
document.addEventListener('pointerdown', e => { QOL_PT.x = e.clientX; QOL_PT.y = e.clientY; }, true);
document.addEventListener('contextmenu', e => { QOL_PT.x = e.clientX; QOL_PT.y = e.clientY; }, true);
let qolSlideOpen = null;
function qolSlide(o){
  if (qolSlideOpen) qolSlideOpen.done(false);
  const box = document.createElement('div');
  box.className = 'qslide';
  const fmt = o.fmt || (v => String(v));
  box.innerHTML = `<div class="qs-t">${esc(o.title)}</div>
    <div class="qs-row"><input type="range" class="qs-r" min="${o.min}" max="${o.max}" step="${o.step}" value="${o.value}">
      <input class="inp qs-n" value="${fmt(o.value)}" spellcheck="false"></div>
    ${o.marks ? `<div class="qs-m">${o.marks.map(m => `<button class="btn sm" type="button" data-qm="${m}">${fmt(m)}</button>`).join('')}</div>` : ''}
    <div class="qs-f"><span class="msg">Enter or click away keeps it · Esc undoes</span><button class="btn sm" type="button" data-qx>✕</button><button class="btn sm primary" type="button" data-qk>✓</button></div>`;
  document.body.appendChild(box);
  const R = box.querySelector('.qs-r'), N = box.querySelector('.qs-n');
  // (by the pointer, kept inside the window)
  const w = box.offsetWidth, h = box.offsetHeight;
  box.style.left = Math.max(8, Math.min(innerWidth - w - 8, QOL_PT.x - w / 2)) + 'px';
  box.style.top = Math.max(8, Math.min(innerHeight - h - 8, QOL_PT.y + 12)) + 'px';
  let v = o.value;
  const set = (x, from) => {
    x = Math.max(o.min, Math.min(o.max, x));
    if (!isFinite(x)) return;
    v = x;
    if (from !== 'r') R.value = x;
    if (from !== 'n') N.value = fmt(x);
    o.input && o.input(x);
  };
  R.oninput = () => set(parseFloat(R.value), 'r');
  N.oninput = () => { const x = parseFloat(N.value.replace(',', '.')); if (isFinite(x) && x > 0) set(x, 'n'); };
  box.onwheel = e => { e.preventDefault(); set(Math.round((v - Math.sign(e.deltaY) * o.step) / o.step) * o.step, null); };
  box.querySelectorAll('[data-qm]').forEach(b => b.onclick = () => set(parseFloat(b.dataset.qm), null));
  const away = e => { if (!box.contains(e.target)) done(true); };
  const keys = e => {
    if (e.key === 'Escape'){ e.preventDefault(); e.stopPropagation(); done(false); }
    else if (e.key === 'Enter'){ e.preventDefault(); e.stopPropagation(); done(true); }
  };
  function done(keep){
    if (!box.isConnected) return;
    box.remove(); qolSlideOpen = null;
    document.removeEventListener('pointerdown', away, true);
    document.removeEventListener('keydown', keys, true);
    if (keep && v !== o.value) o.keep(v); else o.cancel && o.cancel();
  }
  box.querySelector('[data-qk]').onclick = () => done(true);
  box.querySelector('[data-qx]').onclick = () => done(false);
  setTimeout(() => { document.addEventListener('pointerdown', away, true); document.addEventListener('keydown', keys, true); }, 0);
  qolSlideOpen = {done};
  R.focus();
  return box;
}

// ---------------------------------------------------------------- scaling (one thing or a group)
// One thing: its own size, 0.5 to 2 as the game allows. Several: by how much, round their middle, so they
// keep their places to each other. Shown as you drag, written as one change when you keep it.
async function qolScale(){
  const sel = selectionRefs(); if (!sel.length) return false;
  const one = sel.length === 1;
  const was = sel.map(([cell, r]) => ({r, p: r.p.slice(), s: r.s || 1}));
  const xs = sel.map(s => s[1].p[0]), ys = sel.map(s => s[1].p[1]);
  const cx = (Math.min(...xs) + Math.max(...xs)) / 2, cy = (Math.min(...ys) + Math.max(...ys)) / 2, cz = Math.min(...sel.map(s => s[1].p[2]));
  // (what each would become for a slider value v: the size for one, the factor for several)
  const plan = v => was.map(w => {
    const f = one ? v / w.s : v;
    const p = w.p.slice();
    if (!one){ p[0] = cx + (w.p[0] - cx) * f; p[1] = cy + (w.p[1] - cy) * f; p[2] = cz + (w.p[2] - cz) * f; }
    const s = Math.round(Math.max(0.5, Math.min(2, w.s * f)) * 1000) / 1000;      // (the game allows 0.5 to 2)
    return {w, p, s, clamped: w.s * f < 0.5 - 1e-6 || w.s * f > 2 + 1e-6};
  });
  const show = v => { for (const x of plan(v)){ x.w.r.p = x.p; x.w.r.s = x.s; } drawMap(); if (W.sel) renderWside && renderWside(); };
  const back = () => { for (const w of was){ w.r.p = w.p; w.r.s = w.s; } drawMap(); if (W.sel) renderWside && renderWside(); };
  const name = one ? (sel[0][1].name || sel[0][1].id) : sel.length + ' objects';
  qolSlide({
    title: one ? `Size of ${name}` : `Make the ${sel.length} bigger or smaller (×)`,
    value: one ? was[0].s : 1, min: 0.5, max: 2, step: 0.01,
    marks: one ? [0.5, 0.75, 1, 1.25, 1.5, 2] : [0.5, 0.8, 1, 1.25, 1.5, 2],
    fmt: v => (Math.round(v * 100) / 100).toString(),
    input: show,
    cancel: back,
    keep: async v => {
      const xs_ = plan(v);
      back();
      if (!await needProject()) return;
      const moves = xs_.map((x, n) => ({cell: sel[n][0], ref: sel[n][1].k, p: x.p, s: x.s}));
      const clamped = xs_.filter(x => x.clamped).length;
      const say = one ? `${name} now at size ${Math.round(xs_[0].s * 100) / 100}` : `Scaled ${name} by ${Math.round(v * 100) / 100}`;
      await groupAction('/api/group/move', {moves}, say + (clamped ? ` (${clamped} stopped at the game's limit of 0.5 to 2)` : ''));
    }});
}

// ---------------------------------------------------------------- tilt: lean what's selected forwards or sideways
// (the game keeps a turn about X, Y and Z for everything placed; each thing leans about its own spot)
function qolTilt(){
  const sel = selectionRefs(); if (!sel.length) return false;
  const one = sel.length === 1, name = one ? (sel[0][1].name || sel[0][1].id) : sel.length + ' objects';
  const was = sel.map(([cell, r]) => ({cell, r, p: r.p.slice()}));
  const deg = v => Math.round(((v * 180 / Math.PI + 540) % 360 - 180) * 10) / 10;
  // (one thing starts at its own tilt; several start level, and the sliders add to what each has)
  let fx = one ? deg(was[0].p[3]) : 0, fy = one ? deg(was[0].p[4]) : 0;
  const plan = () => was.map(w => {
    const p = w.p.slice();
    if (one){ p[3] = fx * Math.PI / 180; p[4] = fy * Math.PI / 180; }
    else { p[3] = w.p[3] + fx * Math.PI / 180; p[4] = w.p[4] + fy * Math.PI / 180; }
    return {w, p};
  });
  const show = () => { for (const x of plan()) x.w.r.p = x.p; drawMap(); if (typeof v3Refresh === 'function') v3Refresh(); };
  const back = () => { for (const w of was) w.r.p = w.p; drawMap(); if (typeof v3Refresh === 'function') v3Refresh(); };
  const bg = document.createElement('div'); bg.className = 'modal-bg';
  const row = (k, label, v) => `<label>${label}</label><div style="display:flex;gap:8px;align-items:center">
      <input type="range" min="-90" max="90" step="1" value="${v}" data-tr="${k}" style="flex:1"><input class="inp" data-tn="${k}" value="${v}" style="width:70px"><span class="msg">°</span></div>`;
  bg.innerHTML = `<div class="modal" style="width:min(460px,94vw)"><h2>Tilt ${esc(name)}</h2>
    <div class="msg">${one ? 'Lean it forwards or sideways' : 'Lean each of them forwards or sideways, on top of the tilt it has'}, keeping which way it faces. The game keeps it as it is shown here.</div>
    <div class="frow" style="margin-top:10px">${row('x', 'Forwards (X)', fx)}${row('y', 'Sideways (Y)', fy)}</div>
    <div class="actions" style="margin-top:12px"><button class="btn sm" data-tl="level">Level ${one ? 'it' : 'them'}</button>
      ${typeof V3 !== 'undefined' && V3.on ? '<button class="btn sm" data-tl="handles" title="The turning handles in the 3D view, with the two tilt rings shown">Tilt with the handles</button>' : ''}
      <span style="flex:1"></span><button class="btn sm" data-tl="cancel">Cancel</button><button class="btn sm primary" data-tl="keep">Keep</button></div></div>`;
  document.body.appendChild(bg);
  const sync = () => {
    bg.querySelector('[data-tr=x]').value = fx; bg.querySelector('[data-tn=x]').value = fx;
    bg.querySelector('[data-tr=y]').value = fy; bg.querySelector('[data-tn=y]').value = fy;
    show();
  };
  const setv = (k, v) => { v = Math.max(-90, Math.min(90, v)); if (!isFinite(v)) return; if (k === 'x') fx = v; else fy = v; };
  bg.querySelectorAll('[data-tr]').forEach(el => el.oninput = () => { setv(el.dataset.tr, parseFloat(el.value)); sync(); });
  bg.querySelectorAll('[data-tn]').forEach(el => el.onchange = () => { setv(el.dataset.tn, parseFloat(el.value.replace(',', '.'))); sync(); });
  const close = () => { bg.remove(); document.removeEventListener('keydown', keys, true); };
  const cancel = () => { back(); close(); };
  const keep = async () => {
    const xs = plan(); back(); close();
    if (xs.every(x => x.p[3] === x.w.p[3] && x.p[4] === x.w.p[4])) return;
    if (!await needProject()) return;
    const moves = xs.map(x => ({cell: x.w.cell, ref: x.w.r.k, p: x.p, s: x.w.r.s || 1}));
    await groupAction('/api/group/move', {moves}, one ? `Tilted ${name} (${fx}° forwards, ${fy}° sideways)` : `Tilted ${name}`);
  };
  const keys = e => { if (e.key === 'Escape'){ e.preventDefault(); e.stopPropagation(); cancel(); } else if (e.key === 'Enter'){ e.preventDefault(); e.stopPropagation(); keep(); } };
  document.addEventListener('keydown', keys, true);
  bg.querySelector('[data-tl=level]').onclick = () => {
    if (one){ fx = 0; fy = 0; sync(); return; }
    // (several: each one level, whatever tilt it had)
    close();
    (async () => {
      if (!await needProject()) return;
      await groupAction('/api/group/move', {moves: was.map(w => ({cell: w.cell, ref: w.r.k, p: [w.p[0], w.p[1], w.p[2], 0, 0, w.p[5]], s: w.r.s || 1}))}, `Levelled ${name}`);
    })();
  };
  bg.querySelector('[data-tl=cancel]').onclick = cancel;
  bg.querySelector('[data-tl=keep]').onclick = keep;
  const hb = bg.querySelector('[data-tl=handles]');
  if (hb) hb.onclick = () => {
    cancel();
    V3.tilt = true; V3.mode = 'rotate';
    if (typeof v3ApplyMode === 'function') v3ApplyMode();
    if (typeof v3Tools === 'function') v3Tools();
    toast('Turning with tilt: drag the red or green ring to lean it, the blue one to turn it.');
  };
  return true;
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
  {id: 'redrawpaths', label: 'Redraw the walking paths here (Project Tamriel\'s rules)', keys: [], world: true, run: () => redrawPaths()},
  {id: 'marks', label: 'Mark my changes on the map (on / off)', keys: [], world: true, run: () => { setMarks(!W.marks); drawMap(); renderWside(); }},
  {id: 'changes', label: 'My changes (the list)', keys: [], world: true, run: () => PNL.show('world', 'changes')},
  {id: 'through', label: 'Go through the selected door', keys: ['Enter'], world: true, run: () => {
    const r = cfSelRef(); if (!r || !r.to || ['BUTTON', 'A'].includes((document.activeElement || {}).tagName)) return false;
    qolThrough(W.sel.cell, r);
  }},
  {id: 'back', label: 'Back through the door (the place before)', keys: ['Alt+ArrowLeft'], world: true, run: () => QOL.back.length ? qolBack() : false},
  {id: 'reopen', label: 'Reopen the last place you worked on', keys: [], run: () => qolReopen()},
  {id: 'scale', label: 'Scale what\'s selected…', keys: [], world: true, run: () => qolScale()},
  {id: 'tilt', label: 'Tilt what\'s selected…', keys: [], world: true, run: () => qolTilt()},
  {id: 'replace', label: 'Search and replace objects…', keys: ['Ctrl+H'], world: true, run: () => qolReplace(cfSelRef() ? cfSelRef().id : '')},
  {id: 'setups', label: 'Test setups for Play…', keys: [], run: () => qolSetups()},
  {id: 'find', label: 'Find in the list (Objects, or the search box)', keys: ['Ctrl+F'], run: () => {
    if (cfWorldOn()){ PNL.show('world', 'objs'); setTimeout(() => { const f = $('#w-filter'); if (f){ f.focus(); f.select(); } }, 30); return; }
    if ($('#browse').classList.contains('on')){ $('#q').focus(); $('#q').select(); return; }
    return false;
  }},
);
