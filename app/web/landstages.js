// The Land panel in stages (the user, 2026-11-09: "you shape it first and then place things you want on it ... it would
// be nice for all these things to happen in stages that you could actually preview before proceeding"). Mark the cells,
// then 1 Land, 2 Places, 3 Insides and people. Each stage is made for real, one Undo step, then kept, tried again or
// dropped. Keeping takes its shapes off the map: kept land is the start of the next Make and the auto pass leaves it.
// The settings sit behind each stage's gear. Built on landmap.js and castle.js.
const LST_LAND = ['coast', 'ridge', 'river', 'valley', 'plateau', 'lake', 'cover'];
const LST_LAND_MORE = ['cliff', 'stamp', 'spring', 'area'];
const LST_PLACE = ['town', 'castle', 'road', 'farm', 'orchard', 'dungeon'];
const LST_PLACE_ALL = new Set(['town', 'castle', 'road', 'farm', 'orchard', 'dungeon', 'harbour', 'small', 'label', 'street', 'zone', 'gate', 'wall']);
const LST_NAMES = ['Land', 'Places', 'Insides and people'];
const LST_MAKE = ['Make land', 'Make places', 'Make insides'];
const LST_NOTE = ['Made the land', 'Made the places', 'Made the insides'];

function lstOf(L){ return LST_PLACE_ALL.has(L.kind) ? 1 : 0; }
// (the land has no stage on show: Make land makes it, Make land again makes it again, Undo takes it back. A land
// stage left on show by an older Workshop becomes the last Make; the user, 2026-11-10: "too confusing if a land change
// is kept or in limbo or being previewed")
function lstStage(){
  const P = LM.plan, s = P && P.stage;
  if (s && s.n === 0){ P.made = P.made || {id: 0, d0: s.d0, d1: s.d1, cells: P.stageCells || []}; P.stage = null; delete P.stageCells; return null; }
  return s && s.n != null ? s : null;
}
// (the drawn Cliff lines, laid by Make land with the rest, and the cells they run through)
function lstCliffs(){ return lstLayers(0).map(([L]) => L).filter(L => L.kind === 'cliff' && L.on !== false && L.pts && L.pts.length >= 2); }
function lstCliffCells(){
  const out = new Set();
  for (const L of lstCliffs()) for (let i = 0; i < L.pts.length - 1; i++){
    const a = L.pts[i], b = L.pts[i + 1], n = Math.max(1, Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / 1024));
    for (let j = 0; j <= n; j++) out.add(Math.floor((a[0] + (b[0] - a[0]) * j / n) / 8192) + ',' + Math.floor((a[1] + (b[1] - a[1]) * j / n) / 8192));
  }
  return [...out];
}
// (what Make land was asked: the same again rolls it anew)
function lstLandSig(){
  const P = LM.plan, s = JSON.stringify([lstLayers(0).map(([L]) => [L.kind, L.on !== false, L.pts, L.p, L.like, L.only]), P.terrain, P.dress, P.clear, lstLandCells()]);
  let h = 0; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return s.length + ':' + h;
}
function lstKept(){ return new Set((LM.plan && LM.plan.kept) || []); }
function lstLayers(n){ return ((LM.plan && LM.plan.layers) || []).map((L, i) => [L, i]).filter(([L]) => lstOf(L) === n); }
// (the cells a Make land works on: the marked cells not kept yet, and the kept ones a drawn shape reaches)
function lstLandCells(){
  const marks = (LM.data && LM.data.marks) || [], kept = lstKept(), reach = new Set();
  for (const [L] of lstLayers(0)) if (L.on !== false && L.pts && L.pts.length && (!lsNoShape(L.kind) || L.kind === 'cover')) lsShapeCells(L).forEach(k => reach.add(k));
  const auto = lsTerrOn();
  return marks.filter(k => kept.has(k) ? reach.has(k) : (auto || reach.has(k)));
}
// ("Clear what's there first", standins.py: shown with the automatic shaping when the cells being made hold something
// to clear; the user, 2026-11-09, "where one chooses to automatically shape and dress the land, perhaps this should be
// an option". Off: ''. Unset: Tamriel.esm's stand-ins when there are some)
function lstClear(){
  const P = LM.plan, C = LM.clearN;
  if (!lsTerrOn() || !C) return '';
  if (P.clear === '' ) return '';
  const v = P.clear || (C.standins ? 'standins' : '');
  return C[v] ? v : '';
}
async function lstClearCount(){
  const cells = lstLandCells(), sig = cells.join(';');
  if (!lsTerrOn() || !cells.length){ LM.clearN = null; LM.clearSig = ''; return; }
  if (sig === LM.clearSig) return;
  LM.clearSig = sig;
  try { const r = await post('/api/land/clearable', {cells}); if (LM.clearSig === sig){ LM.clearN = r; renderWside(); } } catch (e){}
}
function lstPlacesTodo(){
  return lstLayers(1).filter(([L]) => L.on !== false && L.pts && L.pts.length && L.kind !== 'dungeon' && !(L.p || {}).built && !LS_KINDS[L.kind].town).map(([L]) => L);
}
function lstDungeonsTodo(){ return lstLayers(1).filter(([L]) => L.kind === 'dungeon' && L.on !== false && !(L.p || {}).built).map(([L]) => L); }

async function lstDepth(){ try { const s = await api('/api/status'); return (s.project && s.project.undo_depth) || 0; } catch (e){ return 0; } }
function lstSave(){ return post('/api/land/plan', {plan: LM.plan}).catch(() => {}); }

function lstCss(){
  if ($('#lst-css')) return;
  const c = document.createElement('style'); c.id = 'lst-css';
  c.textContent = `#lst-root{display:flex;flex-direction:column;gap:2px}
    .lst-top{display:flex;gap:4px;align-items:center;margin-bottom:4px}.lst-top .lst-n{flex:1;text-align:right;font-size:11.5px;color:var(--muted)}
    .lst-top .btn.on{outline:1px solid var(--gold);background:color-mix(in srgb,var(--gold) 22%,transparent)}
    .lst-hd{display:flex;align-items:center;gap:7px;padding:7px 2px;border-top:1px solid var(--line);cursor:pointer;font-weight:600;font-size:13px}
    .lst-num{width:19px;height:19px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:11px;background:var(--panel2,rgba(255,255,255,.06));color:var(--muted);flex:none}
    .lst-hd.open .lst-num{background:color-mix(in srgb,var(--gold) 30%,transparent);color:var(--text)}
    .lst-chip{margin-left:auto;font-weight:400;font-size:11px;color:var(--gold)}
    .lst-gear{background:none;border:0;color:var(--muted);cursor:pointer;font-size:14px;padding:0 2px}.lst-gear.on{color:var(--gold)}
    .lst-body{padding:0 2px 8px 26px;display:flex;flex-direction:column;gap:5px}
    .lst-tools{display:grid;grid-template-columns:repeat(4,1fr);gap:3px}
    .lst-tools button{display:flex;flex-direction:column;align-items:center;gap:1px;padding:4px 1px;font-size:10.5px;line-height:1.1;border:1px solid var(--line);border-radius:6px;background:none;color:var(--muted);cursor:pointer}
    .lst-tools button:hover{color:var(--text);border-color:var(--gold)}.lst-tools button span{font-size:15px;line-height:1.2}
    .lst-act{display:flex;gap:4px;flex-wrap:wrap}.lst-act .btn{flex:none}
    .lst-st{font-size:10.5px;color:var(--muted);white-space:nowrap}.lst-st.busy{color:var(--gold)}
    .lst-made{border-top:1px dashed var(--line);margin-top:3px;padding-top:3px}
    .lst-made-hd{font-size:11.5px;color:var(--muted);cursor:pointer;display:flex;gap:5px}.lst-made-hd:hover{color:var(--text)}
    .lst-mrow{display:flex;align-items:center;gap:5px;font-size:12px;padding:1px 0}.lst-mrow .nm{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    #lst-root #ls-tmake,#lst-root #cs-make{display:none}
    .lst-gearbox{border-left:2px solid var(--line);padding-left:8px;margin-top:2px}
    .lst-more{position:relative}.lst-menu{position:absolute;right:0;top:100%;z-index:20;display:flex;flex-direction:column;gap:2px;min-width:170px;padding:5px;background:var(--panel);border:1px solid var(--line);border-radius:6px;box-shadow:0 4px 16px rgba(0,0,0,.4)}
    .lst-menu button,.lst-menu label{text-align:left;font-size:12px;padding:3px 6px;background:none;border:0;color:var(--text);cursor:pointer;border-radius:4px;display:flex;gap:6px;align-items:center}
    .lst-menu button:hover,.lst-menu label:hover{background:color-mix(in srgb,var(--gold) 18%,transparent)}.lst-menu button:disabled{opacity:.4;cursor:default}`;
  document.head.appendChild(c);
}

