// ---------- Minimap ----------
// A small map of where you are, as a panel of the World (dock it, tab it or float it like the others): in 3D it
// follows the camera, an arrow for the way you face; on the flat map it shows where the view is. The land outdoors,
// the building and the things indoors (your storey only, by the camera's height), drawn from what the map has
// loaded. Click to go there (in 3D, at the same height over the ground or on the same floor), drag to look round it,
// wheel to zoom, 📍 to follow again; the line under it names what the pointer is over. (The user, 2026-10-31: "a
// dockable minimap that can be used as a reference or even to move around from the map from the 3d view")
const MM = {zIn: 0.16, zOut: 0.012, follow: true, at: null, cv: null, it: null, last: '', drag: null, hover: ''};

function mmPanels(){
  PNL.define('world', 'minimap', {title: 'Minimap', icon: '🧭', home: 'float', w: 280, h: 320, cls: 'wside mmpanel',
    render: mmRender, onShow: mmRender, onClose: () => { MM.cv = null; MM.it = null; }});
}

function mmRender(it){
  MM.it = it;
  it.el.innerHTML = `<div class="mm"><canvas class="mm-cv"></canvas>
    <div class="mm-bar"><span class="mm-tip" title="What the pointer is over"></span>
      <button class="btn sm mm-follow" title="Follow where you are again">📍</button></div></div>`;
  if (!$('#mm-css')){
    const c = document.createElement('style'); c.id = 'mm-css';
    c.textContent = `.mmpanel{overflow:hidden !important}.mm{display:flex;flex-direction:column;height:100%;min-height:0}
      .mm-cv{flex:1;width:100%;min-height:60px;border-radius:6px;background:#0e0d0a;cursor:crosshair;display:block}
      .mm-bar{display:flex;align-items:center;gap:6px;margin-top:4px;font-size:11.5px;color:var(--muted)}
      .mm-tip{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
      .mm-follow{padding:0 6px}`;
    document.head.appendChild(c);
  }
  MM.cv = it.el.querySelector('.mm-cv');
  it.el.querySelector('.mm-follow').onclick = () => { MM.follow = true; MM.at = null; MM.last = ''; mmDraw(); };
  mmBind(MM.cv);
  MM.last = '';
  mmDraw();
  mmLoop();
}

// where the minimap is centred and which way you face: the 3D camera, else the flat map's view
function mmWhere(){
  if (typeof V3 !== 'undefined' && V3.on && V3.pos){
    const [x, y, z] = v3CamWorld();
    return {x, y, z, yaw: V3.yaw, three: true};
  }
  return {x: W.cam.x, y: W.cam.y, z: null, yaw: null, three: false};
}
function mmScale(){ return W.ext ? MM.zOut : MM.zIn; }
function mmCentre(){ const w = mmWhere(); return MM.follow || !MM.at ? [w.x, w.y] : MM.at; }

// (redrawn only while it's shown, ten times a second at most, and only when what it shows has moved)
function mmLoop(){
  if (MM.looping) return;
  MM.looping = true;
  const tick = () => {
    if (!MM.cv || !MM.cv.isConnected){ MM.looping = false; return; }
    const w = mmWhere(), c = mmCentre();
    const key = [Math.round(c[0] / 8), Math.round(c[1] / 8), w.z == null ? '' : Math.round(w.z / 32), w.yaw == null ? '' : Math.round(w.yaw * 20),
                 MM.cv.clientWidth, MM.cv.clientHeight, W.ext ? MM.zOut : MM.zIn, W.key, Object.keys(W.cells).length, W.sel && W.sel.k].join('|');
    if (key !== MM.last){ MM.last = key; mmDraw(); }
    setTimeout(() => requestAnimationFrame(tick), 100);
  };
  tick();
}

