// Fix-it tools: find the gaps in a place built from room pieces (open sides onto nothing, doorways that
// lead nowhere, missing ceilings), fix them one by one or all at once, and swap a piece for another
// that fits the same spot.
const FX = {cell: null, issues: [], panel: null, marks: null, all: false};

function fixitCss(){
  if ($('#fx-css')) return;
  const c = document.createElement('style'); c.id = 'fx-css';
  c.textContent = `
  #fx-panel{position:fixed;left:16px;bottom:16px;width:min(380px,calc(100vw - 32px));max-height:60vh;display:flex;flex-direction:column;background:var(--panel);border:1px solid var(--line2);border-radius:12px;box-shadow:0 12px 40px #000c;z-index:70}
  .pbody #fx-panel{position:static;width:auto;max-height:none;background:none;border:0;border-radius:0;box-shadow:none;margin:-14px -16px 0}
  .pbody #fx-panel #fx-x{display:none}
  .pbody #fx-panel .fx-list{overflow:visible}
  #fx-panel .fx-h{display:flex;align-items:center;gap:8px;padding:10px 12px;border-bottom:1px solid var(--line)}
  #fx-panel .fx-h b{flex:1}
  #fx-panel .fx-list{overflow:auto;padding:6px 10px 10px}
  #fx-panel .fx-i{border-bottom:1px solid var(--line);padding:8px 0}
  #fx-panel .fx-i:last-child{border:0}
  #fx-panel .fx-i .fx-t{display:flex;gap:6px;align-items:baseline}
  #fx-panel .fx-i .fx-t > span:not(.fx-kind){flex:1}
  .fx-kind{flex:none}
  #fx-panel .fx-acts{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
  .fx-kind{font-size:11px;padding:1px 6px;border-radius:9px;background:#5a2a20;color:#ffb39c}
  .fx-kind.ceiling{background:#2c3a52;color:#a9c6ff}
  .fx-kind.hole{background:#4a2a52;color:#e2b3ff}
  .fx-kind.joint{background:#4a3a1a;color:#ffd98a}
  .fx-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:8px;max-height:56vh;overflow:auto;margin:10px 0}
  .fx-grid button{background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:6px;color:var(--text);cursor:pointer;font:inherit;text-align:center}
  .fx-grid button:hover{border-color:var(--gold, #d9b26a)}
  .fx-grid small{display:block;color:var(--muted);font-size:11px;word-break:break-all}`;
  document.head.appendChild(c);
}

const FX_KIND = {gap: 'Gap', doorway: 'Doorway', ceiling: 'Ceiling', post: 'Post', hole: 'See-through', clip: 'Clips', zfight: 'Flush faces', joint: 'Not the game\'s way', stairend: 'Stair end', sunk: 'Post in a wall', backwall: 'Wall seen from behind', openpost: 'Posts in the open'};

async function fixitOpen(cell){
  fixitCss();
  FX.cell = cell;
  // in the World map it lives in its own panel (that you can move, dock or tab with others)
  const inPanel = typeof PNL !== 'undefined' && PNL.spaces.world && $('#world').classList.contains('on');
  if (inPanel){
    PNL.show('world', 'fixit');
    const body = PNL.body('world', 'fixit');
    if (!FX.panel || !body.contains(FX.panel)){ body.innerHTML = ''; FX.panel = document.createElement('div'); FX.panel.id = 'fx-panel'; body.appendChild(FX.panel); }
  } else if (!FX.panel){
    FX.panel = document.createElement('div'); FX.panel.id = 'fx-panel';
    document.body.appendChild(FX.panel);
  }
  FX.panel.innerHTML = '<div class="fx-h"><b>🔧 Finding gaps…</b></div><div class="fx-list"><span class="spin"></span></div>';
  try { const r = await api('/api/fixit/scan?cell=' + encodeURIComponent(cell) + (FX.all ? '&all=1' : '')); FX.issues = r.issues; FX.res = r; }
  catch (e){ FX.panel.innerHTML = `<div class="fx-h"><b>🔧 Gaps</b><button class="xbtn" id="fx-x">✕</button></div><div class="fx-list msg err">${esc(e.message)}</div>`; $('#fx-x').onclick = fixitClose; return; }
  fixitRender();
}

