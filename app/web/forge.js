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
      <label class="msg fg-radio"><input type="radio" name="fg-m" value="game" ${FG.between ? '' : 'checked'}> An existing material</label>
      <select class="inp" id="fg-mat" ${FG.between ? 'disabled' : ''}>${fgMats().map(m => `<option value="${m.id}" ${m.id === FG.mat ? 'selected' : ''}>${esc(FG_CAP(m.id))} (${m.n} like it)</option>`).join('')}</select>
      <label class="msg fg-radio" style="margin-top:6px"><input type="radio" name="fg-m" value="between" ${FG.between ? 'checked' : ''}> A new material between two</label>
      <div class="fg-row" ${FG.between ? '' : 'style="opacity:.5;pointer-events:none"'}>
        <select class="inp" id="fg-a">${all.map(m => `<option ${FG.between && FG.between[0] === m ? 'selected' : ''}>${m}</option>`).join('')}</select>
        <select class="inp" id="fg-b">${all.map(m => `<option ${FG.between && FG.between[1] === m ? 'selected' : ''}>${m}</option>`).join('')}</select></div>
      <label class="msg fg-row" ${FG.between ? '' : 'style="opacity:.5;pointer-events:none"'}>nearer the first <input type="range" id="fg-f" min="0" max="1" step="0.05" value="${FG.between ? FG.between[2] : 0.5}" style="flex:1"> nearer the second</label>
      <div class="fg-h" style="margin-top:10px">Name</div>
      <input class="inp" id="fg-name" placeholder="e.g. Glass Saber of the Wolf" value="${esc(FG.name || '')}">
      <div class="msg" style="margin-top:4px">ID <input class="inp" id="fg-id" style="width:62%" value="${esc(FG.id || '')}" placeholder="made from the name"></div>
      <div class="fg-h" style="margin-top:10px">Its look <span class="msg">(${FG.between ? 'pieces of either material' : 'pieces of this kind and material'})</span></div>
      <div class="fg-looks" id="fg-looks"></div>
      <button class="btn sm" id="fg-more" style="margin-top:4px" title="Any piece of this kind in your load order">🔍 More looks…</button>
      <div class="fg-h" style="margin-top:10px">Your own look</div>
      <div id="fg-own"></div>
    </div>
    <div class="fg-main">
      <div class="fg-h">Its numbers <span class="msg" id="fg-basis"></span></div>
      <table class="t fg-t" id="fg-stats"></table>
      <div id="fg-class" class="msg" style="margin-top:6px"></div>
      <div id="fg-notes" style="margin-top:6px"></div>
      <div class="msg" style="margin-top:8px;font-size:11.5px">Starts at the typical value; ▲ marks one far past the range. Enchant it in the item editor.</div>
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
  box.querySelector('#fg-more').onclick = () => fgLookPicker(FG.kind, FG.type, (fgTypes().find(t => t.id === FG.type) || {}).label, l => {
    FG.picked = Object.assign({kind: FG.kind, type: FG.type}, l); FG.look = l.i; FG.style = {own: '', worn: {}, skin: {}}; fgLooksDraw(); fgOwnDraw(); fgReady();
  });
  fgOwnDraw();
}