function mmDraw(){
  const cv = MM.cv; if (!cv) return;
  const dpr = window.devicePixelRatio || 1, cw = cv.clientWidth, ch = cv.clientHeight;
  if (!cw || !ch) return;
  if (cv.width !== Math.round(cw * dpr) || cv.height !== Math.round(ch * dpr)){ cv.width = Math.round(cw * dpr); cv.height = Math.round(ch * dpr); }
  const g2 = cv.getContext('2d');
  g2.setTransform(dpr, 0, 0, dpr, 0, 0);
  g2.fillStyle = W.ext ? '#16232b' : '#0e0d0a'; g2.fillRect(0, 0, cw, ch);
  if (!W.key) return;
  const w = mmWhere(), [cx, cy] = mmCentre(), z = mmScale();
  const S = (x, y) => [(x - cx) * z + cw / 2, (cy - y) * z + ch / 2];
  if (W.ext){
    g2.imageSmoothingEnabled = true;
    for (const [k, L] of Object.entries(W.lands)){
      if (!L.img) continue;
      const [gx, gy] = k.split(',').map(Number), [sx, sy] = S(gx * CELL, (gy + 1) * CELL), size = CELL * z;
      if (sx > cw || sy > ch || sx + size < 0 || sy + size < 0) continue;
      g2.drawImage(L.img, sx, sy, size, size);
    }
    g2.strokeStyle = '#ffffff14'; g2.lineWidth = 1;
    for (const k of Object.keys(W.lands)){
      const [gx, gy] = k.split(',').map(Number), [sx, sy] = S(gx * CELL, (gy + 1) * CELL);
      g2.strokeRect(sx, sy, CELL * z, CELL * z);
    }
  }
  // the building and the things: indoors in 3D only your storey (from a little under your feet to the ceiling)
  const feet = w.three && !W.ext ? w.z - 110 : null;
  for (const [ck, r] of visibleRefs()){
    const p = refPos(r);
    if (feet != null && (p[2] < feet - 60 || p[2] > feet + 230)) continue;
    const [sx, sy] = S(p[0], p[1]);
    if (sx < -60 || sy < -60 || sx > cw + 60 || sy > ch + 60) continue;
    const col = TYPE_COLOR[r.type] || '#b0a090', b = r.b, s = r.s || 1;
    const isSel = W.sel && W.sel.k === r.k;
    if (b && Math.max(b[3] - b[0], b[4] - b[1]) * s * z > 3){
      g2.save(); g2.translate(sx, sy); g2.scale(z, -z); g2.rotate(-p[5]); g2.scale(s, s);
      g2.fillStyle = col + (r.arch ? '30' : '70');
      g2.fillRect(b[0], b[1], b[3] - b[0], b[4] - b[1]);
      g2.strokeStyle = isSel ? '#f0cd87' : col + (r.arch ? '66' : 'cc'); g2.lineWidth = (isSel ? 2.5 : 1) / (z * s);
      g2.strokeRect(b[0], b[1], b[3] - b[0], b[4] - b[1]);
      g2.restore();
    } else if (!r.arch){
      g2.fillStyle = col; g2.beginPath(); g2.arc(sx, sy, r.type === 'NPC_' || r.type === 'CREA' ? 3 : 1.6, 0, Math.PI * 2); g2.fill();
    }
  }
  // where you are and which way you face (in 3D), or the flat map's view
  const [px, py] = S(w.x, w.y);
  if (w.three){
    const dx = Math.sin(w.yaw), dy = -Math.cos(w.yaw);
    g2.fillStyle = '#f0cd8733'; g2.beginPath(); g2.moveTo(px, py);
    for (const a of [-0.55, 0.55]){ const c = Math.cos(a), s = Math.sin(a); g2.lineTo(px + (dx * c - dy * s) * 46, py + (dx * s + dy * c) * 46); }
    g2.closePath(); g2.fill();
    g2.fillStyle = '#f0cd87'; g2.strokeStyle = '#000'; g2.lineWidth = 1.5;
    g2.beginPath(); g2.moveTo(px + dx * 9, py + dy * 9); g2.lineTo(px - dy * 5 - dx * 5, py + dx * 5 - dy * 5); g2.lineTo(px + dy * 5 - dx * 5, py - dx * 5 - dy * 5); g2.closePath();
    g2.fill(); g2.stroke();
  } else {
    const vw = W.w / W.cam.z * z, vh = W.h / W.cam.z * z;
    g2.strokeStyle = '#f0cd87'; g2.lineWidth = 1.5; g2.strokeRect(px - vw / 2, py - vh / 2, vw, vh);
  }
}

