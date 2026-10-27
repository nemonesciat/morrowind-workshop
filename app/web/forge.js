// ---------- The Forge: a new weapon or armour piece with the numbers the game gives its type and material ----------
// (gearsurvey.py) Pick what it is and its material, or a new material between two of the game's; the Workshop
// fills in the game's typical numbers for that kind of piece, shows the game's own range beside each, and
// says when yours go beyond anything the game does (more than 15% past its range: 92% of the game's own
// pieces fall inside). The look is taken from one of the game's pieces of that kind; armour shows its weight
// class by the game's own rule. "Forge it" makes the record (items.create_item), one Undo.
const FG = {bg: null, opts: null, kind: 'weapon', type: null, mat: null, between: null, p: null, look: null, stats: {}, edited: {}, seq: 0};

// start: {kind, like: record index} a piece like that one; {world: item id} straight to Into the world for it
async function forgeShow(start){
  if (FG.bg) FG.bg.remove();
  const bg = document.createElement('div'); bg.className = 'modal-bg'; FG.bg = bg;
  FG.tab = start && start.world ? 'world' : 'piece';
  if (start && start.world) FG.world = {id: start.world};
  bg.innerHTML = `<div class="modal fg-win"><h2>⚒ The Forge</h2>
    <div class="fg-tabs"><button data-fgtab="piece">A piece</button><button data-fgtab="set">A whole set</button><span class="fg-tsep">then</span><button data-fgtab="world">Into the world</button></div>
    <div id="fg-body"><div class="msg"><span class="spin"></span>Reading the game's weapons and armour…</div></div>
    <div class="foot"><span class="msg" id="fg-msg" style="flex:1"></span><button class="btn" id="fg-close">Close</button><button class="btn primary" id="fg-go" disabled>⚒ Forge it</button></div></div>`;
  document.body.appendChild(bg);
  fgCss();
  bg.querySelector('#fg-close').onclick = () => { bg.remove(); FG.bg = null; };
  bg.querySelector('#fg-go').onclick = () => FG.tab === 'world' ? fgPlace() : FG.tab === 'set' ? fgSetMake() : fgMake();
  bg.querySelectorAll('[data-fgtab]').forEach(b => b.onclick = () => fgTab(b.dataset.fgtab));
  fgTabs();
  if (FG.tab === 'world') return fgWorld();
  try {
    FG.opts = FG.opts || await api('/api/forge/options');
    if (start){
      Object.assign(FG, {kind: start.kind || FG.kind, between: null, edited: {}});
      // (a piece like this one: its type and material, and its look)
      if (start.like != null){ try { const l = await api('/api/forge/like?i=' + start.like); Object.assign(FG, {type: l.type, mat: l.mat}); FG.look = l.i; } catch (e){} }
    }
    if (!FG.type || !fgTypes().some(t => t.id === FG.type)) FG.type = fgTypes()[0].id;
    if (!FG.mat || !fgMats().some(m => m.id === FG.mat)) FG.mat = (fgMats()[Math.floor(fgMats().length / 2)] || {}).id;
    fgDraw(); await fgPropose();
  } catch (e){ const b = bg.querySelector('#fg-body'); if (b) b.innerHTML = `<div class="msg err">${esc(e.message)}</div>`; }
}
function fgTypes(){ return FG.opts[FG.kind] || []; }
function fgMats(){ const t = fgTypes().find(x => x.id === FG.type); return t ? t.materials : []; }
function fgMsg(t, err){ const m = FG.bg && FG.bg.querySelector('#fg-msg'); if (m){ m.className = 'msg' + (err ? ' err' : ''); m.innerHTML = t; } }
const FG_CAP = s => s ? s.charAt(0).toUpperCase() + s.slice(1) : s;

function fgDraw(){
  const box = FG.bg && FG.bg.querySelector('#fg-body'); if (!box) return;
  const all = FG.opts.all_materials;
  box.innerHTML = `<div class="fg-grid">
    <div class="fg-side">
      <div class="fg-h">What it is</div>
      <div class="fg-row"><button class="btn sm ${FG.kind === 'weapon' ? 'primary' : ''}" data-fgk="weapon">🗡 Weapon</button><button class="btn sm ${FG.kind === 'armor' ? 'primary' : ''}" data-fgk="armor">🛡 Armour</button></div>
      <select class="inp" id="fg-type">${fgTypes().map(t => `<option value="${t.id}" ${t.id === FG.type ? 'selected' : ''}>${esc(t.label)}</option>`).join('')}</select>
      <div class="fg-h" style="margin-top:10px">Material</div>
      <label class="msg fg-radio"><input type="radio" name="fg-m" value="game" ${FG.between ? '' : 'checked'}> One of the game's</label>
      <select class="inp" id="fg-mat" ${FG.between ? 'disabled' : ''}>${fgMats().map(m => `<option value="${m.id}" ${m.id === FG.mat ? 'selected' : ''}>${esc(FG_CAP(m.id))} (${m.n} in the game)</option>`).join('')}</select>
      <label class="msg fg-radio" style="margin-top:6px"><input type="radio" name="fg-m" value="between" ${FG.between ? 'checked' : ''}> A new material between two of the game's</label>
      <div class="fg-row" ${FG.between ? '' : 'style="opacity:.5;pointer-events:none"'}>
        <select class="inp" id="fg-a">${all.map(m => `<option ${FG.between && FG.between[0] === m ? 'selected' : ''}>${m}</option>`).join('')}</select>
        <select class="inp" id="fg-b">${all.map(m => `<option ${FG.between && FG.between[1] === m ? 'selected' : ''}>${m}</option>`).join('')}</select></div>
      <label class="msg fg-row" ${FG.between ? '' : 'style="opacity:.5;pointer-events:none"'}>nearer the first <input type="range" id="fg-f" min="0" max="1" step="0.05" value="${FG.between ? FG.between[2] : 0.5}" style="flex:1"> nearer the second</label>
      <div class="fg-h" style="margin-top:10px">Name</div>
      <input class="inp" id="fg-name" placeholder="e.g. Glass Saber of the Wolf" value="${esc(FG.name || '')}">
      <div class="msg" style="margin-top:4px">ID <input class="inp" id="fg-id" style="width:62%" value="${esc(FG.id || '')}" placeholder="made from the name"></div>
      <div class="fg-h" style="margin-top:10px">Its look <span class="msg">(the game's ${FG.between ? 'pieces of either material' : 'pieces of this kind'})</span></div>
      <div class="fg-looks" id="fg-looks"></div>
    </div>
    <div class="fg-main">
      <div class="fg-h">Its numbers <span class="msg" id="fg-basis"></span></div>
      <table class="t fg-t" id="fg-stats"></table>
      <div id="fg-class" class="msg" style="margin-top:6px"></div>
      <div id="fg-notes" style="margin-top:6px"></div>
      <div class="msg" style="margin-top:8px;font-size:11.5px">Numbers start at the game's middle for this kind, with its lowest and highest beside them. A badge marks any you push well past the game's. Enchant it later in the item editor.</div>
    </div></div>`;
  box.querySelectorAll('[data-fgk]').forEach(b => b.onclick = () => { FG.kind = b.dataset.fgk; FG.type = fgTypes()[0].id; FG.mat = (fgMats()[Math.floor(fgMats().length / 2)] || {}).id; FG.edited = {}; fgDraw(); fgPropose(); });
  box.querySelector('#fg-type').onchange = e => { FG.type = e.target.value; if (!fgMats().some(m => m.id === FG.mat)) FG.mat = (fgMats()[Math.floor(fgMats().length / 2)] || {}).id; FG.edited = {}; fgDraw(); fgPropose(); };
  box.querySelector('#fg-mat').onchange = e => { FG.mat = e.target.value; FG.edited = {}; fgPropose(); };
  box.querySelectorAll('[name=fg-m]').forEach(r => r.onchange = () => {
    FG.between = r.value === 'between' && r.checked ? [box.querySelector('#fg-a').value, box.querySelector('#fg-b').value, +box.querySelector('#fg-f').value] : null;
    if (r.value === 'between' && r.checked && FG.between[0] === FG.between[1]){ const i = all.indexOf(FG.between[0]); FG.between[1] = all[Math.min(all.length - 1, i + 3)]; }
    FG.edited = {}; fgDraw(); fgPropose();
  });
  const bw = () => { if (!FG.between) return; FG.between = [box.querySelector('#fg-a').value, box.querySelector('#fg-b').value, +box.querySelector('#fg-f').value]; FG.edited = {}; fgPropose(); };
  box.querySelector('#fg-a').onchange = bw; box.querySelector('#fg-b').onchange = bw; box.querySelector('#fg-f').onchange = bw;
  const nm = box.querySelector('#fg-name'), idb = box.querySelector('#fg-id');
  nm.oninput = () => { FG.name = nm.value; fgIdSoon(); fgReady(); };
  idb.oninput = () => { FG.id = idb.value; FG.idEdited = !!idb.value; fgReady(); };
}