// ---------- the look: any piece of its kind in the load order, your own model, its pictures (forgelooks.py) ----------
async function fgLib(){
  if (!FG.lib){ try { FG.lib = (await api('/api/library')).items || []; } catch (e){ FG.lib = []; } }
  return FG.lib;
}
const fgLibModels = () => (FG.lib || []).filter(e => e.type === 'model' && e.model);
const fgLibPics = () => (FG.lib || []).filter(e => e.type === 'texture' && e.texture);
// (your Library's models, the ones sorted for this kind of piece first: "Armour › Helmet" for a helmet, then the
// rest of Armour, then everything else; library.js LIB_CATS)
function fgModelSel(attr, val, first, kind, label){
  const cat = kind === 'weapon' ? 'Weapons' : kind === 'armor' ? 'Armour' : '';
  const lab = String(label || '').toLowerCase();
  const fits = e => e.sub && lab && lab.includes(e.sub.toLowerCase().replace(/s$/, ''));
  const ms = fgLibModels(), opt = e => `<option value="${esc(e.id)}" ${e.id === val ? 'selected' : ''}>${esc(e.name || e.id)}${e.sub ? ' · ' + esc(e.sub) : ''}</option>`;
  const a = ms.filter(e => e.cat === cat && fits(e)), b = ms.filter(e => e.cat === cat && !fits(e)), c = ms.filter(e => e.cat !== cat);
  const grp = (l, xs) => xs.length ? `<optgroup label="${esc(l)}">${xs.map(opt).join('')}</optgroup>` : '';
  return `<select class="inp" ${attr}><option value="">${esc(first)}</option>${grp(`${cat} › ${label || ''}`, a)}${grp(cat ? `Other ${cat.toLowerCase()}` : 'Your models', b)}${grp(cat ? 'Everything else' : '', c)}</select>`;
}
// (a window over the Forge: every piece of this kind and type, from every plugin, with a search)
function fgLookPicker(kind, type, label, onPick){
  const bg = document.createElement('div'); bg.className = 'modal-bg'; bg.style.zIndex = 1300;
  const tt = kind === 'weapon' ? 'WEAP' : 'ARMO';
  bg.innerHTML = `<div class="modal" style="width:min(880px,96vw)"><h2 title="Takes its model and icon${kind === 'armor' ? ' and how it is worn' : ''}; not its numbers or magic">🔍 Looks like: any ${esc((label || type).toLowerCase())}</h2>
    <input class="inp" id="flp-q" placeholder="Name, ID, model or mod" style="margin:8px 0" autocomplete="off">
    <div class="msg" id="flp-n"></div><div class="fg-looks flp-grid" id="flp-grid"></div>
    <div class="actions"><button class="btn" id="flp-no">Cancel</button></div></div>`;
  document.body.appendChild(bg);
  const grid = bg.querySelector('#flp-grid'), qi = bg.querySelector('#flp-q');
  let seq = 0, t;
  const load = async () => {
    const my = ++seq;
    try {
      const r = await api('/api/forge/looks?' + new URLSearchParams({kind, type, q: qi.value.trim(), limit: 120}));
      if (my !== seq) return;
      bg.querySelector('#flp-n').textContent = r.n > r.looks.length ? `${r.looks.length} of ${r.n}` : `${r.n}`;
      grid.innerHTML = r.looks.map((l, n) => `<button class="fg-look" data-n="${n}" title="${esc(l.name)} (${esc(l.id)}) · ${esc(l.src)}${l.enchanted ? ' · enchanted' : ''}">
        <img class="thumb" data-tid="${esc(l.id)}" data-tt="${tt}" data-ts="72" alt=""><span>${esc(l.name || l.id)}</span><small class="faint">${esc(l.src.replace(/\.(esm|esp|omwaddon)$/i, ''))}</small></button>`).join('') || '<span class="msg">Nothing like that.</span>';
      grid.querySelectorAll('[data-n]').forEach(b => b.onclick = () => { bg.remove(); onPick(r.looks[+b.dataset.n]); });
      if (typeof v3ThumbScan === 'function') v3ThumbScan(grid);
    } catch (e){ bg.querySelector('#flp-n').textContent = e.message; }
  };
  qi.oninput = () => { clearTimeout(t); t = setTimeout(load, 250); };
  bg.querySelector('#flp-no').onclick = () => bg.remove();
  qi.focus(); load();
}
// (your own model for it, your own worn parts, its pictures swapped: FG.style, sent with Forge it)
async function fgOwnDraw(){
  const box = FG.bg && FG.bg.querySelector('#fg-own'); if (!box) return;
  FG.style = FG.style || {own: '', worn: {}, skin: {}};
  await fgLib();
  const S_ = FG.style, ns = Object.keys(S_.skin).length, models = fgLibModels().length;
  let parts = [];
  if (FG.kind === 'armor' && FG.look != null){ try { parts = (await api('/api/forge/worn?i=' + FG.look)).parts; } catch (e){} }
  if (!FG.bg) return;
  const tl = (fgTypes().find(t => t.id === FG.type) || {}).label || '';
  box.innerHTML = `<div class="msg fg-ownl">${models ? 'Model ' + fgModelSel('id="fg-ownm"', S_.own, "The look's", FG.kind, tl)
    : '<span title="Drop a .nif, .obj, .glb or .fbx on the Library page">Your own models come from the Library.</span>'}</div>
    ${parts.length && models ? `<details class="fgw-more" ${Object.keys(S_.worn).length ? 'open' : ''}><summary title="Each worn mesh must be made for its place on the body; the Workshop doesn't fit it on">Worn parts (${parts.length})${Object.keys(S_.worn).length ? `, ${Object.keys(S_.worn).length} your own` : ''}</summary>
      ${parts.map(p => `<div class="msg fg-ownl">${esc(p.label)} ${fgModelSel(`data-fgw="${p.part}"`, S_.worn[p.part] || '', "The look's", FG.kind, tl)}</div>`).join('')}</details>` : ''}
    <button class="btn sm" id="fg-skin" style="margin-top:4px" ${FG.look == null ? 'disabled' : ''}>🎨 Its pictures${ns ? ` (${ns} swapped)` : '…'}</button>`;
  const om = box.querySelector('#fg-ownm'); if (om) om.onchange = () => { S_.own = om.value; };
  box.querySelectorAll('[data-fgw]').forEach(s => s.onchange = () => { if (s.value) S_.worn[s.dataset.fgw] = s.value; else delete S_.worn[s.dataset.fgw]; });
  box.querySelector('#fg-skin').onclick = () => fgSkinPicker([FG.look], S_.skin, m => { S_.skin = m; fgOwnDraw(); });
}
// (the pictures the pieces use, each swapped for one of the Library's: a skin, over one piece or a whole set)
async function fgSkinPicker(recs, mapping, onDone){
  await fgLib();
  let t;
  try { t = (await post('/api/forge/textures', {recs})).textures; } catch (e){ return toast(e.message, true); }
  if (!t.length) return toast('Its models have no pictures to swap.', true);
  const pics = fgLibPics(), many = recs.length > 1;
  const bg = document.createElement('div'); bg.className = 'modal-bg'; bg.style.zIndex = 1300;
  bg.innerHTML = `<div class="modal" style="width:min(680px,96vw)"><h2 title="New copies of the models are made; the originals stay as they are">🎨 ${many ? 'The set\'s pictures' : 'Its pictures'}</h2>
    ${many ? '<div class="msg">A swap changes every piece that uses it.</div>' : ''}
    <div class="fg-skin">${t.map((x, n) => `<div class="fg-skinr">${x.path ? `<img src="/api/file?path=${encodeURIComponent(x.path)}" onerror="this.style.visibility='hidden'">` : '<span></span>'}
      <div><div class="msg">${esc(x.name)}${many ? ` <span class="faint">· ${x.n} of ${recs.length}</span>` : ''}</div>
      <select class="inp" data-sk="${n}"><option value="">Keep</option>${pics.map(l => `<option value="${esc(l.texture)}" ${mapping[x.name] === l.texture ? 'selected' : ''}>${esc(l.name)}</option>`).join('')}</select></div></div>`).join('')}</div>
    ${pics.length ? '' : '<div class="msg warn">No pictures in your Library yet.</div>'}
    <div class="actions"><button class="btn primary" id="fsk-ok">Use these</button><button class="btn" id="fsk-no">Cancel</button></div></div>`;
  document.body.appendChild(bg);
  bg.querySelector('#fsk-no').onclick = () => bg.remove();
  bg.querySelector('#fsk-ok').onclick = () => {
    const m = {};
    bg.querySelectorAll('[data-sk]').forEach(s => { if (s.value) m[t[+s.dataset.sk].name] = s.value; });
    bg.remove(); onDone(m);
  };
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
    // (a look picked from the whole load order stays while it is still that kind of piece)
    if (FG.picked && (FG.picked.kind !== FG.kind || FG.picked.type !== FG.type)) FG.picked = null;
    if (FG.picked) FG.look = FG.picked.i;
    else if (!FG.look || !p.looks.some(l => l.i === FG.look)) FG.look = p.looks.length ? p.looks[0].i : null;
    fgStatsDraw(); fgLooksDraw(); fgCheck(); fgReady(); fgOwnDraw();
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
  const ls = (FG.picked ? [FG.picked] : []).concat(FG.p.looks.filter(l => !FG.picked || l.i !== FG.picked.i)).slice(0, 18);
  box.innerHTML = ls.map(l => `<button class="fg-look ${l.i === FG.look ? 'on' : ''}" data-fgl="${l.i}" title="${esc(l.name)} (${esc(l.id)})">
    <img class="thumb" data-tid="${esc(l.id)}" data-tt="${tt}" data-ts="72" alt=""><span>${esc(l.name || l.id)}</span></button>`).join('') || '<span class="msg">None plain: search below.</span>';
  box.querySelectorAll('[data-fgl]').forEach(b => b.onclick = () => {
    FG.look = +b.dataset.fgl; if (FG.picked && FG.picked.i !== FG.look) FG.picked = null;
    if (FG.style) FG.style.worn = {};
    box.querySelectorAll('.fg-look').forEach(x => x.classList.toggle('on', x === b)); fgReady(); fgOwnDraw();
  });
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
    const S_ = FG.style || {};
    const r = await post('/api/forge/make', {template: FG.look, id: FG.id.trim(), name: FG.name.trim(), stats,
      mat: FG.between ? null : FG.mat, between: FG.between,
      style: {own: S_.own || '', worn: S_.worn || {}, skin: S_.skin || {}}});
    FG.style = {own: '', worn: {}, skin: {}};
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
      <select class="inp" id="fs-look">${st.opts.looks.map(l => `<option value="${l.material}" ${l.material === st.look ? 'selected' : ''}>${esc(FG_CAP(l.material))} (${l.armor.length} armour pieces${l.weapons.length ? ', ' + l.weapons.length + ' weapons' : ''})</option>`).join('')}</select>
      <div class="fg-h" style="margin-top:10px">Its numbers</div>
      <label class="msg fg-radio"><input type="radio" name="fs-n" value="same" ${st.numbers === 'same' ? 'checked' : ''}> As ${esc(st.look)}</label>
      <label class="msg fg-radio"><input type="radio" name="fs-n" value="game" ${st.numbers === 'game' ? 'checked' : ''}> As another material</label>
      <select class="inp" id="fs-mat" ${st.numbers === 'game' ? '' : 'disabled'}>${all.map(m => `<option ${m === st.mat ? 'selected' : ''}>${m}</option>`).join('')}</select>
      <label class="msg fg-radio" style="margin-top:6px"><input type="radio" name="fs-n" value="between" ${st.numbers === 'between' ? 'checked' : ''}> A new material between two</label>
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
      <div class="fg-row" style="margin-top:6px"><button class="btn sm" id="fs-skin" title="Swap a picture once and every piece that uses it changes">🎨 The set's pictures${Object.keys(st.skin || {}).length ? ` (${Object.keys(st.skin).length} swapped)` : '…'}</button></div>
      <div class="msg" style="margin-top:8px;font-size:11.5px">Numbers are typical for each kind; change them later in the item editor. One Undo.</div>
    </div></div>`;
  const redo = () => { fgSetDraw(); fgSetPreview(); };
  box.querySelector('#fs-look').onchange = e => { st.look = e.target.value; const L2 = fgSetLook(); st.armor = fgSetSlots(L2); st.weapons = new Set([...st.weapons].filter(t => L2.weapons.includes(t))); st.names = {}; st.looks = {}; st.own = {}; st.skin = {}; redo(); };
  box.querySelectorAll('[name=fs-n]').forEach(r => r.onchange = () => { if (r.checked){ st.numbers = r.value; redo(); } });
  box.querySelector('#fs-mat').onchange = e => { st.mat = e.target.value; fgSetPreview(); };
  const bw = () => { st.between = [box.querySelector('#fs-a').value, box.querySelector('#fs-b').value, +box.querySelector('#fs-f').value]; fgSetPreview(); };
  box.querySelector('#fs-a').onchange = bw; box.querySelector('#fs-b').onchange = bw; box.querySelector('#fs-f').onchange = bw;
  let t_; box.querySelector('#fs-stem').oninput = e => { st.stem = e.target.value; st.names = {}; clearTimeout(t_); t_ = setTimeout(fgSetPreview, 300); fgSetReady(); };
  box.querySelectorAll('[data-sc]').forEach(c => c.onchange = () => { st[c.dataset.sc][c.checked ? 'add' : 'delete'](c.value); fgSetPreview(); });
  box.querySelector('#fs-skin').onclick = () => { if (!st.pieces.length) return;
    fgSkinPicker(st.pieces.map(p => p.look.i), st.skin || {}, m => { st.skin = m; fgSetDraw(); fgSetPreview(); }); };
}
function fgSetBody(){
  const st = FG.set, b = {look: st.look, stem: st.stem.trim() || 'New', armor: [...st.armor], weapons: [...st.weapons], looks: st.looks || {}};
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
    await fgLib();
    st.own = st.own || {};
    const models = fgLibModels().length;
    box.innerHTML = r.pieces.map(p => `<div class="fs-piece"><img class="thumb" data-tid="${esc(p.look.id)}" data-tt="${p.kind === 'armor' ? 'ARMO' : 'WEAP'}" data-ts="48" alt="">
        <div class="fs-pn"><input class="inp" data-sn="${esc(p.type)}" value="${esc(st.names[p.type] || p.name)}"><span class="msg">${esc(p.label)} · ${main(p)} · weight ${p.stats.Weight}${p.weight_class ? ' (' + p.weight_class + ')' : ''} · value ${fmtN(p.stats.Value)}</span>
        <span class="msg fs-lk">${esc(p.look.name)} <span class="lnk" data-slk="${esc(p.type)}" data-sk="${p.kind}" data-sl="${esc(p.label)}" title="Take the look from any piece of this kind">change</span>
          ${models ? fgModelSel(`data-som="${esc(p.type)}"`, st.own[p.type] || '', "the look's model", p.kind, p.label) : ''}</span></div></div>`).join('')
      || '<div class="msg">Pick at least one piece on the left.</div>';
    const c = FG.bg.querySelector('#fs-count'); if (c) c.textContent = r.pieces.length ? `(${r.pieces.length} piece${r.pieces.length === 1 ? '' : 's'})` : '';
    box.querySelectorAll('[data-sn]').forEach(inp => inp.oninput = () => { st.names[inp.dataset.sn] = inp.value; });
    box.querySelectorAll('[data-slk]').forEach(b => b.onclick = () => fgLookPicker(b.dataset.sk, b.dataset.slk, b.dataset.sl, l => {
      st.looks = st.looks || {}; st.looks[b.dataset.slk] = l.i; st.skin = {}; fgSetPreview(); }));
    box.querySelectorAll('[data-som]').forEach(s => s.onchange = () => { if (s.value) st.own[s.dataset.som] = s.value; else delete st.own[s.dataset.som]; });
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
    const r = await post('/api/forge/set', Object.assign(fgSetBody(), {stem: st.stem.trim(), names: st.names,
      style: {own: st.own || {}, skin: st.skin || {}}}));
    st.own = {}; st.skin = {}; st.looks = {};
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
      <p class="msg">Its material isn't clear. Which is it nearest?</p>
      <div class="fg-row" style="max-width:360px"><select class="inp" id="fgw-mat">${d.materials.map(m => `<option>${m}</option>`).join('')}</select><button class="btn sm primary" id="fgw-matgo">Show where</button></div></div>`;
    box.querySelector('#fgw-matgo').onclick = () => { FG.world.mat = box.querySelector('#fgw-mat').value; fgWorld(); };
    return;
  }
  FG.world.data = d;
  // (ticked to begin with: the three widest-used lists for anyone it isn't in yet; nobody's own gear is touched
  // until you say so)
  // (a new material between two: only the lists by level, where it gets its own level)
  let n = 0;
  // (a stretched list, the nearest when the game has none, is offered but left for you to tick)
  FG.world.lists = d.general.map(x => !x.in && !x.stretch && (!d.item.between || x.kind === 'type') && n++ < 3);
  FG.world.some = d.some.map(() => false);
  FG.world.who = new Set();
  FG.world.sell = d.sellers.map(() => false);
  fgExtrasInit(FG.world, d.item);
  fgWorldDraw();
}

