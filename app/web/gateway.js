// A way up to a gate or a door (gateway.py): right-click it outdoors, "Make a way up to it". The way the Workshop
// would make is drawn over the ground first (a level landing, then one even ramp to a road or to open ground) with
// its steepness in the top bar; Make it lays it, a click on the ground starts it from there instead, Esc gives it up.
// (The user, 2026-11-13, of gates: "I notice a lot of them have very steep approaches".)
const GW = {on: false, cell: null, key: null, to: null, res: null, line: null, busy: false};

function gwMenuItem(ck, r){
  // (outdoors: a door, or a wall's gate or arch)
  if (!ck || !ck.startsWith('#')) return null;
  if (!(r.type === 'DOOR' || (r.arch && /gate|arch|portcullis|entr/i.test(r.id)))) return null;
  return {label: '◢ Make a way up to it…', act: () => gwStart(ck, r.k)};
}
function gwStart(cell, key){
  gwStop();
  Object.assign(GW, {on: true, cell, key, to: null, res: null});
  gwLook();
}
function gwStop(){
  if (!GW.on && !GW.line) return;
  GW.on = false; GW.res = null; GW.to = null;
  if (GW.line) GW.line.visible = false;
  if (typeof setBanner === 'function') setBanner('');
  if (typeof V3 !== 'undefined' && V3.on) v3Refresh();
}
async function gwLook(){
  if (!GW.on) return;
  setBanner('Finding a way up…');
  let r;
  try { r = await post('/api/wayup/look', {cell: GW.cell, key: GW.key, to: GW.to}); }
  catch (e){ toast(e.message, true); return gwStop(); }
  if (!GW.on) return;
  if (r.none){
    GW.res = null; gwDraw();
    // (nothing to make at all: said and done. No way found: the user's own start may give one)
    if (/gentle as it is|no longer there|no outline|no land/i.test(r.none)){ toast(r.none); return gwStop(); }
    setBanner(`${esc(r.none)} <b>Esc</b> gives it up.`);
    return;
  }
  GW.res = r; gwDraw();
  const steep = r.deg > 27;
  setBanner(`Way up: <b${steep ? ' style="color:#ff8a7a"' : ''}>${r.deg}°</b>, ${Math.abs(r.rise)} ${r.rise >= 0 ? 'up' : 'down'} from the ${r.to === 'spot' ? 'spot you clicked' : r.to === 'road' ? 'road' : 'open ground'}. <button class="btn sm primary" id="gw-make">Make it</button> Click the ground to start it elsewhere. Esc gives it up.`);
  const b = document.querySelector('#gw-make'); if (b) b.onclick = e => { e.stopPropagation(); gwMake(); };
}
// the way as it would be made, over the ground in the 3D view: its two edges
function gwDraw(){
  if (typeof V3 === 'undefined' || !V3.on || !GW.res){ if (GW.line) GW.line.visible = false; if (typeof V3 !== 'undefined' && V3.on) v3Refresh(); return; }
  const T = THREE, O = V3.origin, P = GW.res.pts, half = GW.res.half, left = [], right = [];
  for (let i = 0; i < P.length; i++){
    const a = P[Math.max(0, i - 1)], b = P[Math.min(P.length - 1, i + 1)], d = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1;
    const nx = -(b[1] - a[1]) / d * half, ny = (b[0] - a[0]) / d * half, z = P[i][2] + 8 - O[2];
    left.push(P[i][0] + nx - O[0], P[i][1] + ny - O[1], z);
    right.unshift(P[i][0] - nx - O[0], P[i][1] - ny - O[1], z);
  }
  if (!GW.line || GW.line.parent !== V3.scene){
    GW.line = new T.LineLoop(new T.BufferGeometry(), new T.LineBasicMaterial({color: 0xffe08a, depthTest: false, transparent: true}));
    GW.line.renderOrder = 21; GW.line.frustumCulled = false; V3.scene.add(GW.line);
  }
  GW.line.geometry.dispose(); GW.line.geometry = new T.BufferGeometry();
  GW.line.geometry.setAttribute('position', new T.BufferAttribute(new Float32Array(left.concat(right)), 3));
  GW.line.material.color.set(GW.res.deg > 27 ? 0xff5a4a : 0xffe08a);
  GW.line.visible = true;
  v3Refresh();
}
async function gwMake(){
  if (!GW.on || !GW.res || GW.busy) return;
  GW.busy = true;
  setBanner('Making the way…');
  let r;
  try { r = await post('/api/wayup', {cell: GW.cell, key: GW.key, to: GW.to}); }
  catch (e){ GW.busy = false; toast(e.message, true); return gwStop(); }
  GW.busy = false;
  gwStop();
  if (r.none) return toast(r.none);
  toast(`Way made: ${r.deg}°${r.cleared ? `, ${r.cleared} rock${r.cleared === 1 ? '' : 's'} and plants cleared off it` : ''}. One Undo takes it back.`);
  // (the ground and what followed it, read again, as the ground brush does)
  W.lands = {};
  for (const k of Object.keys(W.cells)) if (W.cells[k] && W.cells[k].exists) await worldReloadCell(k);
  if (typeof v3LandsReload === 'function') v3LandsReload();
  if (typeof afterChange === 'function') afterChange();
  drawMap(); if (V3.on) v3Refresh();
}
// a click on the ground in the 3D view while a way is shown: it starts from there (world3d.js asks first)
function gwClick3(e){
  if (!GW.on || GW.busy || e.button !== 0) return false;
  const at = typeof v3Brush === 'function' ? v3Brush(e) : null;
  if (at){ GW.to = [at[0], at[1]]; gwLook(); }
  return true;
}
window.addEventListener('keydown', e => {
  if (!GW.on) return;
  if (e.target && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
  if (e.key === 'Escape'){ e.preventDefault(); e.stopImmediatePropagation(); gwStop(); }
  else if (e.key === 'Enter' && GW.res){ e.preventDefault(); e.stopImmediatePropagation(); gwMake(); }
}, true);
