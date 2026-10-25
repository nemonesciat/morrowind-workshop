// ---------- Create > Dungeon (dwemer.py) ----------
// A dungeon (a Dwemer ruin, a cave, a Velothi tomb or a Daedric ruin), grown from its front door the way the
// game's own of the kind are put together from their pieces, then lit, stocked, guarded and lived in as
// theirs are. Made again from the World map's right-click menu until you like it.
const RUIN_KINDS = [
  ['dwemer', 'Dwemer ruin', 'Nchulmuz, Lower Halls', 'Dwemer ruins are named "Ruin, Part": Arkngthand, Hall of Centrifuge.',
    'Tunnels of the Dwemer laid out the way the game\'s 111 ruins of them are put together: corridors, corners, junctions and ramps that join where the game joins them, great halls tiled from hall pieces with the last one at the far end, door frames with their doors. Lights, pipes, barrels, coins and gears, chests and centurions stand in it as in the game\'s own.'],
  ['cave_mold', 'Cave: grey stone', 'Sarnabi Cave', 'Caves are named for a place or a person: Shushan, Mallapi, Assemanu.',
    'A cave of grey stone tunnels and chambers, from the in_moldcave pieces the way the game\'s caves join them: winding passages up and down, big chambers on the way and at the far end, rocks, mushrooms, torches and what lives in it copied from the game\'s own caves.'],
  ['cave_mud', 'Cave: brown earth', 'Hlormar Egg Mine', 'Caves are named for a place or a person: Shushan, Mallapi, Assemanu.',
    'A cave of brown earth (the in_mudcave pieces), joined and dressed the way the game\'s own are.'],
  ['cave_py', 'Cave: pale rock', 'Ashurnibi Cave', 'Caves are named for a place or a person: Shushan, Mallapi, Assemanu.',
    'A cave of pale rock (the in_pycave pieces), joined and dressed the way the game\'s own are.'],
  ['cave_lava', 'Cave: lava rock', 'Mabrelet Cave', 'Caves are named for a place or a person: Shushan, Mallapi, Assemanu.',
    'A cave of black lava rock (the in_lavacave pieces), joined and dressed the way the game\'s own are.'],
  ['tomb', 'Velothi tomb', 'Varethi Ancestral Tomb', 'Tombs are named for the family: Andrethi Ancestral Tomb, Sarys Ancestral Tomb.',
    'A family tomb of the small Velothi pieces the way the game\'s 380 tombs are put together: narrow halls, corners and stairs with doors between, burial rooms on the way and at the far end, urns, altars, bones and the restless dead copied from the game\'s own.'],
  ['daedric', 'Daedric ruin', 'Zaintashara, Shrine', 'Daedric ruins have old Dunmer names: Ald Sotha, Zaintiraris, Ashalmimilkala.',
    'A ruined Daedric shrine of the in_dae halls the way the game\'s own are joined, with rooms tiled of 2x3 to 3x4 floors, walls and corners as Project Tamriel\'s guide has them, braziers and censers, rubble and pillars, and its Daedra.'],
];
const RUIN_OPTS = {
  kind: RUIN_KINDS.map(k => [k[0], k[1]]),
  size: [['small', 'Small (about 20 pieces, one hall)'], ['medium', 'Medium (about 45 pieces, two halls)'], ['large', 'Large (about 80 pieces, three halls)']],
  levels: [['flat', 'All on one level'], ['some', 'Some ramps up and down (as the game\'s)'], ['steep', 'Many ramps: up and down a lot']],
  twist: [['linear', 'One long winding way through'], ['branching', 'Branching, with side passages (as the game\'s)'], ['maze', 'A maze of crossroads and dead ends']],
  creatures: [['none', 'None'], ['few', 'A few'], ['usual', 'As in the game\'s own'], ['many', 'Many']],
  loot: [['sparse', 'Picked over'], ['usual', 'As in the game\'s own'], ['rich', 'Rich (full barrels, a chest more)']],
  occupants: [['auto', 'As the game\'s own: some have someone (smugglers, bandits, cultists)'], ['yes', 'Someone has moved in'], ['none', 'Nobody']],
};
const ruinKind = k => RUIN_KINDS.find(x => x[0] === k) || RUIN_KINDS[0];