// ---------- people by name: each class's people, where they are, what they carry now ----------
function fgWhoHtml(classes, who, attr){
  return classes.map((c, n) => {
    const all = c.who.length && c.who.every(p => who.has(p.npc)), some = c.who.some(p => who.has(p.npc));
    return `<details class="fgw-cls" ${some ? 'open' : ''}><summary><input type="checkbox" data-${attr}a="${n}" ${all ? 'checked' : ''} onclick="event.stopPropagation()" title="Everyone of this class">
      <b>${esc(fgCls(c.cls))}</b> <span class="msg">${c.who.length} ${c.who.length === 1 ? 'person' : 'people'}${some ? ` · ${c.who.filter(p => who.has(p.npc)).length} ticked` : ''}</span></summary>
      ${c.who.map(p => `<label class="fgw-row fgw-person"><input type="checkbox" data-${attr}="${esc(p.npc)}" ${who.has(p.npc) ? 'checked' : ''}>
        <span class="fgw-nm">${esc(p.name)}</span><span class="msg fgw-why">${esc(p.where || 'not placed anywhere (a script or a list brings them)')}</span>
        <span class="fgw-src">${esc(p.carries || '')}</span></label>`).join('')}</details>`;
  }).join('');
}
function fgWhoBind(box, classes, who, attr, redraw){
  box.querySelectorAll(`[data-${attr}]`).forEach(c => c.onchange = () => { c.checked ? who.add(c.dataset[attr]) : who.delete(c.dataset[attr]); redraw(); });
  box.querySelectorAll(`[data-${attr}a]`).forEach(c => c.onchange = () => { classes[+c.dataset[attr + 'a']].who.forEach(p => c.checked ? who.add(p.npc) : who.delete(p.npc)); redraw(); });
}

