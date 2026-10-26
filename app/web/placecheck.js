// Health check for a place ("Check this place"): the furnishing faults Auto-furnish's own tests look for
// (chairs with nothing to sit at, things floating or through a wall, shelves and tapestries hung on
// nothing, lights hung from nothing, books leaning on nothing...) and the gap finder's findings, in one
// list grouped by kind, each with a marker on the map and in the 3D view, "Show me", and a fix where
// there's an obvious one (set it down, pull it out of the wall, remove it). Nothing changes until a fix
// is clicked; one Undo takes a fix back.
const PC = {cell: null, issues: [], res: null, panel: null, marks: null, shut: {}};
const PC_COLOR = {wall: '#ff5a3c', floating: '#ffb347', chair: '#ffd166', nowall: '#c77dff', light: '#6aa0ff', tall: '#ff5a3c',
  counter: '#e2b3ff', book: '#9be7a6', gap: '#ff5a3c', doorway: '#ff5a3c', ceiling: '#6aa0ff', post: '#ff5a3c', hole: '#c77dff',
  clip: '#ff8c69', zfight: '#ff8c69', joint: '#ffd98a'};

function placecheckCss(){
  if ($('#pc-css')) return;
  const c = document.createElement('style'); c.id = 'pc-css';
  c.textContent = `
  #pc-panel{position:fixed;left:16px;bottom:16px;width:min(400px,calc(100vw - 32px));max-height:64vh;display:flex;flex-direction:column;background:var(--panel);border:1px solid var(--line2);border-radius:12px;box-shadow:0 12px 40px #000c;z-index:70}
  .pbody #pc-panel{position:static;width:auto;max-height:none;background:none;border:0;border-radius:0;box-shadow:none;margin:-14px -16px 0}
  .pbody #pc-panel #pc-x{display:none}
  .pbody #pc-panel .pc-list{overflow:visible}
  #pc-panel .pc-h{display:flex;align-items:center;gap:8px;padding:10px 12px;border-bottom:1px solid var(--line)}
  #pc-panel .pc-h b{flex:1}
  #pc-panel .pc-list{overflow:auto;padding:6px 10px 10px}
  #pc-panel details{border-bottom:1px solid var(--line);padding:4px 0}
  #pc-panel details:last-of-type{border:0}
  #pc-panel summary{cursor:pointer;display:flex;align-items:center;gap:8px;padding:5px 0;list-style:none}
  #pc-panel summary::-webkit-details-marker{display:none}
  #pc-panel summary .pc-dot{width:10px;height:10px;border-radius:50%;flex:none;box-shadow:0 0 0 1px #0008}
  #pc-panel summary b{flex:1}
  #pc-panel summary .pc-n{font-size:11px;padding:1px 7px;border-radius:9px;background:var(--panel2);border:1px solid var(--line)}
  #pc-panel .pc-what{margin:0 0 4px 18px}
  #pc-panel .pc-i{padding:6px 0 6px 18px;border-top:1px solid var(--line)}
  #pc-panel .pc-i .pc-room{color:var(--muted);font-size:11.5px}
  #pc-panel .pc-acts{display:flex;flex-wrap:wrap;gap:6px;margin-top:5px}`;
  document.head.appendChild(c);
}

async function placecheckOpen(cell){
  placecheckCss();
  PC.cell = cell;
  const inPanel = typeof PNL !== 'undefined' && PNL.spaces.world && $('#world').classList.contains('on');
  if (inPanel){
    PNL.show('world', 'check');
    const body = PNL.body('world', 'check');
    if (!PC.panel || !body.contains(PC.panel)){ body.innerHTML = ''; PC.panel = document.createElement('div'); PC.panel.id = 'pc-panel'; body.appendChild(PC.panel); }
  } else if (!PC.panel){
    PC.panel = document.createElement('div'); PC.panel.id = 'pc-panel';
    document.body.appendChild(PC.panel);
  }
  PC.panel.innerHTML = '<div class="pc-h"><b>🩺 Checking this place…</b></div><div class="pc-list"><span class="spin"></span><div class="msg">Looking at every room: chairs, shelves, lights, books, walls, and the gaps. On a big house this takes a minute or two; you can keep working meanwhile.</div></div>';
  try { const r = await post('/api/place/check', {cell}); PC.issues = r.issues; PC.res = r; }
  catch (e){ PC.panel.innerHTML = `<div class="pc-h"><b>🩺 Check this place</b><button class="xbtn" id="pc-x">✕</button></div><div class="pc-list msg err">${esc(e.message)}</div>`; $('#pc-x').onclick = placecheckClose; return; }
  placecheckRender();
}