// The Dungeon tool: the choices down the left, the plan of the layout they make on the right, grown again
// as soon as anything changes (a tenth of a second on the server); Make it builds the plan shown.
const DT = {kind: 'dwemer', seed: null, lay: null, view: null, seq: 0, hover: null, drag: null, user: false,
  // (the plan flat, or a rough 3D sketch of blocks at their heights, turned by dragging; the user asked for both)
  mode: (() => { try { return localStorage.getItem('ws-dt-mode') === '3d' ? '3d' : '2d'; } catch (e){ return '2d'; } })(), yaw: 0.6, pitch: 0.75};
const DT_ZX = 1.6;          // (heights drawn taller than they are in 3D, so the levels read)
const DT_ICON = {dwemer: '⚙', cave_mold: '◆', cave_mud: '◆', cave_py: '◆', cave_lava: '◆', tomb: '⚱', daedric: '✴'};
const DT_ROCK = {cave_mold: '#8c8f93', cave_mud: '#8a6d4f', cave_py: '#c9c1ad', cave_lava: '#3b3533'};
const DT_SEG = {
  size: [['small', 'Small', 'about 20 pieces, one hall'], ['medium', 'Medium', 'about 45 pieces, two halls'], ['large', 'Large', 'about 80 pieces, three halls']],
  levels: [['flat', 'Flat', 'all on one level'], ['some', 'Some', 'some ramps up and down, as the game\'s'], ['steep', 'Steep', 'up and down a lot']],
  twist: [['linear', 'Winding', 'one long winding way through'], ['branching', 'Branching', 'side passages, as the game\'s'], ['maze', 'Maze', 'crossroads and dead ends']],
  water: [['none', 'Dry', 'no water'], ['pools', 'Pools', 'water over the lowest floors'], ['flooded', 'Flooded', 'the lower half under water, the way in dry, with fish']],
};

function ruinFormHtml(what){
  const s = (id, k, v) => sel(id, RUIN_OPTS[k], v);
  const K = ruinKind(DT.kind);
  if (DT.seed == null) DT.seed = Math.floor(Math.random() * 2147483647);
  const seg = (k, cur) => `<input type="hidden" id="ru-${k}" value="${cur}"><div class="dt-seg" data-seg="${k}">${DT_SEG[k].map(([v, l, t]) =>
    `<button type="button" class="${v === cur ? 'on' : ''}" data-v="${v}" title="${esc(t)}">${l}</button>`).join('')}</div>`;
  setTimeout(dtStart, 0);
  return `<div class="dtool">
    <div class="dt-side">
      <div class="dt-h">Kind</div>
      <input type="hidden" id="ru-kind" value="${DT.kind}">
      <div class="dt-kinds">${RUIN_KINDS.map(k => `<button type="button" class="dt-k ${k[0] === DT.kind ? 'on' : ''}" data-dk="${k[0]}" title="${esc(k[4])}">
        <span class="dt-ki" ${DT_ROCK[k[0]] ? `style="color:${DT_ROCK[k[0]]}"` : ''}>${DT_ICON[k[0]]}</span>${esc(k[1].replace('Cave: ', 'Cave, '))}</button>`).join('')}</div>
      <div class="dt-h">Size</div>${seg('size', 'medium')}
      <div class="dt-h">Levels</div>${seg('levels', 'some')}
      <div class="dt-h">Layout</div>${seg('twist', 'branching')}
      <div class="dt-h">Water</div>${seg('water', 'none')}
      <div class="dt-grid">
        <label>Creatures</label>${s('ru-crea', 'creatures', 'usual')}
        <label>Loot</label>${s('ru-loot', 'loot', 'usual')}
        <label>Lived in</label>${s('ru-occ', 'occupants', 'auto')}
      </div>
      <div class="dt-h">Name</div>
      <input class="inp" id="cr-name" placeholder="e.g. ${esc(K[2])}" maxlength="63" title="${esc(K[3])}">
      <div class="dt-h">Door outside</div>
      <div class="dt-door">${placeOptions(false, "None yet (link one later)")}</div>
      <div class="dt-go"><button class="btn primary" id="cr-go" title="Build the layout shown, dressed, lit and lived in: one Undo takes it back">Make it</button><span class="msg" id="cr-msg"></span></div>
    </div>
    <div class="dt-main">
      <div class="dt-bar"><span class="dt-seed">Seed <input class="inp" id="ru-seed" value="${DT.seed}" spellcheck="false"></span>
        <button class="btn sm" type="button" id="ru-newseed" title="Another layout with the same choices">🎲 Another</button>
        <button class="btn sm" type="button" id="dt-back" title="The layout before this one">↶</button>
        <button class="btn sm" type="button" id="dt-fit" title="Fit the plan to the view">⤢ Fit</button>
        <button class="btn sm dt-mode" type="button" id="dt-3d" title="The plan flat, or a rough 3D sketch you can turn by dragging">${DT.mode === '3d' ? '▦ 2D' : '◩ 3D'}</button>
        <span class="dt-stat" id="dt-stat"></span></div>
      <div class="dt-canvas"><canvas id="dt-cv"></canvas><div class="dt-msg" id="dt-msg"></div></div>
      <div class="dt-legend"><span><i style="background:var(--dt-tun)"></i>tunnel</span><span><i style="background:var(--dt-ramp)"></i>ramp or stairs</span>
        <span><i style="background:var(--dt-hall)"></i><span id="dt-hw">hall</span></span><span><i style="background:var(--dt-dead)"></i>dead end</span>
        <span><b style="color:var(--gold2)">★</b> the last one</span><span><b>▲</b> way in</span><span class="dt-hov" id="dt-hov">Lighter is higher. Drag to move, wheel to zoom.</span></div>
    </div>
  </div><div class="dt-what">${what}</div>`;
}