function lstTool(k){
  const K = LS_KINDS[k];
  return `<button data-add="${k}" title="${esc(K.how)}"><span style="color:${K.color}">${K.icon}</span>${esc(K.label)}</button>`;
}
function lstActs(n, can, why){
  const st = lstStage();
  // (a make under way stays on its button through every redraw, and no stage can be started meanwhile: the user pressed
  // Make insides, a redraw put the plain button back, and nothing said it was working; 2026-11-11)
  const R = LM.running;
  if (R) return `<div class="lst-act"><button class="btn sm primary" id="${n === 0 ? 'ls-apply' : 'lst-make' + n}" disabled>${R.n === n ? `<span class="spin"></span>${esc(R.t)}` : LST_MAKE[n]}</button></div>`;
  if (n === 0) return `<div class="lst-act"><button class="btn sm primary" id="ls-apply" data-make="0" ${can && !st ? '' : 'disabled'} title="${esc(st ? 'Keep or drop the places on show first' : why + '. Pressed again, it makes the land again; Undo takes it back')}">${LST_MAKE[0]}</button></div>`;
  if (st && st.n === n) return `<div class="lst-act"><button class="btn sm primary" data-keep="${n}" title="Keep it. Its shapes leave the map">✓ Keep</button><button class="btn sm" data-retry="${n}" title="Undo it and make it again, rolled anew">↻ Try again</button><button class="btn sm" data-drop="${n}" title="Undo it">✕ Drop</button></div>`;
  return `<div class="lst-act"><button class="btn sm primary" id="${n === 0 ? 'ls-apply' : 'lst-make' + n}" data-make="${n}" ${can && !st ? '' : 'disabled'} title="${esc(st ? 'Keep or drop the stage on show first' : why)}">${LST_MAKE[n]}</button></div>`;
}
// (what a town or castle is doing, on its row: planning, waiting on the learning, ready with so many buildings, built;
// the user, 2026-11-09, "I am never sure if any of this is working")
function lstState(L){
  const T = (L.kind === 'castle' ? LM.castles : LM.towns) || {}, t = T[L.id];
  if (L.kind !== 'town' && L.kind !== 'castle') return (L.p || {}).built ? 'built' : '';
  if ((L.p || {}).built) return 'built';
  if (!t) return lsSizeOf(L);
  if (t.plan && !t.busy && L.kind === 'castle') return 'previewed';
  if (t.built) return 'built';
  if (t.learning) return 'learning…';
  if (t.err) return 'no plan';
  if (t.busy || !t.plan) return 'planning…';
  const n = L.kind === 'town' ? ((t.plan.plots || []).length) : 0;
  return n ? `${n} buildings` : 'ready';
}
function lstRows(n){
  const rows = lstLayers(n).map(([L, i]) => {
    const st = lstState(L); let h = lsRowHtml(L, i);
    // (👁: this place planned once and drawn on the map, until it is changed; nothing is planned by itself)
    const pv = (L.kind === 'town' || L.kind === 'castle') && !(L.p || {}).built && L.on !== false
      ? `<button class="xbtn" data-preview="${i}" title="Preview: plan it once and draw its streets, buildings and walls on the map. It stays until you change the place">👁</button>` : '';
    return h.replace('<button class="xbtn" data-up', `${st ? `<span class="lst-st${/…/.test(st) ? ' busy' : ''}">${esc(st)}</span>` : ''}${pv}<button class="xbtn" data-up`);
  }).join('');
  return rows ? `<div class="ls-list">${rows}</div>` : '';
}
function lstParams(n){
  const P = LM.plan, sel = P && P.layers[LM.sel];
  if (!sel || lstOf(sel) !== n) return '';
  if (sel.kind === 'town' || sel.kind === 'castle'){
    // (a town or castle: its size and whose look in view, the rest folded away; the user, 2026-11-09, "just figure it out")
    const S = LS_MARK_R[sel.kind], cur = lsSizeOf(sel), names = {village: 'Village', town: 'Town', city: 'City', small: 'Small', medium: 'Medium', large: 'Large', great: 'Great (biggest)'};
    if (sel.kind === 'town' && !LM.cultures && !LM.culturesAsked) lsCultures().then(c => { if (c) renderWside(); });
    const cs = LM.cultures || [], st = LM.csStyles || [];
    const like = sel.kind === 'town'
      ? `<label>Like <select class="inp" id="lst-plike"><option value="">nearest in weather</option>${cs.map(c => `<option value="${esc(c.id)}" ${sel.p.culture === c.id ? 'selected' : ''}>${esc(c.label || c.id)}</option>`).join('')}</select></label>`
      : `<label>Like <select class="inp" id="lst-plike">${(st.length ? st : [{id: sel.p.style || 'Imperial'}]).map(c => `<option value="${esc(c.id || c)}" ${(sel.p.style || 'Imperial') === (c.id || c) ? 'selected' : ''}>${esc(c.label || c.id || c)}</option>`).join('')}</select></label>`;
    // (a town with drawn limits has the size drawn: no Size to pick; a castle's Size is its own setting)
    const size = sel.kind === 'town' && !(sel.p || {}).marker ? '' : `<label>Size <select class="inp" id="lst-psize">${Object.keys(S).map(k => `<option value="${k}" ${k === cur ? 'selected' : ''}>${names[k]}</option>`).join('')}</select></label>`;
    return `<div class="lm-raise">${size}${like}
      <details class="lst-more-set"${LM.moreSet ? ' open' : ''}><summary class="msg" style="cursor:pointer;font-size:11.5px">More settings</summary>${lsParamsHtml(sel)}</details></div>`;
  }
  // (a Cliff is laid by Make land with the rest: no button of its own)
  return `<div class="lm-raise">${lsParamsHtml(sel).replace(/<div class="actions"><button[^>]*id="ls-clay"[\s\S]*?<\/div>/, '')}</div>`;
}
function lstHead(n, chip){
  const open = LM.stageOpen === n;
  return `<div class="lst-hd${open ? ' open' : ''}" data-stage="${n}"><span class="lst-num">${n + 1}</span>${LST_NAMES[n]}<span class="lst-chip">${chip || ''}</span>
    <button class="lst-gear${LM.gear && LM.gear[n] ? ' on' : ''}" data-gear="${n}" title="Settings">⚙</button></div>`;
}