function placecheckRender(){
  const r = PC.res, n = PC.issues.length;
  const fixable = PC.issues.filter(i => i.fixes && i.fixes.length).length;
  const where = r.rooms ? `${r.rooms} room${r.rooms === 1 ? '' : 's'} and ${fmtN(r.things)} things` : 'the building';
  const gapNote = r.gaps && r.gaps.tiles ? `The gap finder looked at ${r.gaps.tiles} floor pieces${r.style ? ' (' + esc(r.style) + ')' : ''}${r.gaps.hidden ? `; ${r.gaps.hidden} see-through spot${r.gaps.hidden === 1 ? '' : 's'} left out because the game's own places have as many` : ''}.` : '';
  PC.panel.innerHTML = `<div class="pc-h"><b>🩺 ${n ? `${n} fault${n === 1 ? '' : 's'} found` : 'Nothing wrong found'}</b>
      <button class="btn sm" id="pc-again" title="Look again">↻</button><button class="xbtn" id="pc-x" title="Close">✕</button></div>
    <div class="pc-list">
      ${r.note ? `<div class="msg">${esc(r.note)}</div>` : ''}
      <div class="msg" style="margin-bottom:6px">Checked ${where}.${n ? ` ${fixable ? `${fixable} ${fixable === 1 ? 'has' : 'have'} a fix: each one is a step you can Undo.` : ''}` : ' Every chair has something to sit at, nothing floats or stands through a wall, every shelf and light hangs from something.'} ${gapNote}</div>
      ${r.counts.map(c => `<details ${PC.shut[c.kind] ? '' : 'open'} data-pckind="${c.kind}"><summary><span class="pc-dot" style="background:${PC_COLOR[c.kind] || '#ff5a3c'}"></span><b>${esc(c.label)}</b><span class="pc-n">${c.n}</span></summary>
        <div class="msg pc-what">${esc(c.what)}</div>
        ${PC.issues.filter(i => i.kind === c.kind).map(i => `<div class="pc-i"><div>${esc(i.text)}${i.side ? ` <span class="msg">(${{N: 'north', E: 'east', S: 'south', W: 'west'}[i.side]} side)</span>` : ''}</div>
          <div class="pc-room">${i.room ? esc(i.room) + ' · ' : ''}<span style="word-break:break-all">${esc(i.id)}</span></div>
          <div class="pc-acts"><button class="btn sm" data-pcshow="${i.n}" title="Select it and look at the spot">⌖ Show me</button>
            ${(i.fixes || []).map((f, k) => `<button class="btn sm ${k === 0 ? 'primary' : ''}" data-pcfix="${i.n}:${k}">${esc(f.label)}</button>`).join('')}
            ${i.kind === 'gap' || i.kind === 'doorway' || i.kind === 'ceiling' || i.kind === 'post' || i.kind === 'jambend' || i.kind === 'hole' || i.kind === 'joint' || i.kind === 'stairend' || i.kind === 'sunk' || i.kind === 'backwall' || i.kind === 'openpost' ? '<button class="btn sm" data-pcgaps="1" title="Open Find gaps, where these are fixed one by one or all at once">🔧 In Find gaps</button>' : ''}</div></div>`).join('')}</details>`).join('')}
    </div>`;
  $('#pc-x').onclick = placecheckClose;
  $('#pc-again').onclick = () => placecheckOpen(PC.cell);
  PC.panel.querySelectorAll('details').forEach(d => d.ontoggle = () => { PC.shut[d.dataset.pckind] = !d.open; });
  PC.panel.querySelectorAll('[data-pcshow]').forEach(b => b.onclick = () => placecheckShow(PC.issues.find(x => x.n === +b.dataset.pcshow)));
  PC.panel.querySelectorAll('[data-pcgaps]').forEach(b => b.onclick = () => { if (typeof fixitOpen === 'function') fixitOpen(PC.cell); });
  PC.panel.querySelectorAll('[data-pcfix]').forEach(b => b.onclick = async () => {
    if (!await needProject()) return;
    const [n, k] = b.dataset.pcfix.split(':').map(Number);
    const i = PC.issues.find(x => x.n === n), f = i.fixes[k];
    b.disabled = true;
    try {
      await post('/api/fixit/apply', {cell: PC.cell, ops: f.ops, label: `${f.label}: ${i.text}`});
      toast(`${f.label.replace(/ it$/, ' ' + (i.name || i.id))}. Undo takes it back.`);
      await placecheckAfter();
    } catch (e){ toast(e.message, true); b.disabled = false; }
  });
  placecheckMarks();
  if (!V3.on && typeof drawMap === 'function') drawMap();
}