const DT_HIST = [];
function dtStart(){
  dtCss();
  const cv = $('#dt-cv'); if (!cv) return;
  if (!cv._dt){
    cv._dt = true;
    new ResizeObserver(() => dtDraw()).observe(cv.parentNode);
    cv.addEventListener('wheel', e => { e.preventDefault(); const V = DT.view; if (!V) return;
      const r = cv.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top, f = e.deltaY < 0 ? 1.18 : 1 / 1.18;
      V.ox = mx - (mx - V.ox) * f; V.oy = my - (my - V.oy) * f; V.s *= f; DT.user = true; dtDraw(); }, {passive: false});
    cv.addEventListener('pointerdown', e => { DT.drag = {x: e.clientX, y: e.clientY, pan: e.shiftKey || e.button === 2}; cv.setPointerCapture(e.pointerId); });
    cv.addEventListener('pointerup', () => { DT.drag = null; });
    cv.addEventListener('contextmenu', e => { if (DT.mode === '3d') e.preventDefault(); });
    cv.addEventListener('pointermove', e => {
      const V = DT.view; if (!V) return;
      if (DT.drag){
        const dx = e.clientX - DT.drag.x, dy = e.clientY - DT.drag.y;
        // (in 3D a drag turns the sketch, Shift- or right-drag moves it; flat, a drag moves the plan)
        if (DT.mode === '3d' && !DT.drag.pan){ DT.yaw += dx * 0.01; DT.pitch = Math.max(0.12, Math.min(1.5, DT.pitch + dy * 0.008)); }
        else { V.ox += dx; V.oy += dy; }
        DT.drag = {x: e.clientX, y: e.clientY, pan: DT.drag.pan}; DT.user = true; dtDraw(); return;
      }
      const r = cv.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
      const P = DT.lay ? DT.lay.pieces : [];
      let hit = null;
      if (DT.mode === '3d'){
        // (the nearest block whose top is under the pointer)
        let best = Infinity;
        for (const p of P){ const q = dt3Top(p); if (dtInPoly(mx, my, q.pts) && q.depth < best){ best = q.depth; hit = p; } }
      } else {
        const wx = (mx - V.ox) / V.s, wy = -(my - V.oy) / V.s;
        for (const p of P) if (wx >= p[0] && wx <= p[2] && wy >= p[1] && wy <= p[3] && (!hit || p[5] > hit[5])) hit = p;
      }
      const h = $('#dt-hov');
      if (h) h.textContent = hit ? `${hit[8]} · ${hit[7] != null ? (DT.lay.final === hit[7] ? 'the last ' : '') + DT.lay.hall_word : hit[6]} · height ${hit[4]} to ${hit[5]}` : DT.mode === '3d' ? 'Lighter is higher. Drag to turn, Shift-drag to move, wheel to zoom.' : 'Lighter is higher. Drag to move, wheel to zoom.';
      if (DT.hover !== hit){ DT.hover = hit; dtDraw(); }
    });
  }
  dtPreview();
}