function lstLandHtml(P){
  const T = P.terrain = Object.assign({}, LS_TERRAIN, P.terrain || {});
  const cells = lstLandCells(), ng = lstLayers(0).filter(([L]) => L.on !== false && !lsNoShape(L.kind)).length;
  const gear = LM.gear && LM.gear[0];
  let g = '';
  LM.prevOn = true;               // (the drawn shapes are always sketched on the map)
  if (gear){
    // (three levers: the user, 2026-11-10, "too many boxes and levers")
    const D = P.dress = Object.assign({}, LS_DRESS, P.dress || {});
    const sl = (a, k, v, lab, tip) => `<label title="${esc(tip)}" style="display:flex;gap:6px;align-items:center;font-size:12px">${lab} <input type="range" data-${a}="${k}" min="0" max="2" step="0.1" value="${v}" style="flex:1;min-width:0"><span style="width:26px;text-align:right">${v}</span></label>`;
    g = `<div class="lst-gearbox">${sl('dr', 'rocks', D.rocks, 'Rocks', 'How many rocks on the steep ground: 1 as the game sets them, 0 none, 2 twice')}
      ${sl('tr', 'trees_k', T.trees_k != null ? T.trees_k : 1, 'Trees', 'How many trees: 1 as the land would have them, 0 none, 2 twice')}
      ${sl('tr', 'plants_k', T.plants_k != null ? T.plants_k : 1, 'Plants', 'How many plants: 1 as the land would have them, 0 none, 2 twice')}</div>`;
  }
  const nc = lstCliffs().length;
  const why = !(LM.data && LM.data.marks.length) && !nc ? 'Mark the cells first' : !cells.length && !nc ? 'Draw a shape, or tick Shape the rest automatically' : cells.length ? `${cells.length} cells` : 'The cliff';
  return `<label class="msg" style="display:flex;gap:6px;align-items:center" title="The marked land made as rough, as broken into ranges and as cut by valleys as a hand-made region's, round whatever you draw"><input type="checkbox" id="lst-auto" ${T.on ? 'checked' : ''}> Shape the rest automatically</label>
    ${lstClearHtml(P)}
    <div class="lst-tools">${LST_LAND.map(lstTool).join('')}<button id="lst-more0" title="More shapes">${LM.more0 ? '<span>−</span>Fewer' : '<span>⋯</span>More'}</button>${LM.more0 ? LST_LAND_MORE.map(lstTool).join('') : ''}</div>
    ${lstRows(0)}${lstActs(0, cells.length || nc, why)}${lstParams(0)}${g}`;
}
// (the Trees and Plants sliders: how thick the automatic shaping and Clear first lay them; the user, 2026-11-09)
function lstDensHtml(T){
  const sl = (k, lab, tip) => `<label title="${esc(tip)}" style="display:flex;gap:6px;align-items:center;font-size:12px">${lab} <input type="range" data-tr="${k}" min="0" max="2" step="0.1" value="${T[k] != null ? T[k] : 1}" style="flex:1;min-width:0"><span style="width:26px;text-align:right">${T[k] != null ? T[k] : 1}</span></label>`;
  return sl('trees_k', 'Trees', 'How many trees: 1 as the land would have them (where Tamriel.esm stood stand-in trees, as many as they stood for), 0 none, 2 twice')
    + sl('plants_k', 'Plants', 'How many plants: 1 as the land would have them, 0 none, 2 twice');
}
function lstClearHtml(P){
  const C = LM.clearN;
  if (!lsTerrOn() || !C || !(C.standins || C.nature || C.all)) return '';
  const v = lstClear(), cur = v || P.clear || (C.standins ? 'standins' : C.nature ? 'nature' : 'all');
  // (the count short, so the list fits the panel: "stand-ins (1579…" was cut off, the user's screenshot 2026-11-09)
  const short = n => n >= 10000 ? Math.round(n / 1000) + 'k' : n >= 1000 ? (n / 1000).toFixed(1) + 'k' : String(n);
  const opt = (k, t) => C[k] ? `<option value="${k}" ${cur === k ? 'selected' : ''} title="${C[k]} objects">${t} ${short(C[k])}</option>` : '';
  return `<label class="msg" style="display:flex;gap:6px;align-items:center;flex-wrap:wrap" title="Other mods' objects in the cells being made, marked removed by your mod first (turn your mod off and they're back). Stand-ins: Tamriel.esm's low-detail towns, trees and rocks, with the region's real trees and rocks where theirs stood"><input type="checkbox" id="lst-clear" ${v ? 'checked' : ''}> Clear first
    <select class="inp" id="lst-clearwhat" style="flex:1;min-width:0;max-width:100%">${opt('standins', 'stand-ins')}${opt('nature', 'nature')}${opt('all', 'everything')}</select></label>`;
}
function lstPlacesHtml(P){
  const Q = P.places = Object.assign({}, LS_PLACES, P.places || {});
  const todo = lstPlacesTodo();
  let g = '';
  if (LM.gear && LM.gear[1]){
    if (!LM.cultures) lsCultures().then(cs => { if (cs && cs.length) renderWside(); });
    const cs = LM.cultures || [];
    const sl = (key, lab, tip) => `<label title="${esc(tip)}">${lab} <input type="range" data-pl="${key}" min="0" max="2" step="0.1" value="${Q[key]}"><span>${Q[key]}</span></label>`;
    g = `<div class="lst-gearbox"><div class="lm-raise">
      ${sl('settlements', 'Towns', 'How many towns Suggest puts down: as many as the game has on as much land (1)')}
      ${sl('dungeons', 'Dungeons', 'How many dungeons Suggest puts down (1: the game\'s rate)')}
      ${sl('small', 'Small things', 'Camps, carts, graves, shrines, wrecks (1: the game\'s rate)')}
      <label title="Whose towns they are planned like">Culture <select class="inp" id="lsq-cult"><option value="">nearest in weather</option>${cs.map(c => `<option value="${esc(c.id)}" ${Q.culture === c.id ? 'selected' : ''}>${esc(c.label || c.id)}</option>`).join('')}</select></label>
      <div class="actions"><button class="btn sm" id="lsq-roads" title="Roads between the towns on the map">🛤 Suggest roads only</button></div></div></div>`;
  }
  return `<div class="lst-tools">${LST_PLACE.map(lstTool).join('')}<button id="lsq-go" ${LM.data && LM.data.marks.length ? '' : 'disabled'} title="Towns, dungeons, farms, roads and small places put down at the game's rates over the marked cells, to move or drop before you make them"><span>🎲</span>Suggest</button></div>
    ${lstRows(1)}${lstActs(1, todo.length, todo.length ? `${todo.length} to make` : 'Draw a town, castle, road or farm, or press Suggest')}${lstParams(1)}${g}${lstMadeHtml()}`;
}
// (the made places the mod keeps a record of (ledger.py): each looked at, made again or dropped on its own, whatever
// was built after it. Before, only the last stage could be dropped, by Undo)
const LST_MADE_ICON = {town: '🏘', castle: '🏰', dungeon: '🕳', interior: '🚪'};
const LST_MADE_MAX = 40;
async function lstMade(){ try { LM.made = (await post('/api/places', {})).places || []; } catch (e){ LM.made = []; } }
function lstMadeHtml(){
  const M = (LM.made || []).filter(m => LST_MADE_ICON[m.kind]);
  if (!M.length) return '';
  const rows = !LM.madeOpen ? '' : M.slice(0, LST_MADE_MAX).map(m => {
    const tip = `${m.things} things${m.interiors ? ', ' + m.interiors + ' interiors' : ''}${m.seed != null ? ', seed ' + m.seed : ''}${m.state === 'part' ? '. Its Make stopped half way' : ''}`;
    return `<div class="lst-mrow" title="${esc(tip)}"><span>${LST_MADE_ICON[m.kind]}</span><span class="nm">${esc(m.name || m.kind)}</span><span class="lst-st">${m.state === 'part' ? 'part' : m.things}</span>
      <button class="xbtn" data-mlook="${esc(m.id)}" title="Go there">👁</button>${m.again ? `<button class="xbtn" data-magain="${esc(m.id)}" title="Try again: this one taken away and made anew where it stands, another layout. One Undo">↻</button>` : ''}<button class="xbtn" data-mdrop="${esc(m.id)}" title="Drop only this: what it built and its interiors. What was made after it, what you added and the ground stay. One Undo">✕</button></div>`;
  }).join('');
  return `<div class="lst-made"><div class="lst-made-hd" id="lst-made-hd" title="What the mod's Makes have built">${LM.madeOpen ? '▾' : '▸'} Made · ${M.length}</div>${rows}</div>`;
}
async function lstMadeAfter(){
  // (the map's towns and castles asked of the mod again: one dropped is to make, one made again stays built)
  for (const L of (LM.plan && LM.plan.layers) || []) if ((L.kind === 'town' || L.kind === 'castle') && L.p) L.p.built = (await lsBuiltAt(L)) ? 'yes' : '';
  await lstSave();
  if (typeof refreshAfterEdits === 'function') await refreshAfterEdits();
  await lstLater();
  await lstReload();
  renderWside();
}
function lstMadeBind(root){
  const hd = $('#lst-made-hd'); if (hd) hd.onclick = () => { LM.madeOpen = !LM.madeOpen; renderWside(); };
  const of = id => (LM.made || []).find(m => m.id === id);
  root.querySelectorAll('[data-mlook]').forEach(b => b.onclick = () => {
    const m = of(b.dataset.mlook); if (!m) return;
    if (m.at) worldOpen('#' + Math.floor(m.at[0] / CELL) + ',' + Math.floor(m.at[1] / CELL)); else if (m.cell) worldOpen(m.cell);
  });
  root.querySelectorAll('[data-mdrop]').forEach(b => b.onclick = async () => {
    const m = of(b.dataset.mdrop); if (!m) return;
    let n; try { n = await post('/api/places/drop', {id: m.id, look: true}); } catch (e){ return toast(e.message, true); }
    if (!confirm(`Drop ${m.name || 'this ' + m.kind}: ${n.things} things it built and ${n.interiors} interiors? What was made after it, what you added and the ground stay. One Undo brings it back.`)) return;
    b.disabled = true; b.innerHTML = '<span class="spin"></span>';
    try { const r = await post('/api/places/drop', {id: m.id}); toast(`Dropped ${esc(m.name || 'it')}: ${r.things} things and ${r.interiors} interiors.`); }
    catch (e){ toast(e.message, true); }
    await lstMadeAfter();
  });
  root.querySelectorAll('[data-magain]').forEach(b => b.onclick = async () => {
    const m = of(b.dataset.magain); if (!m) return;
    if (!confirm(`Make ${m.name || 'this ' + m.kind} again with another layout? What it built is taken away first; what was made after it and what you added stay. One Undo brings the old one back.`)) return;
    b.disabled = true; b.innerHTML = '<span class="spin"></span>';
    try {
      const r = await post('/api/places/again', {id: m.id});
      if (r.learning) toast('Still learning the towns of the game: try again when it is done.', true);
      else {
        // (the map's own marker of it takes the new seed, so its plan and what stands agree)
        if (m.at && r.seed != null) for (const L of (LM.plan && LM.plan.layers) || []) if (L.kind === m.kind && L.p && L.pts && L.pts.length >= 3 && lsInPoly(L.pts, m.at[0], m.at[1])) L.p.seed = r.seed;
        toast(`Made ${esc(r.name || m.name || 'it')} again.`);
      }
    } catch (e){ toast(e.message, true); }
    await lstMadeAfter();
  });
}
function lstInsidesHtml(P){
  const I = LM.ins = Object.assign({interiors: true, dungeons: true, people: true, quests: false, rooms: 'furnished'}, LM.ins || {});
  const nt = (LM.later || []).length, nd = lstDungeonsTodo().length;
  const ck = (k, lab, n) => `<label class="msg" style="display:flex;gap:6px;align-items:center"><input type="checkbox" data-ins="${k}" ${I[k] ? 'checked' : ''}> ${lab}${n != null ? ` <span style="color:var(--muted)">(${n})</span>` : ''}</label>`;
  const g = LM.gear && LM.gear[2] ? `<div class="lst-gearbox"><div class="lm-raise"><label title="Furnished by the Workshop, or the buildings' architecture only, for you to furnish">Rooms <select class="inp" id="lst-rooms"><option value="furnished" ${I.rooms !== 'shells' ? 'selected' : ''}>furnished</option><option value="shells" ${I.rooms === 'shells' ? 'selected' : ''}>empty shells</option></select></label></div></div>` : '';
  const can = (I.interiors && nt) || (I.dungeons && nd) || I.people || I.quests;
  return `${ck('interiors', 'Interiors', nt ? nt + (nt === 1 ? ' town' : ' towns') : 0)}${ck('dungeons', 'Dungeons', nd)}${ck('people', 'People and creatures')}${ck('quests', 'Rumours and quests')}
    ${lstActs(2, can, 'Tick what to make')}${g}`;
}