// ---------- anyone, any merchant, a list of its own: the same for one piece and a whole set ----------
function fgExtrasInit(W_, item){
  W_.gives = W_.gives || []; W_.xsell = W_.xsell || [];
  const stem = String(W_.setName || (item && item.id) || 'new').toLowerCase().replace(/[^a-z0-9]+/g, '_').slice(0, 22);
  W_.own = W_.own || {on: false, id: stem + '_lev', level: 1, chance: 0, into: [], gives: []};
}
function fgChips(list, attr, levels){
  return list.map((x, n) => `<span class="fgw-chip on">${esc(x.name || x.id)} <span class="msg">${esc(x.what || '')}</span>${levels && x.type === 'LEVI' ? ` level <input class="inp num" data-${attr}lv="${n}" value="${x.level || 1}" style="width:48px">` : ''}<span class="lnk" data-${attr}x="${n}">✕</span></span>`).join('');
}
const FG_WHAT = {NPC_: 'person', CREA: 'creature', CONT: 'container', LEVI: 'loot list'};
function fgExtrasHtml(W_, isSet){
  const o = W_.own, it = isSet ? 'the set' : 'it';
  return `<div class="fg-h" style="margin-top:14px" title="Added to what they hold; people wear the best armour they carry.">Give ${it} to</div>
    <div class="dd"><input class="inp" id="fgx-give" placeholder="Person, creature or container" autocomplete="off"><div class="ddlist" id="fgx-give-l"></div></div>
    <div class="fgw-chips" style="margin-top:4px">${fgChips(W_.gives, 'xg')}</div>
    <div class="fg-h" style="margin-top:14px">Sold by</div>
    <div class="dd"><input class="inp" id="fgx-sell" placeholder="Any merchant" autocomplete="off"><div class="ddlist" id="fgx-sell-l"></div></div>
    <div class="fgw-chips" style="margin-top:4px">${fgChips(W_.xsell, 'xs')}</div>
    <label class="msg fg-radio" style="margin-top:14px" title="${isSet ? 'Hands out one piece at random each time. ' : ''}Put it in a loot list, a chest or on a person."><input type="checkbox" id="fgx-own" ${o.on ? 'checked' : ''}> A loot list of ${isSet ? 'the set\'s' : 'its'} own</label>
    ${o.on ? `<div class="fgx-own">
      <div class="fg-row"><span class="msg">ID</span><input class="inp" id="fgx-oid" value="${esc(o.id)}" style="flex:1"><span class="msg">level</span><input class="inp num" id="fgx-olv" value="${o.level}" style="width:52px">
        <span class="msg" title="Chance of nothing">none %</span><input class="inp num" id="fgx-ocn" value="${o.chance}" style="width:52px"></div>
      <div class="dd"><input class="inp" id="fgx-oin" placeholder="Put it in: a loot list, chest or person" autocomplete="off"><div class="ddlist" id="fgx-oin-l"></div></div>
      <div class="fgw-chips" style="margin-top:4px">${fgChips(o.into.concat(o.gives), 'xo', true)}</div></div>` : ''}`;
}
function fgExtrasBind(box, W_, redraw){
  const o = W_.own;
  const pick = (id, types, cb) => { if (box.querySelector('#' + id)) ddSearch(id, types, cb); };
  pick('fgx-give', 'NPC_,CREA,CONT', r => { if (!W_.gives.some(x => x.id === r.id)) W_.gives.push({id: r.id, name: r.name, what: FG_WHAT[r.type] || ''}); redraw(); });
  pick('fgx-sell', 'NPC_', r => { if (!W_.xsell.some(x => x.id === r.id)) W_.xsell.push({id: r.id, name: r.name, what: 'merchant'}); redraw(); });
  pick('fgx-oin', 'LEVI,NPC_,CREA,CONT', r => {
    const into = r.type === 'LEVI';
    const lst = into ? o.into : o.gives;
    if (!lst.some(x => x.id === r.id)) lst.push({id: r.id, name: r.name, type: r.type, what: FG_WHAT[r.type] || '', level: o.level});
    redraw();
  });
  box.querySelectorAll('[data-xgx]').forEach(b => b.onclick = () => { W_.gives.splice(+b.dataset.xgx, 1); redraw(); });
  box.querySelectorAll('[data-xsx]').forEach(b => b.onclick = () => { W_.xsell.splice(+b.dataset.xsx, 1); redraw(); });
  box.querySelectorAll('[data-xox]').forEach(b => b.onclick = () => { const n = +b.dataset.xox; n < o.into.length ? o.into.splice(n, 1) : o.gives.splice(n - o.into.length, 1); redraw(); });
  box.querySelectorAll('[data-xolv]').forEach(c => c.oninput = () => { const v = parseInt(c.value, 10); if (v > 0) o.into[+c.dataset.xolv].level = v; });
  const on = box.querySelector('#fgx-own'); if (on) on.onchange = () => { o.on = on.checked; redraw(); };
  const f = (id, k, num) => { const e = box.querySelector('#' + id); if (e) e.oninput = () => { o[k] = num ? Math.max(0, parseInt(e.value, 10) || 0) : e.value.trim(); fgWorldReady(); }; };
  f('fgx-oid', 'id'); f('fgx-olv', 'level', true); f('fgx-ocn', 'chance', true);
}
function fgExtrasPicks(W_){
  const o = W_.own;
  return {gives: W_.gives.map(x => x.id), xsell: W_.xsell.map(x => x.id),
          own_list: o.on && o.id && (o.into.length || o.gives.length) ? {id: o.id, level: o.level || 1, chance_none: o.chance || 0,
            into: o.into.map(x => ({list: x.id, level: x.level || o.level || 1})), gives: o.gives.map(x => x.id)} : null};
}
// (what will happen, in plain words, under the choices)
function fgSummary(p){
  const bits = [];
  if (p.nl) bits.push(`in ${p.nl} loot list${p.nl === 1 ? '' : 's'}`);
  const who = l => l.slice(0, 3).join(', ') + (l.length > 3 ? ` +${l.length - 3}` : '');
  if (p.people.length) bits.push(`${p.set ? 'worn' : 'carried'} by ${who(p.people)}`);
  if (p.sellers.length) bits.push(`sold by ${who(p.sellers)}`);
  if (p.gives.length) bits.push(`given to ${who(p.gives)}`);
  if (p.own) bits.push(`its own list in ${p.own.into.length + p.own.gives.length} place${p.own.into.length + p.own.gives.length === 1 ? '' : 's'}`);
  const s = bits.join('; ');
  return s ? s.charAt(0).toUpperCase() + s.slice(1) + '.' : '';
}
function fgWorldDraw(){
  const box = FG.bg && FG.bg.querySelector('#fg-body'), W_ = FG.world, d = W_ && W_.data; if (!box || !d) return;
  const it = d.item, mat = it.between ? `${it.between[0]} or ${it.between[1]}` : it.material;
  // (the carriers by class, each person by name and place)
  const byc = {};
  d.carriers.forEach(p => (byc[p.cls] = byc[p.cls] || []).push({npc: p.npc, name: p.name, where: p.where, carries: 'has ' + (p.theirs_name || p.theirs)}));
  W_.classes = Object.entries(byc).sort((a, b) => b[1].length - a[1].length).map(([cls, who]) => ({cls, who}));
  const row = (x, n, grp) => `<label class="fgw-row ${x.in ? 'in' : ''}"><input type="checkbox" data-wl="${grp}:${n}" ${x.in || W_[grp][n] ? 'checked' : ''} ${x.in ? 'disabled' : ''}>
      <span class="fgw-nm">${esc(x.list)}</span><span class="msg fgw-why">${x.in ? 'already in' : esc(x.why)}</span>
      <span class="fgw-src">${esc(x.src)}</span><span class="fgw-lv">level <input class="inp num" data-wlv="${grp}:${n}" value="${x.level}" ${x.in ? 'disabled' : ''}></span></label>`;
  const forged = W_.forged ? `<div class="cnote fgw-made">Forged <b>${esc(W_.forged)}</b>. Where should the game have it?</div>` : '';
  // (a set just forged: all of it at once, or its pieces one at a time, each its own Undo)
  const setRow = W_.set ? `${fgWorldModes()}<div class="fgw-set"><span class="fg-h" style="margin:0 6px 0 0">The set</span>${W_.set.map((p, n) => `<button class="fgw-piece ${p.id === W_.id ? 'on' : ''} ${p.placed ? 'done' : ''}" data-wp="${n}" title="${esc(p.id)}">${p.placed ? '✓ ' : ''}${esc(p.name)}</button>`).join('')}</div>` : '';
  box.innerHTML = `<div class="fgw">${forged}${setRow}
    <div class="fgw-head"><img class="thumb" data-tid="${esc(it.id)}" data-tt="${it.kind === 'weapon' ? 'WEAP' : 'ARMO'}" data-ts="64" alt="">
      <div><b>${esc(it.name || it.id)}</b><div class="msg">${esc(it.type_label)} · ${it.between ? `between ${esc(it.between[0])} and ${esc(it.between[1])}` : esc(FG_CAP(it.material))}${it.enchanted ? ' · enchanted' : ''} · <span class="lnk" id="fgw-edit">edit</span></div></div></div>
    <div class="fg-h" title="Where its like are, widest-used first, at the level its material has in each">Loot lists</div>
    ${d.fallback ? `<div class="msg warn fgw-note" title="${esc(d.fallback)}">None for ${esc(mat)}: the nearest, at their top level.</div>` : ''}
    <div class="fgw-list">${d.general.map((x, n) => row(x, n, 'lists')).join('') || '<div class="msg">None for this kind.</div>'}</div>
    ${d.some.length ? `<details class="fgw-more"><summary>For a people, faction or place (${d.some.length})</summary><div class="fgw-list">${d.some.map((x, n) => row(x, n, 'some')).join('')}</div></details>` : ''}
    ${W_.classes.length ? `<div class="fg-h" style="margin-top:14px" title="Tick someone and the one like it they carry is swapped for yours">Carried by, instead of theirs</div>
    <div class="fgw-list">${fgWhoHtml(W_.classes, W_.who, 'wq')}</div>` : ''}
    ${d.sellers.length ? `<div class="fg-h" style="margin-top:14px">Merchants with one like it</div>
    <div class="fgw-chips">${d.sellers.map((s, n) => `<label class="fgw-chip"><input type="checkbox" data-ws="${n}" ${W_.sell[n] ? 'checked' : ''}>${esc(s.name)} <span class="msg">${esc(s.where || fgCls(s.cls))}</span></label>`).join('')}</div>` : ''}
    ${fgExtrasHtml(W_, false)}
    <div class="msg fgw-note" style="margin-top:12px" title="Each change copies that list or person into your mod. If another mod changes the same one, the one loaded last wins.">One Undo takes it all back.</div></div>`;
  if (typeof v3ThumbScan === 'function') v3ThumbScan(box);
  const ed = box.querySelector('#fgw-edit'); if (ed) ed.onclick = () => { FG.bg.remove(); FG.bg = null; ieShow(it.id); };
  box.querySelectorAll('[data-wp]').forEach(b => b.onclick = () => { const p = W_.set[+b.dataset.wp]; W_.id = p.id; W_.forged = null; fgWorld(); });
  fgWorldModesBind(box);
  box.querySelectorAll('[data-wl]').forEach(c => c.onchange = () => { const [g, n] = c.dataset.wl.split(':'); W_[g][+n] = c.checked; fgWorldReady(); });
  box.querySelectorAll('[data-wlv]').forEach(c => c.oninput = () => { const [g, n] = c.dataset.wlv.split(':'); const v = parseInt(c.value, 10); if (v > 0) d[g === 'lists' ? 'general' : 'some'][+n].level = v; });
  fgWhoBind(box, W_.classes, W_.who, 'wq', fgWorldRedraw);
  box.querySelectorAll('[data-ws]').forEach(c => c.onchange = () => { W_.sell[+c.dataset.ws] = c.checked; fgWorldReady(); });
  fgExtrasBind(box, W_, fgWorldRedraw);
  fgWorldReady();
}
// (drawn again where it was scrolled to)
function fgWorldRedraw(){
  const win = FG.bg && FG.bg.querySelector('.fg-win'), y = win ? win.scrollTop : 0;
  (FG.world && FG.world.whole ? fgWorldSetDraw : fgWorldDraw)();
  if (win) win.scrollTop = y;
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
  W_.slists = d.pieces.map(p => { let n = 0; return p.general.map(x => !x.in && !x.stretch && (!p.item.between || x.kind === 'type') && n++ < 3); });
  W_.swho = new Set();
  W_.sclasses = d.classes.map(c => ({cls: c.cls, who: (c.who || []).map(p => ({npc: p.npc, name: p.name, where: p.where,
    carries: `has ${p.slots} of the set's kinds`}))}));
  W_.ssell = d.sellers.map(() => false);
  fgExtrasInit(W_, null);
  fgWorldSetDraw();
}
function fgWorldSetDraw(){
  const box = FG.bg && FG.bg.querySelector('#fg-body'), W_ = FG.world, d = W_ && W_.sd; if (!box || !d) return;
  const row = (x, pi, n) => `<label class="fgw-row ${x.in ? 'in' : ''}"><input type="checkbox" data-sl="${pi}:${n}" ${x.in || W_.slists[pi][n] ? 'checked' : ''} ${x.in ? 'disabled' : ''}>
      <span class="fgw-nm">${esc(x.list)}</span><span class="msg fgw-why">${x.in ? 'already in' : esc(x.why)}</span>
      <span class="fgw-src">${esc(x.src)}</span><span class="fgw-lv">level <input class="inp num" data-slv="${pi}:${n}" value="${x.level}" ${x.in ? 'disabled' : ''}></span></label>`;
  const forged = W_.forged ? `<div class="cnote fgw-made">Forged <b>${esc(W_.forged)}</b>. Where should the game have it?</div>` : '';
  box.innerHTML = `<div class="fgw">${forged}${fgWorldModes()}
    <div class="fg-h" title="Each piece where its like are, widest-used first">Loot lists</div>
    ${d.pieces.map((p, pi) => `<div class="fgws-piece"><div class="fgws-pn"><img class="thumb" data-tid="${esc(p.item.id)}" data-tt="${p.item.kind === 'weapon' ? 'WEAP' : 'ARMO'}" data-ts="32" alt=""><b>${esc(p.item.name || p.item.id)}</b><span class="msg">${esc(p.item.type_label)}</span></div>
      ${p.fallback && p.general.length ? `<div class="msg warn" style="font-size:11.5px" title="${esc(p.fallback)}">None for its material: the nearest, at their top level.</div>` : ''}
      <div class="fgw-list">${p.general.slice(0, 3).map((x, n) => row(x, pi, n)).join('') || '<div class="msg">None for this kind.</div>'}</div>
      ${p.general.length > 3 ? `<details class="fgw-more"><summary>${p.general.length - 3} more</summary><div class="fgw-list">${p.general.slice(3).map((x, n) => row(x, pi, n + 3)).join('')}</div></details>` : ''}</div>`).join('')}
    ${W_.sclasses.length ? `<div class="fg-h" style="margin-top:14px" title="Tick someone and they wear the whole set: their like pieces swapped, the rest added">Worn by, instead of theirs</div>
    <div class="fgw-list">${fgWhoHtml(W_.sclasses, W_.swho, 'sq')}</div>` : ''}
    ${d.sellers.length ? `<div class="fg-h" style="margin-top:14px">Merchants with pieces like these</div>
    <div class="fgw-chips">${d.sellers.map((s, n) => `<label class="fgw-chip"><input type="checkbox" data-ss="${n}" ${W_.ssell[n] ? 'checked' : ''}>${esc(s.name)} <span class="msg">${esc(s.where || fgCls(s.cls))}</span></label>`).join('')}</div>` : ''}
    ${fgExtrasHtml(W_, true)}
    <div class="msg fgw-note" style="margin-top:12px" title="A merchant stocks every piece. If another mod changes the same list or person, the one loaded last wins.">One Undo takes it all back.</div></div>`;
  if (typeof v3ThumbScan === 'function') v3ThumbScan(box);
  fgWorldModesBind(box);
  box.querySelectorAll('[data-sl]').forEach(c => c.onchange = () => { const [p, n] = c.dataset.sl.split(':'); W_.slists[+p][+n] = c.checked; fgWorldReady(); });
  box.querySelectorAll('[data-slv]').forEach(c => c.oninput = () => { const [p, n] = c.dataset.slv.split(':'); const v = parseInt(c.value, 10); if (v > 0) d.pieces[+p].general[+n].level = v; });
  fgWhoBind(box, W_.sclasses, W_.swho, 'sq', fgWorldRedraw);
  box.querySelectorAll('[data-ss]').forEach(c => c.onchange = () => { W_.ssell[+c.dataset.ss] = c.checked; fgWorldReady(); });
  fgExtrasBind(box, W_, fgWorldRedraw);
  fgWorldReady();
}
function fgWorldSetPicks(){
  const W_ = FG.world, d = W_ && W_.sd; if (!d) return null;
  const lists = {};
  let nl = 0;
  d.pieces.forEach((p, pi) => { lists[p.item.id] = p.general.filter((x, n) => W_.slists[pi][n] && !x.in).map(x => ({list: x.list, level: x.level})); nl += lists[p.item.id].length; });
  const people = [...W_.swho];
  const x = fgExtrasPicks(W_);
  const sells = d.sellers.filter((s, n) => W_.ssell[n]).map(s => s.npc).concat(x.xsell);
  const who = {}; W_.sclasses.forEach(c => c.who.forEach(p => { who[p.npc] = p.name; }));
  const sname = id => { const s = d.sellers.find(c => c.npc === id) || W_.xsell.find(c => c.id === id); return s ? s.name : id; };
  return {lists, classes: [], people, sells, gives: x.gives, own_list: x.own_list, nl, np: 0,
          sum: {nl, it: 'the set', set: true, people: people.map(k => who[k] || k), sellers: sells.map(sname), gives: W_.gives.map(g => g.name || g.id), own: x.own_list}};
}