async function dtPreview(){
  const v = id => (($('#' + id) || {}).value || '');
  const seq = ++DT.seq;
  const sd = parseInt(v('ru-seed'), 10);
  DT.seed = isFinite(sd) ? sd : DT.seed;
  const msg = $('#dt-msg');
  for (let n = 0; n < 120; n++){
    let r;
    try { r = await post('/api/ruin/preview', {kind: v('ru-kind'), size: v('ru-size'), levels: v('ru-levels'), twist: v('ru-twist'), seed: DT.seed}); }
    catch (e){ if (msg) msg.textContent = e.message; return; }
    if (seq !== DT.seq) return;
    if (r.learning){ DT.lay = null; const st0 = $('#dt-stat'); if (st0) st0.textContent = ''; const cv0 = $('#dt-cv'); if (cv0) cv0.getContext('2d').clearRect(0, 0, cv0.width, cv0.height); if (msg) msg.innerHTML = `<span class="spin"></span>Learning ${esc(r.learning.join(', '))} first (once, under a minute)…`; await new Promise(res => setTimeout(res, 2500)); continue; }
    if (msg) msg.textContent = '';
    const kindChanged = !DT.lay || DT.lay.kind !== r.kind;
    DT.lay = r;
    if (kindChanged || !DT.user) DT.view = null;
    const st = $('#dt-stat');
    if (st) st.textContent = `${r.tunnels} tunnel pieces, ${r.halls} ${r.hall_word}${r.halls === 1 ? '' : 's'}${r.open_left ? `, ${r.open_left} left open` : ''}`;
    const hw = $('#dt-hw'); if (hw) hw.textContent = r.hall_word;
    dtDraw();
    return;
  }
}

function dtFit(cv){
  const P = DT.lay.pieces;
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const p of P){ x0 = Math.min(x0, p[0]); y0 = Math.min(y0, p[1]); x1 = Math.max(x1, p[2]); y1 = Math.max(y1, p[3]); }
  const w = cv.clientWidth, h = cv.clientHeight;
  if (DT.mode === '3d'){
    // (the sketch's own bounds at scale 1 about the middle, then scaled to the view)
    DT.view = {s: 1, ox: 0, oy: 0};
    let a = Infinity, b = Infinity, c = -Infinity, d = -Infinity;
    for (const p of P) for (const q of dt3Box(p)) { a = Math.min(a, q[0]); b = Math.min(b, q[1]); c = Math.max(c, q[0]); d = Math.max(d, q[1]); }
    const s = Math.min((w - 40) / Math.max(1, c - a), (h - 40) / Math.max(1, d - b));
    DT.view = {s, ox: w / 2 - (a + c) / 2 * s, oy: h / 2 - (b + d) / 2 * s};
    return;
  }
  const s = Math.min((w - 40) / Math.max(1, x1 - x0), (h - 40) / Math.max(1, y1 - y0));
  DT.view = {s, ox: w / 2 - (x0 + x1) / 2 * s, oy: h / 2 + (y0 + y1) / 2 * s};
}