function lstHtml(i){
  if (!i || i.interior) return '';
  lstCss();
  const D = LM.data, n = D ? D.marks.length : 0, P = LM.plan;
  if (!D || !P) return '<div id="lst-root"><div class="msg">Reading the land…</div></div>';
  const st = lstStage();
  if (LM.stageOpen == null) LM.stageOpen = st ? st.n : 0;
  const chip = k => st && st.n === k ? 'to look at' : '';
  const body = [lstLandHtml, lstPlacesHtml, lstInsidesHtml];
  const menu = LM.menuOpen ? `<div class="lst-menu">
      <button id="lm-clear" ${n ? '' : 'disabled'}>Clear marks</button>
      <button id="lm-dress">🪨 Dress…</button>
      <button id="lm-revert" ${n ? '' : 'disabled'} title="The land in the marked cells back as it was before your mod">↶ Undo my land</button>
      <button id="lm-setdown" ${n ? '' : 'disabled'} title="Your mod's crates, barrels, sacks, clutter and furniture in the marked cells lifted out of the dirt or let down onto it. Rocks, plants, fences and buildings stay as they are.">⤓ Set loose things down</button>
      <label><input type="checkbox" id="lm-show" ${LM.show ? 'checked' : ''}> Land map</label>
      <label><input type="checkbox" id="lm-flow" ${LM.flowOn ? 'checked' : ''}> Where water runs</label>
      <button id="lm-export" ${n ? '' : 'disabled'}>⬇ Save as height map</button>
      <button id="lm-import">⬆ Bring in a height map…</button><input type="file" id="lm-file" accept=".png,image/png" style="display:none">
    </div>` : '';
  return `<div id="lst-root">
    <div class="lst-top"><button class="btn sm${W.mode === 'landmap' && LM.brush === 'add' ? ' on' : ''}" id="lst-mark" title="Drag over cells to mark them. Shift+drag: a box. Right-drag moves the map">🖌 Mark</button>
      <button class="btn sm${W.mode === 'landmap' && LM.brush === 'del' ? ' on' : ''}" id="lst-unmark" ${n ? '' : 'disabled'} title="Drag over marked cells to unmark them">⌫ Unmark</button>
      <button class="btn sm" id="ls-undo" ${(LM.hist || []).length ? '' : 'disabled'} title="Undo the last change to your shapes (Ctrl+Z): a moved point, a removed shape, a setting">↶</button><button class="btn sm" id="ls-redo" ${(LM.fut || []).length ? '' : 'disabled'} title="Redo (Ctrl+Y)">↷</button>
      ${LM.before ? '<button class="btn sm" id="lm-before" title="Hold: the land as it was before">◐</button>' : ''}
      <span class="lst-n">${n ? n + ' cells' : ''}</span>
      <span class="lst-more"><button class="btn sm" id="lst-menu" title="More">⋮</button>${menu}</span></div>
    ${D.learning ? '<div class="msg" style="font-size:11.5px">Learning the game\'s land…</div>' : ''}
    <div id="lm-imp"></div>
    ${[0, 1, 2].map(k => lstHead(k, chip(k)) + (LM.stageOpen === k ? `<div class="lst-body">${body[k](P)}</div>` : '')).join('')}
  </div>`;
}

