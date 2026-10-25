// ---------- The Forge: a new weapon or armour piece with the numbers the game gives its type and material ----------
// (gearsurvey.py) Pick what it is and its material, or a new material between two of the game's; the Workshop
// fills in the game's typical numbers for that kind of piece, shows the game's own range beside each, and
// says when yours go beyond anything the game does (more than 15% past its range: 92% of the game's own
// pieces fall inside). The look is taken from one of the game's pieces of that kind; armour shows its weight
// class by the game's own rule. "Forge it" makes the record (items.create_item), one Undo.
const FG = {bg: null, opts: null, kind: 'weapon', type: null, mat: null, between: null, p: null, look: null, stats: {}, edited: {}, seq: 0};

async function forgeShow(start){
  if (FG.bg) FG.bg.remove();
  const bg = document.createElement('div'); bg.className = 'modal-bg'; FG.bg = bg;
  bg.innerHTML = `<div class="modal fg-win"><h2>⚒ Forge a weapon or armour</h2><div id="fg-body"><div class="msg"><span class="spin"></span>Reading the game's weapons and armour…</div></div>
    <div class="foot"><span class="msg" id="fg-msg" style="flex:1"></span><button class="btn" id="fg-close">Close</button><button class="btn primary" id="fg-go" disabled>⚒ Forge it</button></div></div>`;
  document.body.appendChild(bg);
  fgCss();
  bg.querySelector('#fg-close').onclick = () => { bg.remove(); FG.bg = null; };
  bg.querySelector('#fg-go').onclick = fgMake;
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
      <div class="msg" style="margin-top:8px;font-size:11.5px">The numbers start at what the game gives a piece of this type and material (the middle of its own pieces), with the game's lowest and highest beside them. Change any; the badge says when one goes more than 15% beyond the game's range for this material. Enchant it afterwards in its item window, as any item.</div>
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
    fgMsg(`Forged <b>${esc(FG.name)}</b> (${esc(r.id)}). <span class="lnk" id="fg-open">Open it</span> to enchant it or change its looks; place it from the Place panel like any item.`);
    const o = FG.bg.querySelector('#fg-open');
    if (o) o.onclick = () => { FG.bg.remove(); FG.bg = null; showView('browse'); openRecord(r.i, true); };
    FG.name = ''; FG.id = ''; FG.idEdited = false; FG.made = true;
    const nm = FG.bg.querySelector('#fg-name'), idb = FG.bg.querySelector('#fg-id'); if (nm) nm.value = ''; if (idb) idb.value = '';
    fgReady();
  } catch (e){ fgMsg(esc(e.message), true); }
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
  .fg-b{font-size:11.5px;white-space:nowrap}.fg-b.ok{color:var(--good,#8fbf7f)}.fg-b.high,.fg-b.low{color:var(--amber,#e0a050)}`;
  document.head.appendChild(c);
}