// ----- the 3D sketch: blocks a storey's floor thick, seen from above at an angle -----
function dt3Mid(){
  const L = DT.lay;
  if (!L._mid){
    const P = L.pieces;
    let x0 = Infinity, y0 = Infinity, z0 = Infinity, x1 = -Infinity, y1 = -Infinity, z1 = -Infinity;
    for (const p of P){ x0 = Math.min(x0, p[0]); y0 = Math.min(y0, p[1]); x1 = Math.max(x1, p[2]); y1 = Math.max(y1, p[3]); z0 = Math.min(z0, p[4]); z1 = Math.max(z1, p[4]); }
    L._mid = [(x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2];
  }
  return L._mid;
}
// a world point on the screen: [x, y, depth (larger is further)]
function dt3(x, y, z){
  const [cx, cy, cz] = dt3Mid(), V = DT.view, c = Math.cos(DT.yaw), s = Math.sin(DT.yaw), cp = Math.cos(DT.pitch), sp = Math.sin(DT.pitch);
  const dx = x - cx, dy = y - cy, dz = (z - cz) * DT_ZX;
  const rx = dx * c - dy * s, ry = dx * s + dy * c;
  return [V.ox + rx * V.s, V.oy - (ry * cp + dz * sp) * V.s, ry * sp - dz * cp];
}
// (a block from the piece's floor up a little: the floor is what tells the levels apart)
const dt3H = p => Math.min(180, Math.max(48, (p[5] - p[4]) * 0.3));
function dt3Box(p){
  const z0 = p[4], z1 = p[4] + dt3H(p), out = [];
  for (const z of [z0, z1]) for (const [x, y] of [[p[0], p[1]], [p[2], p[1]], [p[2], p[3]], [p[0], p[3]]]) out.push(dt3(x, y, z));
  return out;
}
function dt3Top(p){
  const q = dt3Box(p).slice(4);
  return {pts: q, depth: q.reduce((a, v) => a + v[2], 0) / 4};
}
function dtInPoly(x, y, pts){
  let inside = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++){
    const [xi, yi] = pts[i], [xj, yj] = pts[j];
    if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}
function dtDraw3(g, w, h, col){
  const P = DT.lay.pieces;
  const zs = P.map(p => p[4]), zmin = Math.min(...zs), span = Math.max(1, Math.max(...zs) - zmin);
  const base = r => r === 'ramp' ? '--dt-ramp' : r === 'dead end' ? '--dt-dead' : '--dt-tun';
  // (the lowest level's floor as a faint grid, for the ground)
  const B = DT.lay.pieces.reduce((a, p) => [Math.min(a[0], p[0]), Math.min(a[1], p[1]), Math.max(a[2], p[2]), Math.max(a[3], p[3])], [Infinity, Infinity, -Infinity, -Infinity]);
  g.strokeStyle = col('--dt-grid'); g.lineWidth = 1; g.beginPath();
  for (let x = Math.floor(B[0] / 256) * 256; x <= B[2]; x += 256){ const a = dt3(x, B[1], zmin), b = dt3(x, B[3], zmin); g.moveTo(a[0], a[1]); g.lineTo(b[0], b[1]); }
  for (let y = Math.floor(B[1] / 256) * 256; y <= B[3]; y += 256){ const a = dt3(B[0], y, zmin), b = dt3(B[2], y, zmin); g.moveTo(a[0], a[1]); g.lineTo(b[0], b[1]); }
  g.stroke();
  // further blocks first (the painter's way: rough, as a sketch)
  const order = P.map(p => ({p, box: dt3Box(p)})).map(o => Object.assign(o, {d: o.box.reduce((a, v) => a + v[2], 0) / 8})).sort((a, b) => b.d - a.d);
  const face = (pts, fill, shade, edge, lw) => {
    g.beginPath(); g.moveTo(pts[0][0], pts[0][1]); for (const q of pts.slice(1)) g.lineTo(q[0], q[1]); g.closePath();
    g.fillStyle = fill; g.fill();
    if (shade){ g.fillStyle = `rgba(0,0,0,${shade})`; g.fill(); }
    g.strokeStyle = edge; g.lineWidth = lw; g.stroke();
  };
  for (const {p, box} of order){
    const lift = (p[4] - zmin) / span, fill = col(p[7] != null ? '--dt-hall' : base(p[6]));
    const hov = p === DT.hover, edge = hov ? col('--gold2') : col('--dt-edge'), lw = hov ? 2 : 1;
    g.globalAlpha = 0.7 + 0.3 * lift;
    // (the sides facing the eye: a side is seen when its far corner is further than its near one)
    for (const [a, b] of [[0, 1], [1, 2], [2, 3], [3, 0]]){
      const n0 = box[a], n1 = box[b], mid = (n0[2] + n1[2]) / 2, opp = (box[(a + 2) % 4][2] + box[(b + 2) % 4][2]) / 2;
      if (mid < opp) face([box[a], box[b], box[b + 4], box[a + 4]], fill, 0.42, edge, lw);
    }
    face(box.slice(4), fill, 0, edge, lw);
    g.globalAlpha = 1;
  }
  const fin = P.filter(p => p[7] != null && p[7] === DT.lay.final);
  g.textAlign = 'center'; g.textBaseline = 'middle';
  if (fin.length){
    const cx = fin.reduce((a, p) => a + (p[0] + p[2]) / 2, 0) / fin.length, cy = fin.reduce((a, p) => a + (p[1] + p[3]) / 2, 0) / fin.length;
    const q = dt3(cx, cy, fin[0][4] + dt3H(fin[0]) + 40);
    g.fillStyle = col('--gold2'); g.font = '18px sans-serif'; g.fillText('★', q[0], q[1]);
  }
  const e = DT.lay.entrance, q = dt3(e[0], e[1], (e[2] != null ? e[2] : zmin) + 120);
  g.fillStyle = col('--text'); g.font = '15px sans-serif'; g.fillText('▲', q[0], q[1]);
}

function dtDraw(){
  const cv = $('#dt-cv'); if (!cv || !DT.lay) return;
  const dpr = window.devicePixelRatio || 1, w = cv.parentNode.clientWidth, h = cv.parentNode.clientHeight;
  if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)){ cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); cv.style.width = w + 'px'; cv.style.height = h + 'px'; }
  if (!DT.view || (!DT.user && (DT.fitW !== w || DT.fitH !== h))){ dtFit(cv); DT.fitW = w; DT.fitH = h; }
  const g = cv.getContext('2d'), V = DT.view, cs = getComputedStyle(cv);
  const col = k => cs.getPropertyValue(k).trim();
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.fillStyle = col('--dt-bg'); g.fillRect(0, 0, w, h);
  if (DT.mode === '3d') return dtDraw3(g, w, h, col);
  // (a grid a tile apart, faint, for scale)
  const T = 256 * V.s;
  if (T > 6){
    g.strokeStyle = col('--dt-grid'); g.lineWidth = 1; g.beginPath();
    for (let x = ((V.ox % T) + T) % T; x < w; x += T){ g.moveTo(x, 0); g.lineTo(x, h); }
    for (let y = ((V.oy % T) + T) % T; y < h; y += T){ g.moveTo(0, y); g.lineTo(w, y); }
    g.stroke();
  }
  const P = DT.lay.pieces.slice().sort((a, b) => a[5] - b[5]);         // (the higher drawn over the lower)
  const zs = P.map(p => p[4]), zmin = Math.min(...zs), zmax = Math.max(...zs), span = Math.max(1, zmax - zmin);
  const base = r => r === 'ramp' ? '--dt-ramp' : r === 'dead end' ? '--dt-dead' : '--dt-tun';
  for (const p of P){
    const X = V.ox + p[0] * V.s, Y = V.oy - p[3] * V.s, W = (p[2] - p[0]) * V.s, H = (p[3] - p[1]) * V.s;
    const lift = (p[4] - zmin) / span;
    g.globalAlpha = 0.55 + 0.45 * lift;
    g.fillStyle = col(p[7] != null ? '--dt-hall' : base(p[6]));
    g.fillRect(X, Y, W, H);
    g.globalAlpha = 1;
    g.strokeStyle = p === DT.hover ? col('--gold2') : col('--dt-edge');
    g.lineWidth = p === DT.hover ? 2 : 1;
    g.strokeRect(X + 0.5, Y + 0.5, W - 1, H - 1);
  }
  // the last hall, and the way in
  const fin = P.filter(p => p[7] != null && p[7] === DT.lay.final);
  if (fin.length){
    const cx = fin.reduce((a, p) => a + (p[0] + p[2]) / 2, 0) / fin.length, cy = fin.reduce((a, p) => a + (p[1] + p[3]) / 2, 0) / fin.length;
    g.fillStyle = col('--gold2'); g.font = '18px sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText('★', V.ox + cx * V.s, V.oy - cy * V.s);
  }
  const e = DT.lay.entrance;
  g.fillStyle = col('--text'); g.font = '15px sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
  g.fillText('▲', V.ox + e[0] * V.s, V.oy - e[1] * V.s);
}