// this place's see-through spots per floor piece against the game's own places of the style
function fixitRate(r){
  if (!r.tiles) return '';
  const per10 = x => (10 * x).toFixed(1);
  const holes = FX.issues.filter(i => i.kind === 'hole').length + (r.hidden || 0);
  let s = `See-through spots: ${holes} in ${r.tiles} floor pieces (${per10(r.rate)} per 10).`;
  if (r.typical) s += ` The game's own ${esc(r.style || '')} places have ${per10(r.typical.per_tile.hole || 0)} per 10 (from ${r.typical.places} places)${r.hidden ? ', so this place is no worse than them' : r.rate > (r.typical.per_tile.hole || 0) ? ', so this place is gappier than they are' : ''}.`;
  else if (r.style) s += ` How gappy the game's own ${esc(r.style)} places are is being measured in the background; look again in a minute.`;
  // (the other kinds left out because the game's own places of the style show them as often: posts wanted
  // at a third of the tiles in the game's Gold Coast places, say; clips and z-fights only under "everything")
  const hk = r.hidden_kinds || {}, hkn = Object.values(hk).reduce((a, b) => a + b, 0);
  const kindName = {gap: 'gap', doorway: 'dead doorway', post: 'post wanted', ceiling: 'missing ceiling'};
  if (hkn) s += ` Also left out: ${Object.entries(hk).map(([k, n]) => `${n} ${kindName[k] || k}${n === 1 ? '' : 's'}`).join(', ')}, no more than the game's own places have.`;
  const lg = r.clashes_like_the_game ? Object.values(r.clashes_like_the_game).reduce((a, b) => a + b, 0) : 0;
  if (FX.all && lg) s += ` ${lg} overlapping or flush piece pairs are the kit's own joinery, as in the game's places, and are not listed.`;
  return `<div class="msg" style="margin-bottom:6px">${s}${r.hidden ? ` <b>${r.hidden}</b> left out of the list.` : ''}
    ${(r.hidden || hkn || FX.all) ? ` <a href="#" id="fx-everything">${FX.all ? 'Show only what\'s worse than the game\'s own' : 'Show everything'}</a>` : ''}</div>`;
}