async function lstBind(i){
  if (!i || i.interior) return;
  lmCss(); lsCss(); lstCss();
  if (!LM.data){ try { await lmLoad(); } catch (e){ return; } renderWside(); return; }
  if (LM.later == null && !LM.laterAsked){ LM.laterAsked = true; lstLater().then(() => renderWside()); }
  if (LM.made == null && !LM.madeAsked){ LM.madeAsked = true; lstMade().then(() => renderWside()); }
  // (towns and castles built before places kept their "built" (test6 and before), asked of the mod once: the map
  // called the user's built city "to make", 2026-11-09)
  if (!LM.builtAsked && LM.plan){
    LM.builtAsked = true;
    (async () => {
      let n = 0;
      for (const L of LM.plan.layers) if ((L.kind === 'town' || L.kind === 'castle') && L.on !== false && !(L.p || {}).built && await lsBuiltAt(L)){ L.p.built = 'yes'; n++; }
      if (n){ await lstSave(); renderWside(); drawMap(); }
    })();
  }
  const root = $('#lst-root'); if (!root) return;
  const P = LM.plan;
  // (the old panel's own handlers first, for the pieces it shares: rows, a shape's settings, the gear's sliders, the
  // menu; the stage buttons after, so Make land is the stage's and not the old Shape)
  lmViewBindParts();
  lsBind();
  root.querySelectorAll('.lst-hd').forEach(h => h.onclick = e => { if (e.target.closest('.lst-gear')) return; LM.stageOpen = +h.dataset.stage; LM.sel = null; renderWside(); drawMap(); });
  root.querySelectorAll('[data-gear]').forEach(b => b.onclick = () => { const k = +b.dataset.gear; LM.gear = LM.gear || {}; LM.gear[k] = !LM.gear[k]; LM.stageOpen = k; renderWside(); });
  const mk = $('#lst-mark'); if (mk) mk.onclick = async () => { if (V3.on) await v3Enable(false); if (W.mode === 'landmap' && LM.brush === 'add'){ setMode(null); renderWside(); } else lmMark('add'); };
  const um = $('#lst-unmark'); if (um) um.onclick = async () => { if (V3.on) await v3Enable(false); if (W.mode === 'landmap' && LM.brush === 'del'){ setMode(null); renderWside(); } else lmMark('del'); };
  const mn = $('#lst-menu'); if (mn) mn.onclick = e => { e.stopPropagation(); LM.menuOpen = !LM.menuOpen; renderWside(); };
  if (LM.menuOpen) setTimeout(() => document.addEventListener('click', function off(e){ if (!e.target.closest('.lst-more')){ LM.menuOpen = false; document.removeEventListener('click', off); renderWside(); } }), 0);
  const au = $('#lst-auto'); if (au) au.onchange = () => { (P.terrain || (P.terrain = Object.assign({}, LS_TERRAIN))).on = au.checked; lsChanged(true); };
  const cc = $('#lst-clear'), cw = $('#lst-clearwhat');
  if (cc) cc.onchange = () => { P.clear = cc.checked ? (cw ? cw.value : 'standins') : ''; lsChanged(true); };
  if (cw) cw.onchange = () => { P.clear = cw.value; if (cc) cc.checked = true; lsChanged(true); };
  if (LM.stageOpen === 0) lstClearCount();
  const m0 = $('#lst-more0'); if (m0) m0.onclick = () => { LM.more0 = !LM.more0; renderWside(); };
  root.querySelectorAll('[data-make]').forEach(b => b.onclick = () => lstMake(+b.dataset.make, b));
  lstMadeBind(root);
  root.querySelectorAll('.lst-tools [data-add="town"], .lst-tools [data-add="castle"]').forEach(b => {
    b.title = 'Draw its limits on the map';
    b.onclick = () => lsStart(b.dataset.add);
  });
  root.querySelectorAll('[data-preview]').forEach(b => b.onclick = e => { e.stopPropagation(); lstPreview(+b.dataset.preview); });
  root.querySelectorAll('[data-keep]').forEach(b => b.onclick = () => lstKeep(+b.dataset.keep));
  root.querySelectorAll('[data-drop]').forEach(b => b.onclick = () => lstDrop(+b.dataset.drop, b));
  root.querySelectorAll('[data-retry]').forEach(b => b.onclick = () => lstRetry(+b.dataset.retry, b));
  root.querySelectorAll('[data-ins]').forEach(c => c.onchange = () => { LM.ins[c.dataset.ins] = c.checked; renderWside(); });
  const rm = $('#lst-rooms'); if (rm) rm.onchange = () => { LM.ins.rooms = rm.value; };
  const selL = P.layers[LM.sel];
  const ps = $('#lst-psize'); if (ps && selL) ps.onchange = () => {
    // (the size picked: the marker grown or shrunk to it round its middle)
    // (a marker grown or shrunk to it; an outline you drew stays as drawn, only the castle's size changes)
    if ((selL.p || {}).marker){
      const M = lsMarkerOf(selL), want = LS_MARK_R[selL.kind][ps.value], k = want / (M.r || want);
      selL.pts = selL.pts.map(p => [Math.round(M.x + (p[0] - M.x) * k), Math.round(M.y + (p[1] - M.y) * k)]);
    }
    if (selL.kind === 'castle') selL.p.size = ps.value;
    lsChanged(true);
  };
  const pl = $('#lst-plike'); if (pl && selL) pl.onchange = () => { if (selL.kind === 'town') selL.p.culture = pl.value; else selL.p.style = pl.value; lsChanged(true); };
  const ms = root.querySelector('.lst-more-set'); if (ms) ms.ontoggle = () => { LM.moreSet = ms.open; };
  if (P.layers.some(L => L.kind === 'castle') && !LM.csStyles && !LM.csAsked && typeof csStyles === 'function') csStyles().then(s => { if (s && s.length) renderWside(); });
}