function dtCss(){
  if ($('#dt-css')) return;
  const c = document.createElement('style'); c.id = 'dt-css';
  c.textContent = `
  .dtool{display:grid;grid-template-columns:232px 1fr;gap:12px;min-height:520px;--dt-bg:#0f0d0a;--dt-grid:#ffffff08;--dt-tun:#7d7466;--dt-ramp:#c08a3e;--dt-hall:#4f8a6a;--dt-dead:#4a4038;--dt-edge:#00000080}
  .dt-side{display:flex;flex-direction:column;gap:4px;font-size:12.5px}
  .dt-h{font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--faint);margin:6px 0 1px}
  .dt-kinds{display:flex;flex-direction:column;border:1px solid var(--line2);border-radius:6px;overflow:hidden}
  .dt-k{display:flex;gap:8px;align-items:center;text-align:left;padding:4px 8px;background:none;border:0;border-bottom:1px solid var(--line);color:var(--text);cursor:pointer;font:inherit}
  .dt-k:last-child{border-bottom:0}.dt-k:hover{background:#ffffff0d}.dt-k.on{background:#d2a85a24;color:var(--gold2)}
  .dt-ki{width:14px;text-align:center}
  .dt-seg{display:flex;border:1px solid var(--line2);border-radius:6px;overflow:hidden}
  .dt-seg button{flex:1;padding:4px 0;background:none;border:0;border-right:1px solid var(--line);color:var(--muted);cursor:pointer;font:inherit}
  .dt-seg button:last-child{border-right:0}.dt-seg button:hover{background:#ffffff0d}.dt-seg button.on{background:#d2a85a24;color:var(--gold2)}
  .dt-grid{display:grid;grid-template-columns:70px 1fr;gap:4px 6px;align-items:center;margin-top:6px}
  .dt-grid select,.dt-side .inp,.dt-door select{font-size:12.5px;padding:3px 6px;min-width:0;width:100%}
  .dt-go{display:flex;gap:8px;align-items:center;margin-top:10px}
  .dt-main{display:flex;flex-direction:column;min-width:0}
  .dt-bar{display:flex;gap:6px;align-items:center;font-size:12px;color:var(--muted);margin-bottom:6px;white-space:nowrap;min-width:0}
  .dt-bar .btn{white-space:nowrap;flex:none}.dt-stat{overflow:hidden;text-overflow:ellipsis}
  .dt-seed .inp{width:110px;padding:2px 6px;font-size:12px}
  .dt-stat{margin-left:auto}
  .dt-canvas{position:relative;flex:1;min-height:420px;border:1px solid var(--line2);border-radius:6px;overflow:hidden;cursor:grab}
  .dt-canvas canvas{position:absolute;inset:0;display:block}
  .dt-msg{position:absolute;left:12px;top:10px;font-size:12px;color:var(--muted);pointer-events:none}
  .dt-legend{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:11.5px;color:var(--muted);margin-top:6px;align-items:center}
  .dt-legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px;vertical-align:-1px}
  .dt-hov{margin-left:auto;color:var(--faint)}
  .dt-what{font-size:12px;margin-top:8px;color:var(--muted)}`;
  document.head.appendChild(c);
}

