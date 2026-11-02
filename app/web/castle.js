// Keeps and castles on the Land panel (castle.py): a 🏰 Castle shape drawn like a town, planned in a culture's way and
// drawn on the map before anything is built; Make it builds it, rooms and all, as one Undo.
// (the user, 2026-11-01: "better keep and castle generation, with rooms inside towers, keeps and curtain walls")
const CS_SIZES = [['small', 'Small'], ['medium', 'Medium'], ['large', 'Large'], ['drawn', 'As drawn']];
const CS_ROOMS = [['none', 'None'], ['shells', 'Empty shells'], ['furnished', 'Furnished']];
const CS_COL = {wall: '#8a7a66', corner: '#5a4a3a', tower: '#5a4a3a', bigtower: '#4a3a2a', gate: '#4caf50', end: '#4caf50', keep: '#b0623a'};

async function csStyles(){
  if (!LM.csStyles && !LM.csAsked){
    LM.csAsked = true;
    try { const r = await api('/api/castle/styles'); if (!r.learning) LM.csStyles = r.styles; } catch (e){ LM.csStyles = []; }
    setTimeout(() => { LM.csAsked = false; }, 5000);
  }
  return LM.csStyles;
}

function csHtml(sel){
  const p = sel.p || {}, C = (LM.castles || {})[sel.id], st = LM.csStyles || [];
  // (asked once at a time, and drawn again only once the list is in: drawn again on every answer, a still-learning one
  // asked again at once and the page spun)
  if (!LM.csStyles && !LM.csAsked) csStyles().then(s => { if (s && LM.plan && LM.plan.layers[LM.sel] === sel) renderWside(); });
  let info = '';
  if (C && C.err) info = `<div class="msg warn" style="font-size:11.5px">${esc(C.err)}</div>`;
  else if (C && C.learning) info = `<div class="msg" style="font-size:11.5px"><span class="spin"></span>Learning ${esc(C.learning.join(', '))} first (once)…</div>`;
  else if (!C || C.busy && !C.plan) info = '<div class="msg" style="font-size:11.5px"><span class="spin"></span>Planning…</div>';
  if (C && C.plan) info += csSummaryHtml(C.plan);
  const help = typeof guideLink === 'function' ? guideLink('shaping-the-land.md', 'Keeps and castles', 'How castles are made') : '';
  return `<div style="display:flex;align-items:center;gap:4px;font-size:12px"><b>Castle</b>${help}</div>
    <label title="Whose forts it is built like: their walls, towers and keep, and the rooms behind their doors">Like <select class="inp" id="cs-style">${(st.length ? st : [{id: 'Imperial', label: 'Imperial fort'}]).map(s => `<option value="${esc(s.id)}" ${(p.style || 'Imperial') === s.id ? 'selected' : ''} title="${esc((s.examples || []).join(', '))}">${esc(s.label)}</option>`).join('')}</select></label>
    <label title="How big its walls are, against the game's own of its kind. As drawn: the outline you drew">Size <select class="inp" id="cs-size">${CS_SIZES.map(([v, t]) => `<option value="${v}" ${(p.size || 'medium') === v ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
    <label title="Its name: its rooms are called after it. Blank: the one shown">Name <input class="inp" id="cs-name" value="${esc(p.name || '')}" placeholder="${esc((C && C.plan && C.plan.name) || '')}" maxlength="40"></label>
    <label title="What lies behind its doors. Shells: the rooms' walls, stairs and doors only, to furnish yourself. Furnished: the same, furnished by the Workshop">Rooms <select class="inp" id="cs-rooms">${CS_ROOMS.map(([v, t]) => `<option value="${v}" ${(p.rooms || 'furnished') === v ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
    <label title="Its people, cast as the game's own rooms of its kind have them (furnished rooms only)"><input type="checkbox" id="cs-ppl" ${(p.rooms || 'furnished') !== 'furnished' ? 'disabled' : ''} ${p.nopeople || (p.rooms || 'furnished') !== 'furnished' ? '' : 'checked'}> People</label>
    <div class="actions"><button class="btn sm" id="cs-reroll" title="Another layout of the same castle">🎲 Another</button>
      <button class="btn sm" id="cs-remove" title="Take away what Make it built here, rooms and all. What you added later and the ground stay. One Undo">✕ Remove</button>
      <button class="btn sm primary" id="cs-make" ${C && C.plan ? '' : 'disabled'} title="Build it as shown, its rooms behind its doors. One Undo takes it back">🏰 Make it</button></div>${info}`;
}

function csSummaryHtml(pl){
  const f = pl.fig || {}, g = pl.game || {};
  const ws = f.wall_size && f.wall_size.length ? `${f.wall_size[0]} × ${f.wall_size[1]}` : 'none';
  const gws = g.wall_size && g.wall_size[0] ? `${g.wall_size[0]} × ${g.wall_size[1]}` : 'none';
  const row = (k, a, b) => `<tr><td>${k}</td><td>${a}</td><td style="opacity:.7">${b == null ? '–' : b}</td></tr>`;
  return `<details class="cs-sum" ${LM.csOpen ? 'open' : ''}><summary title="This castle beside the game's own of its kind (their middle values)">${esc(pl.name)}: ${f.interiors} rooms, ${f.towers} towers</summary>
    <table style="font-size:11.5px;width:100%"><tr><td></td><td>This</td><td style="opacity:.7">Game</td></tr>
    ${row('Walls', ws, gws)}${row('Towers', f.towers, g.towers)}${row('Rooms', f.interiors, g.interiors)}${row('Doors out', f.doors_out, g.doors_out)}</table>
    <div style="font-size:11.5px;margin-top:4px">${(pl.rooms || []).map(r => esc(r.name)).join('<br>')}</div>
    ${(pl.faults || []).length ? `<div class="msg warn" style="font-size:11.5px">${pl.faults.map(esc).join('<br>')}</div>` : ''}</details>`;
}

function csBind(){
  const P = LM.plan, sel = P && P.layers[LM.sel]; if (!sel || sel.kind !== 'castle') return;
  const s = $('#cs-style'); if (s) s.onchange = () => { sel.p.style = s.value; lsChanged(true); };
  const z = $('#cs-size'); if (z) z.onchange = () => { sel.p.size = z.value; lsChanged(true); };
  const nm = $('#cs-name'); if (nm) nm.onchange = () => { sel.p.name = nm.value.trim(); lsChanged(true); };
  const rm_ = $('#cs-rooms'); if (rm_) rm_.onchange = () => { sel.p.rooms = rm_.value; lsChanged(true); };
  const pp = $('#cs-ppl'); if (pp) pp.onchange = () => { sel.p.nopeople = !pp.checked; lsChanged(false); };
  const sm = document.querySelector('.cs-sum'); if (sm) sm.ontoggle = () => { LM.csOpen = sm.open; };
  const r = $('#cs-reroll'); if (r) r.onclick = () => { sel.p.seed = ((sel.p.seed || 1) % 100000) + 1 + Math.floor(Math.random() * 1000); lsChanged(true); };
  const rm = $('#cs-remove'); if (rm) rm.onclick = async () => {
    if (!await needProject()) return;
    const C = (LM.castles || {})[sel.id], out = (C && C.plan && C.plan.preview && C.plan.preview.outline.length) ? C.plan.preview.outline : sel.pts;
    let n; try { n = await post('/api/castle/remove', {outline: out, look: true}); } catch (e){ return toast(e.message, true); }
    if (!confirm(`Remove ${n.name}: ${n.things} things it built and its ${n.interiors} rooms? What you added later and the ground stay. One Undo brings it back.`)) return;
    try {
      const r_ = await post('/api/castle/remove', {outline: out});
      toast(`Removed ${r_.name}: ${r_.things} things and ${r_.interiors} rooms.`);
      await csShow();
    } catch (e){ toast(e.message, true); }
  };
  const mk = $('#cs-make'); if (mk) mk.onclick = () => csMake(sel);
  const C = (LM.castles || {})[sel.id];
  if (!C || C.key !== csKey(sel)) csSoon();
}

function csKey(L){ return JSON.stringify([L.pts, L.p.style || 'Imperial', L.p.size || 'medium', L.p.seed || 1, L.p.name || '']); }
function csSoon(){ clearTimeout(LM.csT); LM.csT = setTimeout(csPlans, 350); }
async function csPlans(){
  if (LM.csBusy){ LM.csAgain = true; return; }
  LM.csBusy = true;
  try {
    const P = LM.plan; if (!P) return;
    LM.castles = LM.castles || {};
    for (const L of P.layers){
      if (L.kind !== 'castle' || !L.pts || L.pts.length < 3) continue;
      const key = csKey(L), C = LM.castles[L.id];
      if (C && C.key === key) continue;
      LM.castles[L.id] = {key, plan: C && C.plan, busy: true};
      try {
        let plan;
        for (;;){
          plan = await post('/api/castle/plan', {outline: L.pts, style: L.p.style || 'Imperial', size: L.p.size || 'medium', seed: L.p.seed || 1, name: L.p.name || ''});
          if (!plan.learning || LM.castles[L.id].key !== key) break;
          LM.castles[L.id].learning = plan.learning;
          if (P.layers[LM.sel] === L && PNL.isShown('world', 'land')) renderWside();
          await new Promise(res => setTimeout(res, 2500));
        }
        if (LM.castles[L.id].key === key && !plan.learning) LM.castles[L.id] = {key, plan};
      } catch (e){ if (LM.castles[L.id].key === key) LM.castles[L.id] = {key, err: e.message}; }
      drawMap();
      if (PNL.isShown('world', 'land') && P.layers[LM.sel] === L) renderWside();
    }
  } finally {
    LM.csBusy = false;
    if (LM.csAgain){ LM.csAgain = false; csSoon(); }
  }
}

function csDraw(g, P){
  for (const L of P.layers){
    const C = L.kind === 'castle' && L.on !== false && LM.castles && LM.castles[L.id];
    if (!C || !C.plan || !C.plan.preview) continue;
    const z = W.cam.z, pv = C.plan.preview;
    for (const [k, cs] of pv.pieces){
      g.beginPath(); cs.forEach((p, i) => { const [sx, sy] = toScreen(p[0], p[1]); if (i) g.lineTo(sx, sy); else g.moveTo(sx, sy); });
      g.closePath(); g.fillStyle = CS_COL[k] || '#8a7a66'; g.fill();
    }
    if (z > 0.02) for (const d of pv.doors){
      const [dx, dy] = toScreen(d[0], d[1]); g.fillStyle = '#ff3c3c'; g.beginPath(); g.arc(dx, dy, Math.max(1.5, Math.min(4, 40 * z)), 0, Math.PI * 2); g.fill();
    }
    if (z > 0.04 && C.plan.name){
      const xs = pv.outline.length ? pv.outline : L.pts, cx = xs.reduce((a, p) => a + p[0], 0) / xs.length, cy = xs.reduce((a, p) => a + p[1], 0) / xs.length;
      const [tx, ty] = toScreen(cx, cy); g.font = '12px sans-serif'; g.fillStyle = 'rgba(255,240,210,0.95)'; g.textAlign = 'center'; g.fillText(C.plan.name, tx, ty); g.textAlign = 'start';
    }
  }
}

async function csShow(){
  if (typeof afterChange === 'function') await afterChange();
  for (const k of Object.keys(W.cells)) if (W.cells[k] && W.cells[k].exists) await worldReloadCell(k);
  W.lands = {}; if (typeof v3LandsReload === 'function') v3LandsReload();
  drawMap(); renderWside(); if (typeof v3Refresh === 'function' && V3.on) v3Refresh();
}

async function csMake(sel){
  if (!await needProject()) return false;
  const mk = $('#cs-make');
  const bar = (what, pct) => {
    const b = $('#cs-make'); if (!b) return;
    b.disabled = true; b.textContent = `${what}… ${pct}%`; b.title = 'Building: ' + what;
    b.style.background = `linear-gradient(90deg, var(--gold) ${pct}%, transparent ${pct}%)`; b.classList.add('pbar');
  };
  if (mk){ mk.disabled = true; mk.innerHTML = '<span class="spin"></span>Building…'; }
  const poll = setInterval(async () => {
    let p; try { p = await api('/api/castle/progress'); } catch (e){ return; }
    if (p && p.on) bar(p.what, Math.round(p.frac * 100));
  }, 600);
  let ok = false;
  try {
    let r;
    try {
      r = await post('/api/castle/make', {outline: sel.pts, style: sel.p.style || 'Imperial', size: sel.p.size || 'medium', seed: sel.p.seed || 1,
        name: sel.p.name || '', people: !sel.p.nopeople, rooms: sel.p.rooms || 'furnished'});
    } finally { clearInterval(poll); }
    if (r.learning) throw new Error('Still learning ' + r.learning.join(', ') + ': try again in a minute.');
    toast(`Built ${esc(r.name)}: ${r.pieces} pieces outside, ${r.interiors} rooms${r.people ? `, ${r.people} people` : ''}. One Undo takes it back.`);
    ok = true;
    await csShow();
  } catch (e){ toast(e.message, true); }
  const b = $('#cs-make');
  if (b){ b.disabled = false; b.textContent = '🏰 Make it'; b.style.background = ''; b.title = 'Build it as shown, its rooms behind its doors. One Undo takes it back'; }
  return ok;
}