async function fgPropose(){
  const seq = ++FG.seq;
  const q = new URLSearchParams({kind: FG.kind, type: FG.type});
  if (FG.between) q.set('between', FG.between.join(',')); else if (FG.mat) q.set('mat', FG.mat);
  try {
    const p = await api('/api/forge/propose?' + q.toString());
    if (seq !== FG.seq) return;
    FG.p = p;
    FG.stats = Object.assign({}, p.stats, FG.edited);
    if (!FG.look || !p.looks.some(l => l.i === FG.look)) FG.look = p.looks.length ? p.looks[0].i : null;
    fgStatsDraw(); fgLooksDraw(); fgCheck(); fgReady();
  } catch (e){ fgMsg(esc(e.message), true); }
}

function fgStatsDraw(){
  const t = FG.bg && FG.bg.querySelector('#fg-stats'); if (!t || !FG.p) return;
  const p = FG.p, b = FG.bg.querySelector('#fg-basis');
  if (b) b.textContent = p.borrowed && p.borrowed[0] !== p.borrowed[1] ? `(between the game's ${p.borrowed[0]} and ${p.borrowed[1]})` : p.n ? `(the game has ${p.n} like it)` : '';
  // (a weapon's damage in pairs, as the game shows them; a bow's or a thrown weapon's only by its chop)
  const rows = Object.keys(p.ranges);
  t.innerHTML = `<tr><th></th><th>Yours</th><th>The game's</th><th></th></tr>` + rows.map(lab => {
    const r = p.ranges[lab];
    return `<tr><td>${esc(lab)}</td><td><input class="inp num" data-fgs="${esc(lab)}" value="${FG.stats[lab]}"></td>
      <td class="msg">${r.lo} – ${r.hi} <span class="faint">(mostly ${r.p10}–${r.p90})</span></td><td><span class="fg-b" data-fgb="${esc(lab)}"></span></td></tr>`;
  }).join('');
  t.querySelectorAll('[data-fgs]').forEach(inp => inp.oninput = () => {
    const v = parseFloat(inp.value); if (!isFinite(v)) return;
    FG.stats[inp.dataset.fgs] = v; FG.edited[inp.dataset.fgs] = v; fgCheckSoon();
  });
}
function fgLooksDraw(){
  const box = FG.bg && FG.bg.querySelector('#fg-looks'); if (!box || !FG.p) return;
  const tt = FG.kind === 'weapon' ? 'WEAP' : 'ARMO';
  box.innerHTML = FG.p.looks.slice(0, 18).map(l => `<button class="fg-look ${l.i === FG.look ? 'on' : ''}" data-fgl="${l.i}" title="${esc(l.name)} (${esc(l.id)})">
    <img class="thumb" data-tid="${esc(l.id)}" data-tt="${tt}" data-ts="72" alt=""><span>${esc(l.name)}</span></button>`).join('') || '<span class="msg">The game has no piece of this kind to take the look from.</span>';
  box.querySelectorAll('[data-fgl]').forEach(b => b.onclick = () => { FG.look = +b.dataset.fgl; box.querySelectorAll('.fg-look').forEach(x => x.classList.toggle('on', x === b)); fgReady(); });
  if (typeof v3ThumbScan === 'function') v3ThumbScan(box);
}
let FG_T = 0, FG_ID = 0;
function fgCheckSoon(){ clearTimeout(FG_T); FG_T = setTimeout(fgCheck, 250); }
async function fgCheck(){
  if (!FG.p || !FG.bg) return;
  try {
    const r = await post('/api/forge/check', {kind: FG.kind, type: FG.type, mat: FG.between ? null : FG.mat, between: FG.between, stats: FG.stats});
    FG.bg.querySelectorAll('[data-fgb]').forEach(el => {
      const st = r.states[el.dataset.fgb];
      el.className = 'fg-b ' + (st || '');
      el.textContent = st === 'high' ? '▲ beyond the game' : st === 'low' ? '▼ below the game' : st === 'ok' ? '✓' : '';
    });
    const n = FG.bg.querySelector('#fg-notes');
    if (n) n.innerHTML = r.notes.map(x => `<div class="msg warn">${esc(x)}</div>`).join('');
    const c = FG.bg.querySelector('#fg-class');
    if (c) c.innerHTML = r.weight_class ? `Weight class: <b>${r.weight_class}</b> (the game's rule, from its weight: it decides which armour skill it trains)` : '';
  } catch (e){ fgMsg(esc(e.message), true); }
}
function fgIdSoon(){
  if (FG.idEdited) return;
  clearTimeout(FG_ID);
  FG_ID = setTimeout(async () => {
    if (!FG.name || !FG.bg) return;
    try { const r = await api('/api/create/suggest_id?name=' + encodeURIComponent(FG.name)); FG.id = r.id; const b = FG.bg.querySelector('#fg-id'); if (b && !FG.idEdited) b.value = r.id; fgReady(); } catch (e){}
  }, 300);
}
function fgReady(){
  const go = FG.bg && FG.bg.querySelector('#fg-go'); if (!go) return;
  if (FG.tab === 'world') return fgWorldReady();
  if (FG.tab === 'set') return fgSetReady();
  go.disabled = !(FG.p && FG.look != null && (FG.name || '').trim() && (FG.id || '').trim());
  // (what was just forged stays said until the next one is named)
  if (FG.made && !(FG.name || '').trim()) return;
  FG.made = false;
  if (go.disabled) fgMsg(!FG.look ? 'Pick its look.' : !(FG.name || '').trim() ? 'Give it a name.' : '');
  else fgMsg('');
}