document.addEventListener('click', e => {
  const t = e.target.closest && e.target.closest('.dt-seg button, .dt-k, #dt-fit, #dt-back, #dt-3d');
  if (!t) return;
  if (t.id === 'dt-fit'){ DT.view = null; DT.user = false; dtDraw(); return; }
  if (t.id === 'dt-3d'){
    DT.mode = DT.mode === '3d' ? '2d' : '3d';
    try { localStorage.setItem('ws-dt-mode', DT.mode); } catch (er){}
    t.textContent = DT.mode === '3d' ? '▦ 2D' : '◩ 3D';
    const hv = $('#dt-hov'); if (hv) hv.textContent = DT.mode === '3d' ? 'Lighter is higher. Drag to turn, Shift-drag to move, wheel to zoom.' : 'Lighter is higher. Drag to move, wheel to zoom.';
    DT.view = null; DT.user = false; dtDraw(); return;
  }
  if (t.id === 'dt-back'){ const s = DT_HIST.pop(); if (s == null) return toast('No layout before this one.'); DT.seed = s; const i = $('#ru-seed'); if (i) i.value = s; dtPreview(); return; }
  if (t.classList.contains('dt-k')){
    DT.kind = t.dataset.dk; $('#ru-kind').value = DT.kind;
    document.querySelectorAll('.dt-k').forEach(b => b.classList.toggle('on', b === t));
    const K = ruinKind(DT.kind), n = $('#cr-name'); if (n){ n.placeholder = 'e.g. ' + K[2]; n.title = K[3]; }
  } else {
    const box = t.parentNode, k = box.dataset.seg;
    box.querySelectorAll('button').forEach(b => b.classList.toggle('on', b === t));
    $('#ru-' + k).value = t.dataset.v;
  }
  if (typeof crWhat === 'function') crWhat();
  dtPreview();
});
document.addEventListener('change', e => { if (e.target && e.target.id === 'ru-seed') dtPreview(); });