// (more than one: "cuirasses", "helmets", "boots" as they are)
function fgPlural(w){ return /(greaves|boots|arrow|bolt)s?$/.test(w) ? w.replace(/(arrow|bolt)$/, '$1s') : /(s|sh|ch|x)$/.test(w) ? w + 'es' : w + 's'; }
// (a class's own name: the T_Glb_ and such prefixes of Tamriel Data's left off)
function fgCls(c){ return String(c || '').replace(/^T_[A-Za-z]+_/, '').replace(/([a-z])([A-Z])/g, '$1 $2'); }
// what is chosen: the lists, the people whose like piece is swapped (spread over each class's), the merchants
function fgWorldPicks(){
  const W_ = FG.world, d = W_ && W_.data; if (!d) return null;
  const lists = d.general.filter((x, n) => W_.lists[n] && !x.in).concat(d.some.filter((x, n) => W_.some[n] && !x.in)).map(x => ({list: x.list, level: x.level}));
  const swaps = d.carriers.filter(p => W_.who.has(p.npc)).map(p => ({npc: p.npc, theirs: p.theirs}));
  const x = fgExtrasPicks(W_);
  const sells = d.sellers.filter((s, n) => W_.sell[n]).map(s => s.npc).concat(x.xsell);
  const names = id => { const p = d.carriers.find(c => c.npc === id) || d.sellers.find(c => c.npc === id) || W_.xsell.find(c => c.id === id); return p ? p.name : id; };
  return {lists, swaps, sells, gives: x.gives, own_list: x.own_list,
          sum: {nl: lists.length, it: 'it', people: swaps.map(s => names(s.npc)), sellers: sells.map(names), gives: W_.gives.map(g => g.name || g.id), own: x.own_list}};
}
function fgWorldReady(){
  const go = FG.bg && FG.bg.querySelector('#fg-go'); if (!go) return;
  const whole = FG.world && FG.world.whole;
  const p = whole ? fgWorldSetPicks() : fgWorldPicks();
  go.innerHTML = whole ? '🌐 Put the whole set into the world' : '🌐 Put it into the world';
  const n = p ? (whole ? p.nl + p.people.length + p.np : p.lists.length + p.swaps.length) + p.sells.length + p.gives.length + (p.own_list ? 1 : 0) : 0;
  go.disabled = !n;
  if (p) fgMsg(n ? esc(fgSummary(p.sum)) : 'Tick where the game should find it.');
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
    FG.world.forged = null; FG.world.gives = []; FG.world.xsell = []; FG.world.own = null;
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
      mat: W_.between ? null : W_.mat, between: W_.between, name: W_.setName || '', people: q.people, gives: q.gives, own_list: q.own_list});
    W_.gives = []; W_.xsell = []; W_.own = null;
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
  .fgw-chip:has(input:checked),.fgw-chip.on{border-color:var(--gold)}
  .fgw-chip .lnk{margin-left:2px}
  .fgw-cls{border-top:1px solid var(--line);padding:2px 0}.fgw-cls>summary{cursor:pointer;padding:4px 6px;font-size:13px;display:flex;gap:8px;align-items:center}
  .fgw-cls>summary::before{content:'▸';color:var(--faint)}.fgw-cls[open]>summary::before{content:'▾'}
  .fgw-cls>summary::-webkit-details-marker{display:none}
  .modal .fgw-person{padding-left:26px}
  .fgx-own{border-left:2px solid var(--line2);padding:4px 0 4px 10px;margin:4px 0}
  .fg-ownl{display:flex;gap:6px;align-items:center;margin:3px 0}.fg-ownl select{flex:1;min-width:0}
  .flp-grid{grid-template-columns:repeat(auto-fill,minmax(118px,1fr));max-height:56vh}
  .fg-look small{font-size:10px;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .fs-lk{display:flex;gap:6px;align-items:center;flex-wrap:wrap}.fs-lk select{max-width:200px;padding:2px 4px;font-size:12px}
  .fg-skin{display:flex;flex-direction:column;gap:8px;margin:10px 0;max-height:56vh;overflow:auto}
  .fg-skinr{display:grid;grid-template-columns:64px 1fr;gap:8px;align-items:center}
  .fg-skinr img{width:64px;height:64px;object-fit:cover;border-radius:6px;background:#000}`;
  document.head.appendChild(c);
}