async function fgMake(){
  if (!await needProject()) return;
  const stats = {};
  for (const [k, v] of Object.entries(FG.stats)) stats[k] = v;
  try {
    const r = await post('/api/items/create', {template: FG.look, id: FG.id.trim(), name: FG.name.trim(), stats});
    if (typeof afterChange === 'function') afterChange();
    const name = FG.name;
    FG.name = ''; FG.id = ''; FG.idEdited = false; FG.made = true;
    // (straight on to where the game would find it: the second step, which can be left at Close)
    FG.world = {id: r.id, i: r.i, forged: name, mat: FG.between ? null : FG.mat, between: FG.between};
    fgTab('world');
  } catch (e){ fgMsg(esc(e.message), true); }
}

// ---------- the two steps: the piece, then into the world ----------
function fgTabs(){
  if (!FG.bg) return;
  FG.bg.querySelectorAll('[data-fgtab]').forEach(b => {
    b.classList.toggle('on', b.dataset.fgtab === FG.tab);
    b.disabled = b.dataset.fgtab === 'world' && !FG.world;
    b.title = b.disabled ? 'Forge a piece first (or right-click any weapon or armour: Into the world)' : '';
  });
  const go = FG.bg.querySelector('#fg-go');
  if (go) go.innerHTML = FG.tab === 'world' ? '🌐 Put it into the world' : FG.tab === 'set' ? '⚒ Forge the set' : '⚒ Forge it';
}
async function fgTab(t){
  if (t === 'world' && !FG.world) return;
  FG.tab = t; fgTabs(); fgMsg('');
  if (t === 'world') return fgWorld();
  if (t === 'set') return fgSet();
  if (!FG.opts){ try { FG.opts = await api('/api/forge/options'); } catch (e){ return fgMsg(esc(e.message), true); } }
  if (!FG.type || !fgTypes().some(x => x.id === FG.type)) FG.type = fgTypes()[0].id;
  if (!FG.mat || !fgMats().some(m => m.id === FG.mat)) FG.mat = (fgMats()[Math.floor(fgMats().length / 2)] || {}).id;
  fgDraw(); await fgPropose();
}