const RUIN_SAY = {
  twist: {linear: 'one long winding way through', branching: 'branching, with side passages', maze: 'a maze of crossroads and dead ends'},
  levels: {flat: 'all on one level', some: 'with some ramps up and down', steep: 'climbing and dropping a lot'},
  creatures: {none: 'no creatures', few: 'a few creatures', usual: 'as many creatures as the game\'s own', many: 'many creatures'},
  loot: {sparse: 'picked-over loot', usual: 'loot as in the game\'s own', rich: 'rich loot'},
};
function ruinWhat(where){
  const v = id => (($('#' + id) || {}).value || '');
  const say = (k, id) => RUIN_SAY[k][v(id)] || '';
  const name = v('cr-name').trim();
  const K = ruinKind(v('ru-kind'));
  return `<b>Make it</b> builds the plan shown as ${name ? `"${esc(name)}"` : 'a new place'}, dressed as the game's own ${esc(K[1].replace('Cave: ', 'caves of ').toLowerCase().replace('dwemer ruin', 'Dwemer ruins').replace('velothi tomb', 'Velothi tombs').replace('daedric ruin', 'Daedric ruins'))}, ` +
    `with ${say('creatures', 'ru-crea')} and ${say('loot', 'ru-loot')}` +
    (v('ru-occ') === 'yes' ? ', someone living in it' : v('ru-occ') === 'none' ? ', nobody living in it' : '') +
    (where ? `, its front door linked to a door ${where}` : '') + '. One Undo takes it back.';
}

async function ruinGo(msg){
  const v = id => (($('#' + id) || {}).value || '');
  const body = {kind: v('ru-kind') || 'dwemer', name: v('cr-name'), size: v('ru-size'), levels: v('ru-levels'), twist: v('ru-twist'), creatures: v('ru-crea'),
    loot: v('ru-loot'), occupants: v('ru-occ'), water: v('ru-water') || 'none', seed: v('ru-seed').trim() || null, entrance: placeValue()};
  // (the first of each kind waits for the survey of the game's own, 15-20 s once; the survey process learns it)
  for (let n = 0; n < 120; n++){
    const r = await post('/api/ruin/build', body);
    if (!r.learning) return r;
    msg.innerHTML = `<span class="spin"></span>Learning ${esc(r.learning.join(', '))} first (once)…`;
    await new Promise(res => setTimeout(res, 3000));
  }
  throw new Error('Still learning the game\'s own places of the kind: try again in a minute.');
}

// (what the toast calls a made place's halls)
const ruinHalls = (kind, n) => `${n} ${kind === 'daedric' ? 'room' : kind && kind !== 'dwemer' ? 'chamber' : 'hall'}${n === 1 ? '' : 's'}`;

async function ruinAgain(key){
  if (!await needProject()) return;
  try {
    toast('Making it again…');
    const r = await post('/api/ruin/again', {cell: key});
    await afterChange();
    await worldOpen(r.key);
    toast(`A new layout: ${r.tunnels} tunnel pieces, ${ruinHalls(r.kind, r.halls)}${r.people ? `, ${r.people} living in it` : ''}. Undo brings the last one back.`);
  } catch (e){ toast(e.message, true); }
}

document.addEventListener('click', e => {
  if (!(e.target && e.target.closest && e.target.closest('#ru-newseed'))) return;
  const s = $('#ru-seed'); if (!s) return;
  if (DT.seed != null) DT_HIST.push(DT.seed);
  DT.seed = Math.floor(Math.random() * 2147483647);
  s.value = String(DT.seed);
  dtPreview();
});
if (typeof CF_ACT !== 'undefined') CF_ACT.push({id: 'ruinagain', label: 'Make this dungeon again (a new layout)', keys: [], world: true,
  run: () => W.info && W.info.ruin ? ruinAgain(W.info.key) : toast('Open a dungeon you made first.', true)});