// ----- making a stage, keeping it, trying again, dropping it
async function lstMake(n, btn){
  if (!await needProject()) return;
  if (lstStage() || LM.running) return;
  if (n === 0){ const lb = await lstLandBack(btn); if (!lb){ renderWside(); return; } LM.landBack = lb === 'back'; }
  const d0 = await lstDepth();
  let ok = false;
  try {
    LM.running = {n, t: 'Working…'};
    ok = n === 0 ? await lstMakeLand(btn) : n === 1 ? await lstMakePlaces(btn) : await lstMakeInsides(btn);
  } catch (e){ toast(e.message, true); }
  finally { LM.running = null; }
  const d1 = await lstDepth();
  if (d1 > d0){
    if (d1 - d0 > 1){ try { await post('/api/fold', {n: d1 - d0, note: LST_NOTE[n]}); } catch (e){} }
    if (n === 0){
      // (no stage to keep or drop: the shapes stay on the map, to change and make again)
      let id = 0; try { const lg = (await api('/api/project')).log || []; id = lg.length ? lg[lg.length - 1].id : 0; } catch (e){}
      LM.plan.made = {id, d0, d1: d0 + 1, cells: LM.stageCells || [], sig: lstLandSig()};
      LM.stageCells = null;
    } else {
      LM.plan.stage = {n, d0, d1: d0 + 1};
      LM.plan.stageCells = LM.stageCells || [];
    }
    await lstSave();
  } else if (ok !== false) toast('Nothing was made.');
  renderWside(); drawMap();
}
// (Make land again: the last Make land still in the mod is taken back first, so nothing stacks. The same asked again
// is rolled anew. False: it could not be taken back, and why was said)
async function lstLandBack(btn){
  const P = LM.plan, M = P.made;
  if (!M) return true;
  if (M.sig && M.sig === lstLandSig()){
    P.seed = (P.seed || 1) + 1;
    for (const L of lstCliffs()) (L.p || (L.p = {})).seed = (L.p.seed || 1) + 1;
  }
  const now = new Set(lstLandCells().concat(lstCliffCells()));
  if (!(M.cells || []).some(k => now.has(k))) return true;
  let lg; try { lg = (await api('/api/project')).log || []; } catch (e){ return true; }
  const e = M.id ? lg.find(e => e.id === M.id) : lg.filter(e => e.text === LST_NOTE[0]).pop();
  if (!e || !e.can_undo || e.undone) return true;
  btn.disabled = true; btn.innerHTML = '<span class="spin"></span>Taking the last one back…';
  try {
    // (the last change of all: a plain Undo. With changes made since, or the app closed since: its row alone)
    if (lg[lg.length - 1].id === e.id && await lstDepth() === M.d1) await post('/api/undo', {to: M.d0});
    else await post('/api/undo_entry', {id: e.id, only: true});
  } catch (err){ toast(err.message, true); return false; }
  P.made = null;
  return 'back';
}
async function lstMakeLand(btn){
  // (kept land an Undo took back is kept no more: read off the mod's own land before each Make)
  await lmLoad(true, true);
  if (LM.data && LM.data.own && LM.plan.kept) LM.plan.kept = LM.plan.kept.filter(k => LM.data.own[k]);
  const cells = lstLandCells(), cliffs = lstCliffs();
  if (!cells.length && !cliffs.length) return false;
  const P = LM.plan;
  const layers = P.layers.filter(L => lstOf(L) === 0);
  const send = Object.assign({}, P, {layers, start: LM.landBack ? 'now' : '', kept: [], protect: Object.assign({}, P.protect || {}, {fresh: false}), clear: lstClear()});
  btn.disabled = true; btn.textContent = `Making ${cells.length} cells…`; if (LM.running) LM.running.t = btn.textContent;
  await lmKeepBefore('the land');
  const poll = setInterval(async () => {
    let p; try { p = await api('/api/land/progress'); } catch (e){ return; }
    if (!p || !p.on) return;
    const pct = Math.round(p.frac * 100), b = $('#ls-apply');
    if (LM.running) LM.running.t = `${p.what}… ${pct}%`; if (b){ b.disabled = true; b.textContent = `${p.what}… ${pct}%`; b.style.background = `linear-gradient(90deg, var(--gold) ${pct}%, transparent ${pct}%)`; }
  }, 600);
  try {
    const r = cells.length ? await post('/api/land/plan/apply', {cells, plan: send}) : {cells: 0};
    LM.stageCells = [...new Set(cells.concat(lstCliffCells()))];
    // (the drawn cliffs, on the land just made: the same one Undo)
    let cr = 0;
    for (const L of cliffs){
      const p = L.p || {}, b = $('#ls-apply');
      if (b){ b.textContent = 'Laying the cliff…'; b.style.background = ''; }
      try {
        const c = await post('/api/land/cliff', {pts: L.pts, side: p.side || 0, height: p.height || 600, amount: p.amount != null ? p.amount : 1, like: L.like || '', pieces: [], raise: !!p.raise, seed: p.seed || 1, clad: p.clad !== 0});
        cr += c.rocks || 0;
        if (!c.rocks) toast(c.why ? `No cliff laid: ${c.why}.` : 'No cliff laid.', true);
      } catch (e){ toast(e.message, true); }
    }
    if (!cells.length){ if (cr) toast(`Laid the cliff: ${cr} rocks.`); LM.clearSig = ''; clearInterval(poll); await lstReload(); return true; }
    if (cr) r.cliff = cr;
    const cl = r.cleared || {};
    const cv_ = r.cover || {};
    toast(`Made the land in ${r.cells} cell${r.cells === 1 ? '' : 's'}${cv_.covers ? `, ${cv_.covers} cover${cv_.covers === 1 ? '' : 's'} (${cv_.laid} laid${(cv_.like || []).length ? ', like ' + [...new Set(cv_.like)].map(lsRegionName).join(', ') : ''})` : ''}${cl.removed ? `, ${cl.removed} objects cleared${cl.replaced ? ` (${cl.replaced} real trees and rocks in their place)` : ''}` : ''}${r.rocks || cr ? `, ${(r.rocks || 0) + cr} rocks` : ''}${r.plants ? `, ${r.plants} plants` : ''}.${r.clad_pending ? ' Its cliff rocks are still being learned: make it again when that is done.' : ''}`, !!r.clad_pending);
    LM.clearSig = '';
  } finally { clearInterval(poll); }
  await lstReload();
  return true;
}
async function lstMakePlaces(btn){
  const todo = lstPlacesTodo();
  if (!todo.length) return false;
  let now = '';
  const label = t => { now = t; if (LM.running) LM.running.t = t; const b = $('#lst-make1') || btn; if (b){ b.disabled = true; b.innerHTML = `<span class="spin"></span>${esc(t)}`; } };
  // (the step and how far it has got, on this button: a castle's 2 minutes said only "Building the castle…" here, its
  // bar on the castle's own panel, the user's "unclear progress bars", 2026-11-09)
  const tick = setInterval(async () => {
    let p = null;
    for (const u of ['/api/castle/progress', '/api/town/progress']){ try { const q = await api(u); if (q && q.on){ p = q; break; } } catch (e){} }
    const b = $('#lst-make1');
    if (b && p){ const pct = Math.round(p.frac * 100); b.innerHTML = `<span class="spin"></span>${esc(now.replace(/…$/, ''))}: ${esc(p.what)}… ${pct}%`; b.style.background = `linear-gradient(90deg, color-mix(in srgb, var(--gold) 35%, transparent) ${pct}%, transparent ${pct}%)`; }
  }, 700);
  try { return await lstMakePlacesRun(btn, todo, label); } finally { clearInterval(tick); }
}
async function lstMakePlacesRun(btn, todo, label){
  // roads first: their beds cut and painted on the land as it is
  const roads = todo.filter(L => L.kind === 'road');
  if (roads.length){
    label('Laying the roads…');
    const cells = [...new Set(roads.flatMap(L => lsRoadCells(L)))];
    const P = LM.plan;
    await post('/api/land/plan/apply', {cells, plan: Object.assign({}, P, {layers: roads, start: 'now', kept: P.kept || [], terrain: Object.assign({}, P.terrain || {}, {on: false}),
      protect: Object.assign({}, P.protect || {}, {fresh: false})})});
  }
  // the towns, outsides only: their interiors and people wait for the third stage
  // (a marker fitted to the land under it first: rays out from its middle stop at the shore and steep ground)
  const fit = async L => {
    if (!(L.p || {}).marker) return;
    label('Fitting ' + (L.p.name || 'the ' + lsSizeOf(L)) + ' to the land…');
    const M = lsMarkerOf(L);
    // (kept beside the marker, never over it: the circle stays as drawn, and the same circle fits the same way each time)
    try { const r = await post('/api/land/fit', {x: M.x, y: M.y, r: M.r}); if (r.outline && r.outline.length >= 3) L._fit = r.outline; } catch (e){}
  };
  // (each one tried, whatever the one before did, and what was left out said at the end: the castle was skipped
  // without a word, the user's "why does it just seem to stop and not do everything it's supposed to", 2026-11-09)
  const left = [], failed = [], joined = [];
  const nameOf = L => L.p.name || L.name || (L.kind === 'castle' ? 'the castle' : 'the ' + lsSizeOf(L));
  // (a castle inside a town's outline first, so the town is planned round it: its streets and houses keep off what
  // stands; one at the town's edge after, to stand on the town's wall. The user's "a castle there, with a city built
  // around", 2026-11-09)
  const towns_ = todo.filter(L => L.kind === 'town');
  // (and one beside a town, or in its edge: built first too, and the town's wall planned onto the castle's, one ring
  // between them. Built after, the castle was slid at the town's wall and kept its own whole ring a lane away, the
  // town's wall run through it: the user, 2026-11-11, "arent the walls supposed to meld")
  const inTown = L => { const M = lsMarkerOf(L); return towns_.some(T => lsInPoly(T.pts, M.x, M.y)) || (typeof csTownsOf === 'function' && csTownsOf(L).some(T => towns_.includes(T))); };
  const castleFirst = todo.filter(L => L.kind === 'castle' && inTown(L));
  // (a town previewed beside a castle is built with the wall the preview showed: its line goes with the build)
  for (const L of towns_){
    const Tn = LM.towns && LM.towns[L.id], W_ = Tn && Tn.plan && Tn.plan.walls;
    L._ring = (W_ && W_.outline && W_.outline.length >= 4 && Tn.key === lsTownKey(L) && typeof csCastlesOf === 'function' && csCastlesOf(L).length) ? W_.outline : null;
  }
  // (what stands already, asked of the mod before anything is built: a castle built first inside a city made the city
  // read as standing, and the city was left out, lab 2026-11-09)
  const stood = new Map();
  for (const L of todo) if (L.kind === 'town' || L.kind === 'castle') stood.set(L, await lsBuiltAt(L));
  const makeCastle = async L => {
    if (stood.get(L)){ L.p.built = 'yes'; left.push(nameOf(L)); return; }
    await fit(L);
    label('Building ' + nameOf(L) + '…');
    if (typeof csMake === 'function' && await csMake(L)) L.p.built = 'yes'; else failed.push(nameOf(L));
  };
  for (const L of castleFirst) await makeCastle(L);
  LM.laterMake = true;
  try {
    for (const L of todo.filter(L => L.kind === 'town')){
      if (stood.get(L)){ L.p.built = 'yes'; left.push(nameOf(L)); continue; }
      await fit(L);
      label('Building ' + nameOf(L) + '…');
      if (await lsMakeTown(L, '#lst-make1')) L.p.built = 'yes'; else failed.push(nameOf(L));
    }
  } finally { LM.laterMake = false; }
  for (const L of todo.filter(L => L.kind === 'castle' && !castleFirst.includes(L))) await makeCastle(L);
  if (left.length || failed.length || joined.length) setTimeout(() => toast([joined.length ? `${joined.join(', ')} built against the town wall beside it, sharing it.` : '', left.length ? `Left as built already: ${left.join(', ')}.` : '', failed.length ? `Not built: ${failed.join(', ')} (the message before says why).` : ''].filter(Boolean).join(' '), !!failed.length), 2500);
  for (const L of todo.filter(L => (L.kind === 'farm' || L.kind === 'orchard') && !(L.p || {}).proposed)){ label('Laying a field…'); await lsLayField(L, null); }
  const rest = lsPlacesToBuild(LM.plan).filter(L => L.kind !== 'dungeon');
  if (rest.length){ label('Laying the small places…'); await lsBuildDungeons(rest, null); }
  await lstLater();
  await lstReload();
  return true;
}
async function lstMakeInsides(btn){
  const I = LM.ins || {};
  const label = t => { if (LM.running) LM.running.t = t; const b = $('#lst-make2') || btn; if (b){ b.disabled = true; b.innerHTML = `<span class="spin"></span>${esc(t)}`; } };
  const said = [];
  if ((I.interiors || I.people) && (LM.later || []).length){
    label('Making the interiors…');
    const r = await post('/api/town/insides', {interiors: !!I.interiors, people: !!I.people, rooms: I.rooms || 'furnished', reseed: LM.reseed || 0});
    if (r.learning) throw new Error('Still learning ' + r.learning.join(', ') + ': try again in a minute.');
    if (r.interiors) said.push(`${r.interiors} interiors`);
    if (r.people) said.push(`${r.people} people in the towns`);
  }
  if (I.dungeons){
    const ds = lstDungeonsTodo();
    if (ds.length){ label('Building the dungeons…'); await lsBuildDungeons(ds, null); }
  }
  if (I.people){
    label('Bringing in people and creatures…');
    const on = LM.plan.layers.filter(L => L.on !== false), Q = LM.plan.places || {};
    try {
      const r = await post('/api/land/folk', {cells: LM.data.marks, seed: 1 + Math.floor(Math.random() * 99999), culture: Q.culture || '',
        roads: on.filter(L => L.kind === 'road').map(L => L.pts), towns: on.filter(L => L.kind === 'town').map(L => L.pts),
        camps: on.filter(L => L.kind === 'small' && (L.p || {}).what === 'camp' && (L.p || {}).built).map(L => L.pts[0])});
      if (r.people || r.creatures) said.push(`${r.people + r.creatures} people and creatures outdoors`);
    } catch (e){ toast(e.message, true); }
  }
  if (I.quests){
    label('Writing the rumours…');
    try {
      const r = await post('/api/land/rumours', {cells: LM.data.marks, seed: 1 + Math.floor(Math.random() * 99999)});
      if (r.places) said.push(`${r.lines} lines of rumour${r.quests ? `, ${r.quests} quests` : ''}`);
    } catch (e){ toast(e.message, true); }
  }
  if (said.length) toast(`Made ${said.join(', ')}. Look them over, then Keep, Try again or Drop.`);
  await lstLater();
  await lstReload();
  return true;
}
// (one place planned and drawn: its plan comes in from the planner the old panel used, kept until the place changes)
async function lstPreview(i){
  const L = LM.plan.layers[i]; if (!L) return;
  LM.sel = i;
  // (a marker fitted to the land first, as Make places does, so the preview is what will be built)
  if ((L.p || {}).marker && L.kind === 'town'){
    const M = lsMarkerOf(L);
    try { const r = await post('/api/land/fit', {x: M.x, y: M.y, r: M.r}); if (r.outline && r.outline.length >= 3) L._fit = r.outline; } catch (e){}
  }
  // (a town and the castle beside it are one ring: the castle planned first, the town's wall onto it, so the preview is
  // what Make places builds)
  const town1 = async T => {
    if (LM.towns) delete LM.towns[T.id];
    LM.towns = LM.towns || {}; LM.towns[T.id] = {key: '', busy: true};
    renderWside();
    LM.previewOnly = T.id;
    try { await lsTownsOnce(); } catch (e){ toast(e.message, true); } finally { LM.previewOnly = null; }
  };
  const castle1 = async (C, fresh) => {
    LM.castles = LM.castles || {};
    if (!fresh && LM.castles[C.id] && LM.castles[C.id].plan && LM.castles[C.id].key === csKey(C)) return;
    delete LM.castles[C.id]; LM.castles[C.id] = {key: '', busy: true};
    renderWside();
    LM.previewOnly = C.id;
    try { await csPlans(); } catch (e){ toast(e.message, true); } finally { LM.previewOnly = null; }
  };
  if (L.kind === 'town'){
    for (const C of csCastlesOf(L)) if (!(C.p || {}).built) await castle1(C, false);
    await town1(L);
  } else {
    await castle1(L, true);
    for (const T of csTownsOf(L)) if (LM.towns && LM.towns[T.id] && LM.towns[T.id].plan && !(T.p || {}).built) await town1(T);
  }
  const T = (L.kind === 'castle' ? LM.castles : LM.towns)[L.id] || {};
  if (T.err) toast(T.err, true);
  drawMap(); renderWside();
}
async function lstLater(){ try { LM.later = (await post('/api/town/insides', {look: true})).towns || []; } catch (e){ LM.later = []; } }
async function lstReload(){
  LM.prev = null; LM.prevData = null;
  W.lands = {}; if (typeof v3LandsReload === 'function') v3LandsReload();
  await afterChange(); await lmLoad(true, true);
  await lstMade();
  await lmReloadObjects();
  await loadAround(Math.floor(W.cam.x / CELL), Math.floor(W.cam.y / CELL));
  lmFlowSoon(); drawMap();
  if (typeof v3Refresh === 'function' && V3.on) v3Refresh();
}
async function lstKeep(n){
  const P = LM.plan, st = lstStage(); if (!st || st.n !== n) return;
  if (n === 0){
    // (the land made is the start of the next Make; its shapes leave the map: the user, "these shapes should just be gone")
    P.kept = [...new Set((P.kept || []).concat(P.stageCells || LM.stageCells || []))];
    P.layers = P.layers.filter(L => lstOf(L) !== 0 || !L.pts || !L.pts.length || L.on === false);
  } else if (n === 1){
    // (a town or castle built before a place kept its "built" (test6 and before): asked of the mod, so Keep takes it off
    // the map too; the user's two towns stayed on after Keep, 2026-11-09)
    for (const L of P.layers) if ((L.kind === 'town' || L.kind === 'castle') && L.on !== false && !(L.p || {}).built && await lsBuiltAt(L)) L.p.built = 'yes';
    // (what was made goes off the map; the dungeon markers stay for the third stage)
    // (only what was built: a castle the Make left unbuilt stays drawn, to make next; Keep took it off the map too)
    P.layers = P.layers.filter(L => !(lstOf(L) === 1 && L.kind !== 'dungeon' && L.on !== false && ((L.p || {}).built || !['town', 'castle'].includes(L.kind))));
  } else {
    P.layers = P.layers.filter(L => !(L.kind === 'dungeon' && (L.p || {}).built));
  }
  P.stage = null; delete P.stageCells; LM.stageCells = null; LM.sel = null; LM.reseed = 0;
  lsHistNote();                   // (the shapes Keep takes off the map come back with ↶)
  LM.towns = {}; if (LM.castles) LM.castles = {};
  await lstSave();
  if (n < 2) LM.stageOpen = n + 1;
  toast(['Kept the land.', 'Kept the places.', 'Kept the insides.'][n]);
  renderWside(); drawMap();
}
// (undo back to before the stage; with changes made since, only on a yes)
async function lstUndoStage(st){
  const now = await lstDepth();
  if (now < st.d1){
    // (the app was closed since: the stage's row in My mod is taken back by itself, later changes left alone. Without
    // this, Try again after a restart undid nothing and made nothing)
    try {
      const rows = ((await api('/api/project')).log || []).filter(e => e.text === LST_NOTE[st.n] && e.can_undo);
      if (rows.length) await post('/api/undo_entry', {id: Math.max(...rows.map(e => e.id)), only: true});
    } catch (e){ toast(e.message, true); return false; }
    return true;
  }
  if (now > st.d1 && !confirm(`You've made ${now - st.d1} change${now - st.d1 === 1 ? '' : 's'} since. Take ${now - st.d1 === 1 ? 'it' : 'them'} back too?`)) return false;
  await post('/api/undo', {to: st.d0});
  return true;
}
async function lstDrop(n, btn){
  const st = lstStage(); if (!st || st.n !== n) return;
  if (btn){ btn.disabled = true; btn.innerHTML = '<span class="spin"></span>Dropping…'; }
  if (!await lstUndoStage(st)){ renderWside(); return false; }
  // (a Land made and dropped: its built places on the map are unbuilt again)
  if (n === 1){
    // (each town and castle asked of the mod after the undo: one built before this Make stays built. Unmarking them all
    // made the next Make build the user's city a second time, 2026-11-09)
    for (const L of LM.plan.layers){
      if (lstOf(L) !== 1 || L.kind === 'dungeon' || !L.p) continue;
      if (L.kind === 'town' || L.kind === 'castle') L.p.built = (await lsBuiltAt(L)) ? 'yes' : '';
      else delete L.p.built;
    }
  }
  if (n === 2) for (const L of LM.plan.layers) if (L.kind === 'dungeon' && L.p) delete L.p.built;
  LM.plan.stage = null; delete LM.plan.stageCells;
  if (LM.towns) for (const T of Object.values(LM.towns)) if (T) T.built = false;
  await lstSave();
  if (typeof refreshAfterEdits === 'function') await refreshAfterEdits();
  await lstLater();
  await lstReload();
  renderWside();
  return true;
}
async function lstRetry(n, btn){
  if (!await lstDrop(n, btn)) return;
  const P = LM.plan;
  // (rolled anew: the land's seed, each town's and castle's, the insides' own)
  if (n === 0) P.seed = (P.seed || 1) + 1;
  if (n === 1) for (const L of P.layers) if ((L.kind === 'town' || L.kind === 'castle') && L.p) L.p.seed = 1 + Math.floor(Math.random() * 99999);
  if (n === 2) LM.reseed = (LM.reseed || 0) + 1;
  if (n === 1){ LM.towns = {}; lsTownsSoon(); }
  await lstSave();
  renderWside();
  const b = document.querySelector(`[data-make="${n}"]`);
  await lstMake(n, b || {disabled: false, textContent: ''});
}