// ---------- a whole set: one look, one set of numbers, a name; every piece the look's material has (gearsets.py)
async function fgSet(){
  const box = FG.bg && FG.bg.querySelector('#fg-body'); if (!box) return;
  if (!FG.set){
    box.innerHTML = '<div class="msg"><span class="spin"></span>Reading the game\'s sets…</div>';
    try { FG.set = {opts: await api('/api/forge/setoptions'), numbers: 'same', stem: '', names: {}, pieces: []}; }
    catch (e){ box.innerHTML = `<div class="msg err">${esc(e.message)}</div>`; return; }
    const st = FG.set, steel = st.opts.looks.find(l => l.material === 'steel') || st.opts.looks[0];
    st.look = steel.material; st.mat = steel.material;
    st.armor = fgSetSlots(steel); st.weapons = new Set();
    const all = st.opts.all_materials; st.between = [steel.material, all[Math.min(all.length - 1, all.indexOf(steel.material) + 3)], 0.5];
  }
  fgSetDraw(); fgSetPreview();
}
function fgSetLook(){ return FG.set.opts.looks.find(l => l.material === FG.set.look); }
// (every armour slot the look has, with gauntlets or bracers, as one is worn or the other: the pair the server
// picked, the one the base game has both of; its glass has bracers and only a right gauntlet)
function fgSetSlots(L){
  const drop = L.pair === 'gauntlet' ? /Bracer/ : L.pair === 'bracer' ? /Gauntlet/ : null;
  return new Set(L.armor.filter(t => !(drop && drop.test(t))));
}
function fgSetDraw(){
  const box = FG.bg && FG.bg.querySelector('#fg-body'), st = FG.set; if (!box || !st) return;
  const L = fgSetLook(), lab = st.opts.labels, all = st.opts.all_materials;
  const chip = (grp, t) => `<label class="fgw-chip"><input type="checkbox" data-sc="${grp}" value="${t}" ${st[grp].has(t) ? 'checked' : ''}>${esc(lab[t] || t)}</label>`;
  box.innerHTML = `<div class="fg-grid">
    <div class="fg-side">
      <div class="fg-h">It looks like</div>
      <select class="inp" id="fs-look">${st.opts.looks.map(l => `<option value="${l.material}" ${l.material === st.look ? 'selected' : ''}>The game's ${esc(l.material)} (${l.armor.length} armour pieces${l.weapons.length ? ', ' + l.weapons.length + ' weapons' : ''})</option>`).join('')}</select>
      <div class="fg-h" style="margin-top:10px">Its numbers</div>
      <label class="msg fg-radio"><input type="radio" name="fs-n" value="same" ${st.numbers === 'same' ? 'checked' : ''}> As the game's ${esc(st.look)}</label>
      <label class="msg fg-radio"><input type="radio" name="fs-n" value="game" ${st.numbers === 'game' ? 'checked' : ''}> As another of the game's materials</label>
      <select class="inp" id="fs-mat" ${st.numbers === 'game' ? '' : 'disabled'}>${all.map(m => `<option ${m === st.mat ? 'selected' : ''}>${m}</option>`).join('')}</select>
      <label class="msg fg-radio" style="margin-top:6px"><input type="radio" name="fs-n" value="between" ${st.numbers === 'between' ? 'checked' : ''}> A new material between two of the game's</label>
      <div class="fg-row" ${st.numbers === 'between' ? '' : 'style="opacity:.5;pointer-events:none"'}>
        <select class="inp" id="fs-a">${all.map(m => `<option ${st.between[0] === m ? 'selected' : ''}>${m}</option>`).join('')}</select>
        <select class="inp" id="fs-b">${all.map(m => `<option ${st.between[1] === m ? 'selected' : ''}>${m}</option>`).join('')}</select></div>
      <label class="msg fg-row" ${st.numbers === 'between' ? '' : 'style="opacity:.5;pointer-events:none"'}>nearer the first <input type="range" id="fs-f" min="0" max="1" step="0.05" value="${st.between[2]}" style="flex:1"> nearer the second</label>
      <div class="fg-h" style="margin-top:10px">The set's name</div>
      <input class="inp" id="fs-stem" placeholder="e.g. Sunsteel" value="${esc(st.stem)}">
      <div class="msg" style="font-size:11.5px;margin-top:3px">Each piece is named as its look is, with "${esc(st.look)}" swapped for this.</div>
      <div class="fg-h" style="margin-top:10px">Armour</div>
      <div class="fgw-chips">${L.armor.map(t => chip('armor', t)).join('')}</div>
      ${L.weapons.length ? `<div class="fg-h" style="margin-top:10px">Weapons to go with it</div><div class="fgw-chips">${L.weapons.map(t => chip('weapons', t)).join('')}</div>` : ''}
    </div>
    <div class="fg-main">
      <div class="fg-h">The set <span class="msg" id="fs-count"></span></div>
      <div id="fs-pieces" class="fs-pieces"><div class="msg"><span class="spin"></span></div></div>
      <div class="msg" style="margin-top:8px;font-size:11.5px">Each piece gets the game's numbers for its kind and material. Rename pieces here, change numbers later in the item editor. The whole set is one Undo.</div>
    </div></div>`;
  const redo = () => { fgSetDraw(); fgSetPreview(); };
  box.querySelector('#fs-look').onchange = e => { st.look = e.target.value; const L2 = fgSetLook(); st.armor = fgSetSlots(L2); st.weapons = new Set([...st.weapons].filter(t => L2.weapons.includes(t))); st.names = {}; redo(); };
  box.querySelectorAll('[name=fs-n]').forEach(r => r.onchange = () => { if (r.checked){ st.numbers = r.value; redo(); } });
  box.querySelector('#fs-mat').onchange = e => { st.mat = e.target.value; fgSetPreview(); };
  const bw = () => { st.between = [box.querySelector('#fs-a').value, box.querySelector('#fs-b').value, +box.querySelector('#fs-f').value]; fgSetPreview(); };
  box.querySelector('#fs-a').onchange = bw; box.querySelector('#fs-b').onchange = bw; box.querySelector('#fs-f').onchange = bw;
  let t_; box.querySelector('#fs-stem').oninput = e => { st.stem = e.target.value; st.names = {}; clearTimeout(t_); t_ = setTimeout(fgSetPreview, 300); fgSetReady(); };
  box.querySelectorAll('[data-sc]').forEach(c => c.onchange = () => { st[c.dataset.sc][c.checked ? 'add' : 'delete'](c.value); fgSetPreview(); });
}
function fgSetBody(){
  const st = FG.set, b = {look: st.look, stem: st.stem.trim() || 'New', armor: [...st.armor], weapons: [...st.weapons]};
  if (st.numbers === 'game') b.mat = st.mat; else if (st.numbers === 'between') b.between = st.between; else b.mat = st.look;
  return b;
}
async function fgSetPreview(){
  const st = FG.set, seq = ++FG.seq;
  try {
    const r = await post('/api/forge/setpreview', fgSetBody());
    if (seq !== FG.seq || !FG.bg) return;
    st.pieces = r.pieces;
    const box = FG.bg.querySelector('#fs-pieces'); if (!box) return;
    const main = p => p.kind === 'armor' ? `armour ${p.stats['Armor Rating']}` : `damage ${Math.max(p.stats['Chop Max'] || 0, p.stats['Slash Max'] || 0, p.stats['Thrust Max'] || 0)}`;
    box.innerHTML = r.pieces.map(p => `<div class="fs-piece"><img class="thumb" data-tid="${esc(p.look.id)}" data-tt="${p.kind === 'armor' ? 'ARMO' : 'WEAP'}" data-ts="48" alt="">
        <div class="fs-pn"><input class="inp" data-sn="${esc(p.type)}" value="${esc(st.names[p.type] || p.name)}"><span class="msg">${esc(p.label)} · ${main(p)} · weight ${p.stats.Weight}${p.weight_class ? ' (' + p.weight_class + ')' : ''} · value ${fmtN(p.stats.Value)}</span></div></div>`).join('')
      || '<div class="msg">Pick at least one piece on the left.</div>';
    const c = FG.bg.querySelector('#fs-count'); if (c) c.textContent = r.pieces.length ? `(${r.pieces.length} piece${r.pieces.length === 1 ? '' : 's'})` : '';
    box.querySelectorAll('[data-sn]').forEach(inp => inp.oninput = () => { st.names[inp.dataset.sn] = inp.value; });
    if (typeof v3ThumbScan === 'function') v3ThumbScan(box);
    fgSetReady();
  } catch (e){ fgMsg(esc(e.message), true); }
}
function fgSetReady(){
  const go = FG.bg && FG.bg.querySelector('#fg-go'); if (!go || FG.tab !== 'set') return;
  const st = FG.set;
  go.disabled = !(st && st.stem.trim() && st.pieces.length);
  fgMsg(!st || !st.stem.trim() ? 'Give the set a name.' : `${st.pieces.length} piece${st.pieces.length === 1 ? '' : 's'}`);
}
async function fgSetMake(){
  if (!await needProject()) return;
  const st = FG.set, go = FG.bg.querySelector('#fg-go'); go.disabled = true;
  fgMsg('<span class="spin"></span>Forging the set…');
  try {
    const r = await post('/api/forge/set', Object.assign(fgSetBody(), {stem: st.stem.trim(), names: st.names}));
    if (typeof afterChange === 'function') afterChange();
    toast(`Forged the ${st.stem.trim()} set: ${r.made.length} pieces, one Undo.`);
    // (then each piece into the world, one after another)
    const sb = fgSetBody();
    FG.world = {id: r.made[0].id, set: r.made.map(m => ({id: m.id, name: m.name})), forged: `the ${st.stem.trim()} set (${r.made.length} pieces)`,
                mat: sb.between ? null : sb.mat, between: sb.between || null, whole: true, setName: st.stem.trim()};
    st.stem = ''; st.names = {};
    fgTab('world');
  } catch (e){ fgMsg(esc(e.message), true); go.disabled = false; }
}

// where the game would find a piece like this (gearplaces.py): lists for anyone ticked, the rest for you to pick
async function fgWorld(){
  const box = FG.bg && FG.bg.querySelector('#fg-body'); if (!box) return;
  if (FG.world && FG.world.set && FG.world.whole) return fgWorldSet();
  box.innerHTML = '<div class="msg"><span class="spin"></span>Looking at where the game puts pieces like this…</div>';
  fgWorldReady();
  let d;
  // (what it was forged as, when known: its name doesn't always say, "Sunsteel" isn't steel)
  const q = new URLSearchParams({id: FG.world.id});
  if (FG.world.between) q.set('between', FG.world.between.join(',')); else if (FG.world.mat) q.set('mat', FG.world.mat);
  try { d = await api('/api/forge/places?' + q.toString()); }
  catch (e){ box.innerHTML = `<div class="msg err" style="padding:12px">${esc(e.message)}</div>`; return; }
  if (!FG.bg) return;
  if (d.need_material){
    box.innerHTML = `<div class="fgw"><div class="fgw-head"><div><b>${esc(d.item.name || d.item.id)}</b><div class="msg">${esc(d.item.type_label)}</div></div></div>
      <p class="msg">Nothing in its name or its model says what it is made of. Pick the material it is nearest to, and the Workshop shows where the game puts pieces of that.</p>
      <div class="fg-row" style="max-width:360px"><select class="inp" id="fgw-mat">${d.materials.map(m => `<option>${m}</option>`).join('')}</select><button class="btn sm primary" id="fgw-matgo">Show where</button></div></div>`;
    box.querySelector('#fgw-matgo').onclick = () => { FG.world.mat = box.querySelector('#fgw-mat').value; fgWorld(); };
    return;
  }
  FG.world.data = d;
  // (ticked to begin with: the three widest-used lists for anyone it isn't in yet; nobody's own gear is touched
  // until you say so)
  // (a new material between two: only the lists by level, where it gets its own level)
  let n = 0;
  FG.world.lists = d.general.map(x => !x.in && (!d.item.between || x.why.startsWith('a list of')) && n++ < 3);
  FG.world.some = d.some.map(() => false);
  FG.world.cls = d.classes.map(() => ({on: false, n: 3}));
  FG.world.sell = d.sellers.map(() => false);
  fgWorldDraw();
}
function fgWorldDraw(){
  const box = FG.bg && FG.bg.querySelector('#fg-body'), W_ = FG.world, d = W_ && W_.data; if (!box || !d) return;
  const it = d.item;
  const row = (x, n, grp) => `<label class="fgw-row ${x.in ? 'in' : ''}"><input type="checkbox" data-wl="${grp}:${n}" ${x.in || W_[grp][n] ? 'checked' : ''} ${x.in ? 'disabled' : ''}>
      <span class="fgw-nm">${esc(x.list)}</span><span class="msg fgw-why">${x.in ? 'it\'s in this one already' : esc(x.why)}</span>
      <span class="fgw-src">${esc(x.src)}</span><span class="fgw-lv">level <input class="inp num" data-wlv="${grp}:${n}" value="${x.level}" ${x.in ? 'disabled' : ''}></span></label>`;
  const forged = W_.forged ? `<div class="cnote fgw-made">Forged <b>${esc(W_.forged)}</b>. Choose where the game finds it, or Close to keep it to yourself (right-click it later: Into the world).</div>` : '';
  // (a set just forged: all of it at once, or its pieces one at a time, each its own Undo)
  const setRow = W_.set ? `${fgWorldModes()}<div class="fgw-set"><span class="fg-h" style="margin:0 6px 0 0">The set</span>${W_.set.map((p, n) => `<button class="fgw-piece ${p.id === W_.id ? 'on' : ''} ${p.placed ? 'done' : ''}" data-wp="${n}" title="${esc(p.id)}">${p.placed ? '✓ ' : ''}${esc(p.name)}</button>`).join('')}</div>` : '';
  box.innerHTML = `<div class="fgw">${forged}${setRow}
    <div class="fgw-head"><img class="thumb" data-tid="${esc(it.id)}" data-tt="${it.kind === 'weapon' ? 'WEAP' : 'ARMO'}" data-ts="64" alt="">
      <div><b>${esc(it.name || it.id)}</b><div class="msg">${esc(it.type_label)} · ${it.between ? `a new material between ${esc(it.between[0])} and ${esc(it.between[1])}` : esc(FG_CAP(it.material))}${it.enchanted ? ' · enchanted' : ''} · <span class="lnk" id="fgw-edit">open in the item editor</span></div></div></div>
    <div class="fg-h">Random loot lists, for anyone</div>
    <div class="msg fgw-note">Where the game puts its own ${it.between ? esc(it.between[0]) + ' and ' + esc(it.between[1]) : esc(it.material)} ${esc(fgPlural(it.type_label.split(' (')[0].split(',')[0].toLowerCase()))}, widest-used first, at the level ${it.between ? 'a material between the two' : 'its tier'} has in each.</div>
    <div class="fgw-list">${d.general.map((x, n) => row(x, n, 'lists')).join('') || '<div class="msg">None: the game has no list for this kind.</div>'}</div>
    ${d.some.length ? `<details class="fgw-more"><summary>Lists for a people, a faction or a place (${d.some.length})</summary><div class="fgw-list">${d.some.map((x, n) => row(x, n, 'some')).join('')}</div></details>` : ''}
    <div class="fg-h" style="margin-top:14px">Carried by</div>
    <div class="msg fgw-note">People carrying one like it get this instead, in as many as you choose.</div>
    <div class="fgw-list">${d.classes.map(([c, k], n) => `<label class="fgw-row"><input type="checkbox" data-wc="${n}" ${W_.cls[n].on ? 'checked' : ''}>
      <span class="fgw-nm">${esc(fgCls(c))}</span><span class="msg fgw-why">${k} carry one like it</span>
      <span class="fgw-lv">in <input class="inp num" data-wcn="${n}" value="${W_.cls[n].n}"> of them</span></label>`).join('') || '<div class="msg">Nobody in the game carries one like it.</div>'}</div>
    <div class="fg-h" style="margin-top:14px">Sold by</div>
    <div class="fgw-chips">${d.sellers.map((s, n) => `<label class="fgw-chip"><input type="checkbox" data-ws="${n}" ${W_.sell[n] ? 'checked' : ''}>${esc(s.name)} <span class="msg">${esc(fgCls(s.cls))}</span></label>`).join('') || '<span class="msg">No merchant in the game sells one like it.</span>'}</div>
    <div class="msg fgw-note" style="margin-top:12px">Each tick copies that list or person into your mod with the piece added. If another mod changes the same one, the one loaded last wins. One Undo takes it all back.</div></div>`;
  if (typeof v3ThumbScan === 'function') v3ThumbScan(box);
  const ed = box.querySelector('#fgw-edit'); if (ed) ed.onclick = () => { FG.bg.remove(); FG.bg = null; ieShow(it.id); };
  box.querySelectorAll('[data-wp]').forEach(b => b.onclick = () => { const p = W_.set[+b.dataset.wp]; W_.id = p.id; W_.forged = null; fgWorld(); });
  fgWorldModesBind(box);
  box.querySelectorAll('[data-wl]').forEach(c => c.onchange = () => { const [g, n] = c.dataset.wl.split(':'); W_[g][+n] = c.checked; fgWorldReady(); });
  box.querySelectorAll('[data-wlv]').forEach(c => c.oninput = () => { const [g, n] = c.dataset.wlv.split(':'); const v = parseInt(c.value, 10); if (v > 0) d[g === 'lists' ? 'general' : 'some'][+n].level = v; });
  box.querySelectorAll('[data-wc]').forEach(c => c.onchange = () => { W_.cls[+c.dataset.wc].on = c.checked; fgWorldReady(); });
  box.querySelectorAll('[data-wcn]').forEach(c => c.oninput = () => { const v = parseInt(c.value, 10); if (v >= 0) W_.cls[+c.dataset.wcn].n = v; fgWorldReady(); });
  box.querySelectorAll('[data-ws]').forEach(c => c.onchange = () => { W_.sell[+c.dataset.ws] = c.checked; fgWorldReady(); });
  fgWorldReady();
}
// ---------- a whole set into the world at once (gearplaces.set_places / place_set): each piece's own lists,
// people of a class dressed in all of it, merchants stocking all of it, one Undo
function fgWorldModes(){
  const W_ = FG.world;
  return `<div class="fgw-modes"><button data-wmode="whole" class="${W_.whole ? 'on' : ''}">The whole set (${W_.set.length})</button><button data-wmode="piece" class="${W_.whole ? '' : 'on'}">One piece at a time</button></div>`;
}
function fgWorldModesBind(box){
  box.querySelectorAll('[data-wmode]').forEach(b => b.onclick = () => { FG.world.whole = b.dataset.wmode === 'whole'; fgWorld(); });
}
async function fgWorldSet(){
  const box = FG.bg.querySelector('#fg-body'), W_ = FG.world;
  box.innerHTML = '<div class="msg"><span class="spin"></span>Looking at where the game puts pieces like these…</div>';
  fgWorldReady();
  let d;
  try { d = await post('/api/forge/setplaces', {ids: W_.set.map(p => p.id), mat: W_.between ? null : W_.mat, between: W_.between}); }
  catch (e){ box.innerHTML = `<div class="msg err" style="padding:12px">${esc(e.message)}</div>`; return; }
  if (!FG.bg) return;
  W_.sd = d;
  // (each piece's own first lists ticked, as for one piece: only the lists by level for a material between two)
  W_.slists = d.pieces.map(p => { let n = 0; return p.general.map(x => !x.in && (!p.item.between || x.why.startsWith('a list of')) && n++ < 3); });
  W_.scls = d.classes.map(() => ({on: false, n: 3}));
  W_.ssell = d.sellers.map(() => false);
  fgWorldSetDraw();
}
function fgWorldSetDraw(){
  const box = FG.bg && FG.bg.querySelector('#fg-body'), W_ = FG.world, d = W_ && W_.sd; if (!box || !d) return;
  const row = (x, pi, n) => `<label class="fgw-row ${x.in ? 'in' : ''}"><input type="checkbox" data-sl="${pi}:${n}" ${x.in || W_.slists[pi][n] ? 'checked' : ''} ${x.in ? 'disabled' : ''}>
      <span class="fgw-nm">${esc(x.list)}</span><span class="msg fgw-why">${x.in ? 'it\'s in this one already' : esc(x.why)}</span>
      <span class="fgw-src">${esc(x.src)}</span><span class="fgw-lv">level <input class="inp num" data-slv="${pi}:${n}" value="${x.level}" ${x.in ? 'disabled' : ''}></span></label>`;
  const forged = W_.forged ? `<div class="cnote fgw-made">Forged <b>${esc(W_.forged)}</b>. Choose where the game finds it, or Close to keep it to yourself (right-click a piece later: Into the world).</div>` : '';
  box.innerHTML = `<div class="fgw">${forged}${fgWorldModes()}
    <div class="fg-h">Random loot lists, for anyone</div>
    <div class="msg fgw-note">Each piece where the game puts its own of that kind, widest-used first.</div>
    ${d.pieces.map((p, pi) => `<div class="fgws-piece"><div class="fgws-pn"><img class="thumb" data-tid="${esc(p.item.id)}" data-tt="${p.item.kind === 'weapon' ? 'WEAP' : 'ARMO'}" data-ts="32" alt=""><b>${esc(p.item.name || p.item.id)}</b><span class="msg">${esc(p.item.type_label)}</span></div>
      <div class="fgw-list">${p.general.slice(0, 3).map((x, n) => row(x, pi, n)).join('') || '<div class="msg">No list for this kind.</div>'}</div>
      ${p.general.length > 3 ? `<details class="fgw-more"><summary>${p.general.length - 3} more</summary><div class="fgw-list">${p.general.slice(3).map((x, n) => row(x, pi, n + 3)).join('')}</div></details>` : ''}</div>`).join('')}
    <div class="fg-h" style="margin-top:14px">Worn by</div>
    <div class="msg fgw-note">People of a class carrying pieces like these wear the whole set instead, those carrying the most first.</div>
    <div class="fgw-list">${d.classes.map((c, n) => `<label class="fgw-row"><input type="checkbox" data-sc2="${n}" ${W_.scls[n].on ? 'checked' : ''}>
      <span class="fgw-nm">${esc(fgCls(c.cls))}</span><span class="msg fgw-why">${c.people} carry pieces like it (up to ${c.slots} of the set's)</span>
      <span class="fgw-lv">in <input class="inp num" data-sc2n="${n}" value="${W_.scls[n].n}"> of them</span></label>`).join('') || '<div class="msg">Nobody in the game carries pieces like these.</div>'}</div>
    <div class="fg-h" style="margin-top:14px">Sold by</div>
    <div class="fgw-chips">${d.sellers.map((s, n) => `<label class="fgw-chip"><input type="checkbox" data-ss="${n}" ${W_.ssell[n] ? 'checked' : ''}>${esc(s.name)} <span class="msg">${esc(fgCls(s.cls))}</span></label>`).join('') || '<span class="msg">No merchant in the game sells pieces like these.</span>'}</div>
    <div class="msg fgw-note" style="margin-top:12px">A ticked merchant stocks every piece. If another mod changes the same list or person, the one loaded last wins. One Undo takes it all back.</div></div>`;
  if (typeof v3ThumbScan === 'function') v3ThumbScan(box);
  fgWorldModesBind(box);
  box.querySelectorAll('[data-sl]').forEach(c => c.onchange = () => { const [p, n] = c.dataset.sl.split(':'); W_.slists[+p][+n] = c.checked; fgWorldReady(); });
  box.querySelectorAll('[data-slv]').forEach(c => c.oninput = () => { const [p, n] = c.dataset.slv.split(':'); const v = parseInt(c.value, 10); if (v > 0) d.pieces[+p].general[+n].level = v; });
  box.querySelectorAll('[data-sc2]').forEach(c => c.onchange = () => { W_.scls[+c.dataset.sc2].on = c.checked; fgWorldReady(); });
  box.querySelectorAll('[data-sc2n]').forEach(c => c.oninput = () => { const v = parseInt(c.value, 10); if (v >= 0) W_.scls[+c.dataset.sc2n].n = v; fgWorldReady(); });
  box.querySelectorAll('[data-ss]').forEach(c => c.onchange = () => { W_.ssell[+c.dataset.ss] = c.checked; fgWorldReady(); });
  fgWorldReady();
}
function fgWorldSetPicks(){
  const W_ = FG.world, d = W_ && W_.sd; if (!d) return null;
  const lists = {};
  let nl = 0;
  d.pieces.forEach((p, pi) => { lists[p.item.id] = p.general.filter((x, n) => W_.slists[pi][n] && !x.in).map(x => ({list: x.list, level: x.level})); nl += lists[p.item.id].length; });
  const classes = d.classes.filter((c, n) => W_.scls[n].on && W_.scls[n].n > 0).map((c, n) => ({cls: c.cls, n: W_.scls[d.classes.indexOf(c)].n}));
  const sells = d.sellers.filter((s, n) => W_.ssell[n]).map(s => s.npc);
  return {lists, classes, sells, nl, np: classes.reduce((a, c) => a + c.n, 0)};
}

// (more than one: "cuirasses", "helmets", "boots" as they are)
function fgPlural(w){ return /(greaves|boots|arrow|bolt)s?$/.test(w) ? w.replace(/(arrow|bolt)$/, '$1s') : /(s|sh|ch|x)$/.test(w) ? w + 'es' : w + 's'; }
// (a class's own name: the T_Glb_ and such prefixes of Tamriel Data's left off)
function fgCls(c){ return String(c || '').replace(/^T_[A-Za-z]+_/, '').replace(/([a-z])([A-Z])/g, '$1 $2'); }
// what is chosen: the lists, the people whose like piece is swapped (spread over each class's), the merchants
function fgWorldPicks(){
  const W_ = FG.world, d = W_ && W_.data; if (!d) return null;
  const lists = d.general.filter((x, n) => W_.lists[n] && !x.in).concat(d.some.filter((x, n) => W_.some[n] && !x.in)).map(x => ({list: x.list, level: x.level}));
  const swaps = [];
  d.classes.forEach(([c], n) => {
    const pick = W_.cls[n]; if (!pick.on || !pick.n) return;
    const of = d.carriers.filter(p => p.cls === c), k = Math.min(pick.n, of.length);
    for (let i = 0; i < k; i++){ const p = of[Math.floor(i * of.length / k)]; swaps.push({npc: p.npc, theirs: p.theirs}); }
  });
  const sells = d.sellers.filter((s, n) => W_.sell[n]).map(s => s.npc);
  return {lists, swaps, sells};
}
function fgWorldReady(){
  const go = FG.bg && FG.bg.querySelector('#fg-go'); if (!go) return;
  if (FG.world && FG.world.whole){
    const q = fgWorldSetPicks(), n = q ? q.nl + q.np + q.sells.length : 0;
    go.disabled = !n; go.innerHTML = '🌐 Put the whole set into the world';
    if (q) fgMsg(n ? `${q.nl} list entr${q.nl === 1 ? 'y' : 'ies'}, up to ${q.np} ${q.np === 1 ? 'person' : 'people'} wearing it, ${q.sells.length} merchant${q.sells.length === 1 ? '' : 's'}` : 'Tick where the game should find it.');
    return;
  }
  go.innerHTML = '🌐 Put it into the world';
  const p = fgWorldPicks();
  const n = p ? p.lists.length + p.swaps.length + p.sells.length : 0;
  go.disabled = !n;
  if (p) fgMsg(n ? `${p.lists.length} list${p.lists.length === 1 ? '' : 's'}, ${p.swaps.length} ${p.swaps.length === 1 ? 'person' : 'people'}, ${p.sells.length} merchant${p.sells.length === 1 ? '' : 's'}` : 'Tick where the game should find it.');
}
async function fgPlace(){
  if (!await needProject()) return;
  if (FG.world && FG.world.whole) return fgPlaceSet();
  const p = fgWorldPicks(); if (!p) return;
  const go = FG.bg.querySelector('#fg-go'); go.disabled = true;
  fgMsg('<span class="spin"></span>Putting it into the world…');
  try {
    const r = await post('/api/forge/place', Object.assign({id: FG.world.id}, p));
    if (typeof afterChange === 'function') afterChange();
    toast(`${FG.world.data.item.name || FG.world.id} is in the world: ${fgMsgText(p)}. One Undo takes it back.`);
    FG.world.forged = null;
    // (in a set: this piece ticked off, and on to the next one not yet placed)
    if (FG.world.set){
      const cur = FG.world.set.find(x => x.id === FG.world.id); if (cur) cur.placed = true;
      const next = FG.world.set.find(x => !x.placed); if (next) FG.world.id = next.id;
    }
    await fgWorld();
    fgMsg(`Done: ${r.changed} change${r.changed === 1 ? '' : 's'}, in one Undo.`);
  } catch (e){ fgMsg(esc(e.message), true); go.disabled = false; }
}
async function fgPlaceSet(){
  const W_ = FG.world, q = fgWorldSetPicks(); if (!q) return;
  const go = FG.bg.querySelector('#fg-go'); go.disabled = true;
  fgMsg('<span class="spin"></span>Putting the set into the world…');
  try {
    const r = await post('/api/forge/placeset', {ids: W_.set.map(p => p.id), lists: q.lists, classes: q.classes, sells: q.sells,
      mat: W_.between ? null : W_.mat, between: W_.between, name: W_.setName || ''});
    if (typeof afterChange === 'function') afterChange();
    toast(`The set is in the world: ${r.lists} list entries, ${r.people} ${r.people === 1 ? 'person' : 'people'} wearing it, ${r.merchants} merchant${r.merchants === 1 ? '' : 's'}. One Undo takes it back.`);
    W_.forged = null; W_.set.forEach(p => p.placed = true);
    await fgWorldSet();
    fgMsg(`Done: ${r.changed} change${r.changed === 1 ? '' : 's'}, in one Undo.`);
  } catch (e){ fgMsg(esc(e.message), true); go.disabled = false; }
}
function fgMsgText(p){
  return [p.lists.length && `${p.lists.length} list${p.lists.length === 1 ? '' : 's'}`, p.swaps.length && `${p.swaps.length} ${p.swaps.length === 1 ? 'person' : 'people'}`,
          p.sells.length && `${p.sells.length} merchant${p.sells.length === 1 ? '' : 's'}`].filter(Boolean).join(', ');
}

function fgCss(){
  if ($('#fg-css')) return;
  const c = document.createElement('style'); c.id = 'fg-css';
  c.textContent = `
  .fg-win{width:min(1000px,96vw);max-height:92vh;overflow:auto}
  .fg-grid{display:grid;grid-template-columns:minmax(260px,330px) minmax(0,1fr);gap:16px}
  .fg-h{font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--faint);margin:2px 0 4px}
  .fg-row{display:flex;gap:6px;align-items:center;margin:4px 0}.fg-row select{flex:1;min-width:0}
  .fg-radio{display:flex;gap:6px;align-items:center}
  .fg-looks{display:grid;grid-template-columns:repeat(3,1fr);gap:4px;max-height:270px;overflow:auto}
  .fg-look{display:flex;flex-direction:column;align-items:center;gap:2px;padding:4px;border:1px solid var(--line2);border-radius:6px;background:var(--panel2);cursor:pointer;color:var(--text);font:inherit;font-size:11px}
  .fg-look.on{border-color:var(--gold);background:var(--hl)}.fg-look img{width:72px;height:72px}.fg-look span{max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .fg-t{width:100%;font-size:13px}.fg-t td,.fg-t th{padding:3px 6px;text-align:left}.fg-t input{width:90px}
  .fg-b{font-size:11.5px;white-space:nowrap}.fg-b.ok{color:var(--good,#8fbf7f)}.fg-b.high,.fg-b.low{color:var(--amber,#e0a050)}
  @media (max-width: 820px){ .fg-grid{grid-template-columns:minmax(0,1fr)} .modal .fgw-row{grid-template-columns:20px minmax(0,1fr) auto} .fgw-why,.fgw-src{display:none} }
  .fg-tsep{align-self:center;color:var(--faint);font-size:11px;padding:0 4px}
  .fs-pieces{display:flex;flex-direction:column;gap:4px;max-height:52vh;overflow:auto}
  .fs-piece{display:flex;gap:10px;align-items:center;padding:4px 6px;border:1px solid var(--line);border-radius:8px;background:var(--panel2)}
  .fs-piece img{width:48px;height:48px;flex:none}.fs-pn{display:flex;flex-direction:column;gap:2px;min-width:0;flex:1}
  .fs-pn .inp{font-weight:600}.fs-pn .msg{font-size:11.5px}
  .fgw-modes{display:inline-flex;border:1px solid var(--line2);border-radius:8px;overflow:hidden;margin-bottom:12px}
  .fgw-modes button{background:none;border:0;padding:5px 12px;font:inherit;font-size:12.5px;color:var(--muted);cursor:pointer}
  .fgw-modes button.on{background:var(--sel);color:var(--gold2)}
  .fgws-piece{border-top:1px solid var(--line);padding:6px 0 4px}
  .fgws-pn{display:flex;align-items:center;gap:8px;margin-bottom:2px;font-size:13px}.fgws-pn img{width:32px;height:32px}
  .fgw-set{display:flex;flex-wrap:wrap;gap:5px;align-items:center;margin-bottom:12px}
  .fgw-piece{background:var(--panel2);border:1px solid var(--line2);border-radius:14px;padding:3px 10px;font:inherit;font-size:12px;color:var(--text);cursor:pointer}
  .fgw-piece.on{border-color:var(--gold);color:var(--gold2)}.fgw-piece.done{opacity:.6}
  .fg-win > .foot{position:sticky;bottom:-18px;background:var(--panel);padding-bottom:4px;z-index:2}
  .fg-tabs{display:flex;gap:4px;margin:-4px 0 12px;border-bottom:1px solid var(--line)}
  .fg-tabs button{background:none;border:0;border-bottom:2px solid transparent;color:var(--muted);padding:6px 12px;font:inherit;font-size:13px;cursor:pointer}
  .fg-tabs button.on{color:var(--gold2);border-bottom-color:var(--gold)}.fg-tabs button:disabled{opacity:.45;cursor:default}
  .fgw-head{display:flex;gap:12px;align-items:center;margin-bottom:12px}.fgw-head img{width:64px;height:64px;border:1px solid var(--line);border-radius:8px;background:var(--panel2)}
  .fgw-made{margin-bottom:12px}
  .fgw-note{font-size:12px;margin:0 0 6px}
  .fgw-list{display:flex;flex-direction:column;gap:2px}
  .modal .fgw-row{display:grid;grid-template-columns:20px minmax(160px,1.2fr) minmax(0,1.4fr) auto auto;gap:8px;align-items:center;padding:4px 6px;margin:0;border-radius:6px;font-size:13px;color:var(--text);cursor:pointer}
  .fgw-row:hover{background:var(--hover)}.fgw-row.in{opacity:.6;cursor:default}
  .fgw-row:has(> input[type=checkbox]:not(:checked)) .fgw-lv{opacity:.45}
  .fgw-nm{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.fgw-why{font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .fgw-src{font-size:11px;color:var(--faint);white-space:nowrap}.fgw-lv{font-size:12px;color:var(--muted);white-space:nowrap}.fgw-lv input{width:52px;margin-left:4px}
  .fgw-more{margin-top:8px}.fgw-more>summary{cursor:pointer;color:var(--muted);font-size:12.5px;padding:4px 0}
  .fgw-chips{display:flex;flex-wrap:wrap;gap:6px}
  .modal .fgw-chip{margin:0;color:var(--text)}
  .fgw-chip{display:inline-flex;gap:6px;align-items:center;padding:4px 9px;border:1px solid var(--line2);border-radius:14px;font-size:12.5px;cursor:pointer;background:var(--panel2)}
  .fgw-chip:has(input:checked){border-color:var(--gold)}`;
  document.head.appendChild(c);
}