function fixitRender(){
  const r = FX.res, n = FX.issues.length, fixable = FX.issues.filter(i => i.fixes.length).length;
  FX.panel.innerHTML = `<div class="fx-h"><b>🔧 ${n ? `${n} gap${n === 1 ? '' : 's'} found` : 'No gaps found'}</b>
      ${fixable ? `<button class="btn sm primary" id="fx-all" title="Close every gap that has a fix, in one step (one Undo takes it back)">Fix all</button>` : ''}
      <button class="btn sm" id="fx-again" title="Look again">↻</button><button class="xbtn" id="fx-x" title="Close">✕</button></div>
    <div class="fx-list">${r.note ? `<div class="msg">${esc(r.note)}</div>` : n > 1 ? '<div class="msg">Fixing one by one? Go from the top: posts and columns come first, and often close gaps further down the list. It looks again after each fix.</div>' : n ? '' : `<div class="msg">Checked ${r.tiles} floor pieces${r.style ? ' (' + esc(r.style) + ')' : ''}: every side is closed or carries on into another room${r.hidden ? '' : ', and looking round from inside, nothing shows through where pieces meet'}.</div>`}
      ${fixitRate(r)}
      ${FX.issues.map(i => `<div class="fx-i"><div class="fx-t"><span class="fx-kind ${i.kind}">${FX_KIND[i.kind] || i.kind}</span><span>${esc(i.text)}${i.side ? ` <span class="msg">(${{N: 'north', E: 'east', S: 'south', W: 'west'}[i.side]} side)</span>` : ''}</span></div>
        <div class="msg" style="word-break:break-all">${esc(i.id)}</div>
        <div class="fx-acts"><button class="btn sm" data-fxshow="${i.n}" title="Select the piece and look at the spot">⌖ Show</button>
          ${i.fixes.map((f, k) => `<button class="btn sm ${k === 0 ? 'primary' : ''}" data-fxfix="${i.n}:${k}">${esc(f.label)}</button>`).join('')}
          ${i.fixes.length ? '' : '<span class="msg">No piece of this style closes it: use the Fix-it pieces in Place → Suggested.</span>'}
          <button class="btn sm" data-fxvar="${i.n}" title="Other pieces of the style that fit this spot">↻ Other pieces</button></div></div>`).join('')}
      ${r.posts ? `<div class="msg" style="margin-top:6px;font-size:11.5px">${r.posts.places
        ? `In the game's own ${esc(r.style || '')} places, ${Math.round(100 * (r.posts.share || 0))}% of the corners have a post or column${(r.posts.share || 0) < 0.12 ? ', so gaps here are closed some other way first' : ''}.`
        : `No place in your game is built in ${esc(r.style || 'this style')}; most styles have a post at only about 1 corner in 20, so gaps here are closed some other way first.`}</div>` : ''}
      ${r.tiles ? `<div class="fx-i" style="border-top:1px solid var(--line);margin-top:6px;padding-top:8px"><div class="msg">Posts or columns standing where there's no corner, or several on one?</div>
        <div class="fx-acts"><button class="btn sm" id="fx-spare" title="Takes out the posts and columns your mod put here that close nothing (it looks round the whole place to be sure nothing shows through without them). One Undo puts them back.">🧹 Take out spare columns</button>
          ${r.door_frame ? `<button class="btn sm" id="fx-frames" title="For a place built before 2.2: stands the style's door frame (${esc(r.door_frame)}) in each doorway between rooms that's just a gap in the wall, then takes out the columns that were only covering the wall ends. One Undo takes it back.">🚪 Door frames in doorways</button>` : ''}</div></div>` : ''}</div>`;
  const fr = $('#fx-frames');
  if (fr) fr.onclick = async () => {
    if (!await needProject()) return;
    fr.disabled = true; fr.textContent = '🚪 Fitting door frames…';
    try {
      const m = await post('/api/fixit/doorframes', {cell: FX.cell});
      toast(m.frames ? `Put door frames in ${m.frames} doorway${m.frames === 1 ? '' : 's'}${m.removed ? ` and took out ${m.removed} column${m.removed === 1 ? '' : 's'}` : ''}. One Undo takes it back.` : 'Every doorway here has its frame already.');
      await fixitAfter();
    } catch (e){ toast(e.message, true); fr.disabled = false; fr.textContent = '🚪 Door frames in doorways'; }
  };
  $('#fx-x').onclick = fixitClose;
  const ev = $('#fx-everything');
  if (ev) ev.onclick = e => { e.preventDefault(); FX.all = !FX.all; fixitOpen(FX.cell); };
  const sp = $('#fx-spare');
  if (sp) sp.onclick = async () => {
    if (!await needProject()) return;
    sp.disabled = true; sp.textContent = '🧹 Looking round the place…';
    try {
      const m = await post('/api/fixit/spare', {cell: FX.cell});
      toast(m.removed ? `Took out ${m.removed} spare column${m.removed === 1 ? '' : 's'}. Undo puts ${m.removed === 1 ? 'it' : 'them'} back.` : 'Every post and column here closes something, so they all stay.');
      await fixitAfter();
    } catch (e){ toast(e.message, true); sp.disabled = false; sp.textContent = '🧹 Take out spare columns'; }
  };
  $('#fx-again').onclick = () => fixitOpen(FX.cell);
  const all = $('#fx-all');
  if (all) all.onclick = async () => {
    if (!await needProject()) return;
    all.disabled = true;
    try {
      const m = await post('/api/fixit/all', {cell: FX.cell});
      toast(`Closed ${m.changed.length} spot${m.changed.length === 1 ? '' : 's'}.${m.left ? ` ${m.left} left that need a hand.` : ''} One Undo takes it all back.`);
      await fixitAfter();
    } catch (e){ toast(e.message, true); all.disabled = false; }
  };
  FX.panel.querySelectorAll('[data-fxfix]').forEach(b => b.onclick = async () => {
    if (!await needProject()) return;
    const [n, k] = b.dataset.fxfix.split(':').map(Number);
    const i = FX.issues.find(x => x.n === n), f = i.fixes[k];
    b.disabled = true;
    try { await post('/api/fixit/apply', {cell: FX.cell, ops: f.ops, label: f.label}); toast('Fixed. Undo takes it back.'); await fixitAfter(); }
    catch (e){ toast(e.message, true); b.disabled = false; }
  });
  FX.panel.querySelectorAll('[data-fxshow]').forEach(b => b.onclick = () => fixitShow(FX.issues.find(x => x.n === +b.dataset.fxshow)));
  FX.panel.querySelectorAll('[data-fxvar]').forEach(b => b.onclick = () => { const i = FX.issues.find(x => x.n === +b.dataset.fxvar); fixitVariants(FX.cell, i.ref, i.id); });
  fixitMarks();
}

async function fixitAfter(){
  if (typeof worldReloadCell === 'function') await worldReloadCell(FX.cell);
  if (typeof afterChange === 'function') afterChange();
  if (typeof v3Refresh === 'function' && V3.on) v3Refresh();
  await fixitOpen(FX.cell);
}

function fixitClose(){
  if (FX.panel && FX.panel.closest('.pbody')){ PNL.close('world', 'fixit'); return; }
  if (FX.panel){ FX.panel.remove(); FX.panel = null; }
  FX.issues = [];
  fixitMarks();
}