// from the minimap's pixels to the world
function mmWorld(ev){
  const cv = MM.cv, rc = cv.getBoundingClientRect(), [cx, cy] = mmCentre(), z = mmScale();
  return [(ev.clientX - rc.left - rc.width / 2) / z + cx, cy - (ev.clientY - rc.top - rc.height / 2) / z];
}

function mmBind(cv){
  cv.onmousedown = ev => {
    if (ev.button !== 0) return;
    MM.drag = {x: ev.clientX, y: ev.clientY, at: mmCentre(), moved: false};
    const up = e2 => {
      document.removeEventListener('mousemove', mv); document.removeEventListener('mouseup', up);
      const D = MM.drag; MM.drag = null;
      if (D && !D.moved) mmGo(mmWorld(e2));
    };
    const mv = e2 => {
      const D = MM.drag; if (!D) return;
      const dx = e2.clientX - D.x, dy = e2.clientY - D.y;
      if (!D.moved && Math.hypot(dx, dy) < 4) return;
      D.moved = true; MM.follow = false;
      const z = mmScale();
      MM.at = [D.at[0] - dx / z, D.at[1] + dy / z];
      mmDraw();
    };
    document.addEventListener('mousemove', mv); document.addEventListener('mouseup', up);
  };
  cv.onwheel = ev => {
    ev.preventDefault();
    const f = ev.deltaY < 0 ? 1.25 : 1 / 1.25;
    if (W.ext) MM.zOut = Math.max(0.002, Math.min(0.2, MM.zOut * f)); else MM.zIn = Math.max(0.02, Math.min(1.2, MM.zIn * f));
    mmDraw();
  };
  cv.onmousemove = ev => { if (!MM.drag) mmHover(mmWorld(ev)); };
  cv.onmouseleave = () => { const t = MM.it && MM.it.el.querySelector('.mm-tip'); if (t) t.textContent = ''; };
}

// the line under the map: the thing under the pointer (the nearest within a few pixels), else the cell outdoors
function mmHover([x, y]){
  const t = MM.it && MM.it.el.querySelector('.mm-tip'); if (!t) return;
  const w = mmWhere(), feet = w.three && !W.ext ? w.z - 110 : null, z = mmScale();
  let best = null, bd = 9 / z;
  for (const [ck, r] of visibleRefs()){
    if (r.arch) continue;
    const p = refPos(r);
    if (feet != null && (p[2] < feet - 60 || p[2] > feet + 230)) continue;
    const d = Math.hypot(p[0] - x, p[1] - y);
    if (d < bd){ bd = d; best = r; }
  }
  if (best){ t.textContent = (best.name ? best.name + ' · ' : '') + best.id; return; }
  if (W.ext){
    const k = extKey(Math.floor(x / CELL), Math.floor(y / CELL)), c = W.cells[k];
    t.textContent = ((c && c.name) || (W.info && W.info.region) || '') + ' (' + Math.floor(x / CELL) + ', ' + Math.floor(y / CELL) + ')';
  } else t.textContent = '';
}

// go there: in 3D the camera moves (the same height over the ground outdoors, the same floor indoors), else the map
function mmGo([x, y]){
  const w = mmWhere();
  if (w.three){
    let z = w.z;
    if (W.ext && typeof v3GroundAt === 'function'){
      const g0 = v3GroundAt(w.x, w.y), g1 = v3GroundAt(x, y);
      if (g0 != null && g1 != null) z = g1 + Math.max(60, w.z - g0);
    }
    V3.pos.set(x - V3.origin[0], y - V3.origin[1], z - V3.origin[2]);
    if (typeof v3Refresh === 'function') v3Refresh();
    // (outdoors the cells round the new spot load as the map's would)
    if (W.ext && typeof loadAround === 'function') loadAround(Math.floor(x / CELL), Math.floor(y / CELL));
  } else {
    W.cam.x = x; W.cam.y = y; drawMap();
    if (W.ext && typeof recentre === 'function') recentre();
  }
  MM.follow = true; MM.at = null; MM.last = '';
  mmDraw();
}

if (typeof CF_ACT !== 'undefined') CF_ACT.push({id: 'minimap', label: 'Minimap (where you are; click it to go there)', keys: [], world: true,
  run: () => { if (typeof worldPanelsInit === 'function') worldPanelsInit(); PNL.show('world', 'minimap'); }});
