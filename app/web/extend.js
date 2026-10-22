// Add a room through a wall: right-click an outer wall of a place built from pieces, and a see-through room
// appears beyond it, drawn as the kit's own pieces where they would stand; a small card sets its size, name
// and kind; Build lays only the new room and the doorway (the rest of the house stays as it is) and furnishes
// it (app/extend.py). The ghost is the planner's "fits here" / Fix here preview (v3GhostAt).
const EX = {card: null, cell: null, ref: null, at: null, w: 3, h: 3, shift: 0, name: '', kind: '', furnish: true, last: null, busy: false};

const EX_KINDS = ['Bedroom', 'Study', 'Library', 'Dining room', 'Kitchen', 'Hall', 'Storeroom', 'Shop', 'Bath', 'Shrine', 'Guard room', 'Workshop'];

async function extendStart(cell, ref, at){
  if (!await needProject()) return;
  extendClose();
  EX.cell = cell; EX.ref = ref || null; EX.at = at || null; EX.w = 3; EX.h = 3; EX.shift = 0; EX.name = 'Bedroom'; EX.furnish = true;
  const card = document.createElement('div'); card.className = 'modal'; card.id = 'ex-card';
  card.style.cssText = 'position:absolute;right:24px;bottom:72px;width:300px;z-index:30;box-shadow:0 6px 24px #0008';
  card.innerHTML = `<h2 style="margin:0 0 6px;font-size:16px">➕ Add a room through this wall</h2>
    <div class="msg" id="ex-where"><span class="spin"></span> Reading the wall…</div>
    <div style="display:flex;gap:6px;margin-top:8px;flex-wrap:wrap">
      <button class="btn sm" data-exp="3,3" title="A square room, three tiles each way">Room 3×3</button>
      <button class="btn sm" data-exp="4,4" title="A big room">Hall 4×4</button>
      <button class="btn sm" data-exp="1,4" title="A passage one tile wide, four deep">Corridor 1×4</button>
      <button class="btn sm" data-exp="2,2" title="A small room">Closet 2×2</button>
    </div>
    <div class="frow" style="display:grid;grid-template-columns:1fr 1fr;gap:6px 10px;margin-top:8px">
      <label>Kind<select class="inp" id="ex-kind">${EX_KINDS.map(k => `<option ${k === 'Bedroom' ? 'selected' : ''}>${k}</option>`).join('')}</select></label>
      <label>Name<input class="inp" id="ex-name" value="Bedroom" maxlength="40"></label>
      <label>Along the wall<input class="inp" id="ex-w" type="number" min="1" max="6" value="3"></label>
      <label>Deep<input class="inp" id="ex-h" type="number" min="1" max="6" value="3"></label>
      <label style="grid-column:1/3">Slide along the wall <input id="ex-shift" type="range" min="-3" max="3" value="0" style="width:100%"></label>
      <label class="msg" style="grid-column:1/3;display:flex;gap:6px;align-items:center"><input type="checkbox" id="ex-furnish" checked> Furnish it (the game's way, as this kind of room)</label>
    </div>
    <div class="msg err" id="ex-err" style="margin-top:6px"></div>
    <div class="foot" style="margin-top:8px"><button class="btn" id="ex-cancel">Cancel</button><button class="btn primary" id="ex-go" disabled>Build it</button></div>`;
  $('#v3wrap').appendChild(card);
  EX.card = card;
  const q = s => card.querySelector(s);
  q('#ex-cancel').onclick = extendClose;
  q('#ex-kind').onchange = () => { EX.kind = q('#ex-kind').value; q('#ex-name').value = EX.kind; EX.name = EX.kind; extendPreview(); };
  q('#ex-name').oninput = () => { EX.name = q('#ex-name').value; };
  q('#ex-w').onchange = () => { EX.w = Math.max(1, Math.min(6, +q('#ex-w').value || 3)); extendPreview(); };
  q('#ex-h').onchange = () => { EX.h = Math.max(1, Math.min(6, +q('#ex-h').value || 3)); extendPreview(); };
  q('#ex-shift').oninput = () => { EX.shift = +q('#ex-shift').value; extendPreview(); };
  q('#ex-furnish').onchange = () => { EX.furnish = q('#ex-furnish').checked; };
  q('#ex-go').onclick = extendBuild;
  card.querySelectorAll('[data-exp]').forEach(b => b.onclick = () => {
    const [w, h] = b.dataset.exp.split(',').map(Number);
    EX.w = w; EX.h = h; q('#ex-w').value = w; q('#ex-h').value = h;
    if (w === 1){ EX.kind = 'Hall'; q('#ex-kind').value = 'Hall'; q('#ex-name').value = 'Passage'; EX.name = 'Passage'; }
    extendPreview();
  });
  await extendPreview();
}

async function extendPreview(){
  const card = EX.card; if (!card) return;
  const q = s => card.querySelector(s);
  let r;
  try { r = await post('/api/extend/options', {cell: EX.cell, ref: EX.ref, at: EX.at, w: EX.w, h: EX.h, shift: EX.shift, name: EX.name}); }
  catch (e){ q('#ex-where').textContent = ''; q('#ex-err').textContent = e.message; q('#ex-go').disabled = true; if (typeof v3GhostClear === 'function') v3GhostClear(); return; }
  if (!EX.card) return;
  EX.last = r;
  const sides = {N: 'north', E: 'east', S: 'south', W: 'west'};
  q('#ex-where').innerHTML = `Through the <b>${sides[r.side]}</b> wall of <b>${esc(r.from)}</b>: a ${r.room.w} × ${r.room.h} tile room of ${esc(r.style)} pieces${r.fits ? '' : ''}.`;
  q('#ex-err').textContent = r.fits ? '' : (r.note || 'It does not fit there.');
  q('#ex-go').disabled = !r.fits;
  if (typeof v3GhostAt === 'function' && V3.on) v3GhostAt(r.ghost || []);
}

async function extendBuild(){
  const card = EX.card; if (!card || EX.busy) return;
  const q = s => card.querySelector(s);
  EX.busy = true; q('#ex-go').disabled = true; q('#ex-go').innerHTML = '<span class="spin"></span> Building…';
  try {
    const m = await post('/api/extend/apply', {cell: EX.cell, ref: EX.ref, at: EX.at, w: EX.w, h: EX.h, shift: EX.shift, name: EX.name,
                                               furnish: EX.furnish, level: (typeof furnishAsValue === 'function' && $('#fu-level')) ? furnishAsValue('fu') : null});
    const cell = EX.cell;
    extendClose();
    toast(`Added the ${m.room} (${m.pieces} pieces${m.furnished ? ', ' + m.placed + ' things' : ''}). Undo takes it back.` + (m.note ? ' ' + m.note : ''), !!m.note);
    if (typeof worldReloadCell === 'function') await worldReloadCell(cell);
    if (typeof afterChange === 'function') afterChange();
    if (typeof v3Refresh === 'function' && V3.on) v3Refresh();
    W.roomInfo = {}; W.dressable = {};
  } catch (e){
    EX.busy = false;
    if (EX.card){ q('#ex-err').textContent = e.message; q('#ex-go').disabled = false; q('#ex-go').textContent = 'Build it'; }
  }
}

function extendClose(){
  if (EX.card){ EX.card.remove(); EX.card = null; }
  EX.busy = false;
  if (typeof v3GhostClear === 'function') v3GhostClear();
}