// red markers in the 3D view where the gaps are (blue for ceilings)
function fixitMarks(){
  if (typeof THREE === 'undefined' || !V3.scene) return;
  const T = THREE;
  if (FX.marks){ V3.scene.remove(FX.marks); FX.marks.children.forEach(c => c.geometry && c.geometry.dispose()); FX.marks = null; }
  if (!FX.issues.length) { if (V3.on) v3Refresh(); return; }
  const g = new T.Group();
  for (const i of FX.issues){
    const m = new T.Mesh(new T.SphereGeometry(18, 14, 10), new T.MeshBasicMaterial({color: i.kind === 'ceiling' ? 0x6aa0ff : i.kind === 'hole' ? 0xc77dff : 0xff5a3c, depthTest: false, transparent: true, opacity: 0.85}));
    m.position.set(i.x - V3.origin[0], i.y - V3.origin[1], i.z - V3.origin[2]);
    m.renderOrder = 30;
    g.add(m);
  }
  FX.marks = g; V3.scene.add(g);
  if (V3.on) v3Refresh();
}

async function fixitShow(i){
  if (!i) return;
  if (typeof selectRef === 'function') selectRef(FX.cell, i.ref, true);
  if (V3.on){
    // stand a little way into the room, looking at the spot
    const back = 420, dir = {N: [0, -1], S: [0, 1], E: [-1, 0], W: [1, 0]}[i.side] || [0, -1];
    V3.pos.set(i.x + dir[0] * back - V3.origin[0], i.y + dir[1] * back - V3.origin[1], i.z + 60 - V3.origin[2]);
    V3.yaw = Math.atan2(-dir[0], -dir[1]); V3.pitch = i.kind === 'ceiling' ? 0.6 : -0.1;
    v3Refresh();
  } else {
    W.cam.x = i.x; W.cam.y = i.y; if (W.cam.z < 1.5) W.cam.z = 1.5; drawMap();
  }
}

// other pieces of the style that fit the spot of a piece (or, for a loose piece, others its size)
async function fixitVariants(cell, ref, id){
  let r;
  try { r = await api('/api/fixit/variants?cell=' + encodeURIComponent(cell) + '&ref=' + encodeURIComponent(ref)); }
  catch (e){ return toast(e.message, true); }
  if (!r.variants.length) return toast(r.note || 'No other pieces of this style fit here.', true);
  fixitCss();
  const bg = document.createElement('div'); bg.className = 'modal-bg';
  const word = {W: 'wall', D: 'doorway', O: 'open'};
  const sides = p => p ? ['N', 'E', 'S', 'W'].map((s, k) => `${s} ${word[p[k]]}`).join(', ') : '';
  bg.innerHTML = `<div class="modal" style="width:min(760px,94vw)"><h2>↻ Other pieces for this spot</h2>
    <div class="msg">${esc(id)}${r.current ? ` · now: ${sides(r.current)}` : ''}. Pick one to swap it in, already turned to fit; the most alike come first.</div>
    <div class="fx-grid">${r.variants.map((v, k) => `<button data-fxv="${k}" title="${esc(v.id)}${v.pattern ? '\n' + sides(v.pattern) : ''}">${thumbImg(v.id, 'STAT', 96)}<small>${esc(v.id)}</small>
      ${v.pattern ? `<small>${v.pattern.split('').map(c => ({W: '▮', D: '⌂', O: '·'})[c]).join(' ')}${v.ceiling ? '' : ' · no ceiling'}</small>` : ''}</button>`).join('')}</div>
    <div class="msg">▮ wall · ⌂ doorway · · open, for the north, east, south and west sides.</div>
    <div class="actions"><button class="btn" id="fxv-no">Close</button></div></div>`;
  document.body.appendChild(bg);
  if (typeof v3ThumbScan === 'function') v3ThumbScan(bg);
  bg.querySelector('#fxv-no').onclick = () => bg.remove();
  bg.querySelectorAll('[data-fxv]').forEach(b => b.onclick = async () => {
    if (!await needProject()) return;
    const v = r.variants[+b.dataset.fxv];
    try {
      await post('/api/fixit/apply', {cell, ops: [{op: 'swap', ref, id: v.id, rz: v.rz}], label: 'Swapped "' + id + '" for "' + v.id + '"'});
      bg.remove(); toast('Swapped. Undo takes it back.');
      if (FX.panel && FX.cell === cell) await fixitAfter();
      else { if (typeof worldReloadCell === 'function') await worldReloadCell(cell); if (typeof afterChange === 'function') afterChange(); if (V3.on) v3Refresh(); }
    } catch (e){ toast(e.message, true); }
  });
}