async function placecheckAfter(){
  if (typeof worldReloadCell === 'function') await worldReloadCell(PC.cell);
  if (typeof afterChange === 'function') afterChange();
  if (typeof v3Refresh === 'function' && V3.on) v3Refresh();
  await placecheckOpen(PC.cell);
}

function placecheckClose(){
  if (PC.panel && PC.panel.closest('.pbody')){ PNL.close('world', 'check'); return; }
  if (PC.panel){ PC.panel.remove(); PC.panel = null; }
  PC.issues = [];
  placecheckMarks();
  if (!V3.on && typeof drawMap === 'function') drawMap();
}

// markers in the 3D view where the faults are, coloured by kind
function placecheckMarks(){
  if (typeof THREE === 'undefined' || !V3.scene) return;
  const T = THREE;
  if (PC.marks){ V3.scene.remove(PC.marks); PC.marks.children.forEach(c => c.geometry && c.geometry.dispose()); PC.marks = null; }
  if (!PC.issues.length) { if (V3.on) v3Refresh(); return; }
  const g = new T.Group();
  for (const i of PC.issues){
    const m = new T.Mesh(new T.SphereGeometry(16, 14, 10), new T.MeshBasicMaterial({color: parseInt((PC_COLOR[i.kind] || '#ff5a3c').slice(1), 16), depthTest: false, transparent: true, opacity: 0.85}));
    m.position.set(i.x - V3.origin[0], i.y - V3.origin[1], i.z - V3.origin[2]);
    m.renderOrder = 30;
    g.add(m);
  }
  PC.marks = g; V3.scene.add(g);
  if (V3.on) v3Refresh();
}

// the same markers on the flat map (called from drawMap)
function placecheckDraw(g){
  if (!PC.issues.length || !PC.cell || PC.cell !== W.key) return;
  for (const i of PC.issues){
    const [sx, sy] = toScreen(i.x, i.y);
    if (sx < -20 || sy < -20 || sx > W.w + 20 || sy > W.h + 20) continue;
    g.save();
    g.strokeStyle = PC_COLOR[i.kind] || '#ff5a3c'; g.lineWidth = 2.2; g.fillStyle = (PC_COLOR[i.kind] || '#ff5a3c') + '55';
    g.beginPath(); g.arc(sx, sy, 8, 0, Math.PI * 2); g.fill(); g.stroke();
    g.restore();
  }
}

function placecheckShow(i){
  if (!i) return;
  if (i.ref && typeof selectRef === 'function') selectRef(PC.cell, i.ref, true);
  if (V3.on){
    // stand a little way off, looking at the spot
    const back = 360, dir = {N: [0, -1], S: [0, 1], E: [-1, 0], W: [1, 0]}[i.side] || [0, -1];
    V3.pos.set(i.x + dir[0] * back - V3.origin[0], i.y + dir[1] * back - V3.origin[1], i.z + 90 - V3.origin[2]);
    V3.yaw = Math.atan2(-dir[0], -dir[1]); V3.pitch = i.kind === 'ceiling' || i.kind === 'light' ? 0.5 : -0.2;
    v3Refresh();
  } else {
    W.cam.x = i.x; W.cam.y = i.y; if (W.cam.z < 1.5) W.cam.z = 1.5; drawMap();
  }
}
