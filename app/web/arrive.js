// Where a door puts you: the arrival pick, on the map and in 3D. Press where the player lands and drag the way they
// face; a plain click faces away from the nearest door, into the place. The spot under the mouse shows as a figure
// with an arrow, and the door's arrival now as a faint one, so you see what you change. The server stands the player
// on the floor there (doors.stand_spot): the map has no height, and before this a pick took the top of whatever stood
// there and always faced north, "random effects, rarely what I want" (StingDR, 2026-11-02).
const AR = {press: null, aim: null, mark3: null, cur3: null};

// the door's arrival now, read when the pick starts (the door's own place is gone once the other one opens)
{
  let arriving = W.arriving;
  Object.defineProperty(W, 'arriving', {configurable: true, get: () => arriving, set: v => {
    arriving = v;
    if (v && v.cur === undefined && v.cell){ const r = findRef(v.cell, v.ref); v.cur = r && r.to && r.to.key === v.target ? r.to : null; }
  }});
}
// (shown when it lands in the place that is open)
function arCurrent(){
  const A = W.arriving;
  return A && A.cur && W.key === A.target ? A.cur : null;
}
// the way a plain click faces: away from the nearest door within 600, into the place (as the server does)
function arAway(x, y){
  let best = null, bd = 600;
  for (const [, r] of visibleRefs()){
    if (r.type !== 'DOOR') continue;
    const d = Math.hypot(r.p[0] - x, r.p[1] - y);
    if (d < bd){ bd = d; best = r; }
  }
  return best ? Math.atan2(x - best.p[0], y - best.p[1]) : 0;
}
function arFacing(rz){
  const deg = ((rz * 180 / Math.PI) % 360 + 360) % 360;
  return ['north', 'north-east', 'east', 'south-east', 'south', 'south-west', 'west', 'north-west'][Math.round(deg / 45) % 8];
}

// ----- the map
function arDown(e){
  if (W.mode !== 'arrive') return false;
  const hit = hitTest(e.offsetX, e.offsetY);
  if (hit && hit[1].type === 'DOOR' && typeof arriveDoor === 'function'){ arriveDoor(hit[0], hit[1].k); return true; }
  const [wx, wy] = toWorld(e.offsetX, e.offsetY);
  AR.press = {sx: e.offsetX, sy: e.offsetY, x: wx, y: wy}; AR.aim = null;
  return true;
}
function arMove(e){
  if (W.mode !== 'arrive') return false;
  W.mouse = [e.offsetX, e.offsetY];
  const P = AR.press;
  if (P && Math.hypot(e.offsetX - P.sx, e.offsetY - P.sy) > 8){ const [wx, wy] = toWorld(e.offsetX, e.offsetY); AR.aim = Math.atan2(wx - P.x, wy - P.y); }
  drawMap();
  return true;
}
function arUp(){
  const P = AR.press; if (!P) return false;
  AR.press = null;
  // (the map has no height: the storey shown under Floors, else the server takes the nearest door's)
  if (W.mode === 'arrive') arriveAt(P.x, P.y, !W.ext && W.cut != null ? W.cut - 60 : null, AR.aim);
  AR.aim = null;
  return true;
}
function arFigure(g, x, y, rz, faint){
  const [sx, sy] = toScreen(x, y), r = Math.max(7, Math.min(16, 32 * W.cam.z));
  g.save(); g.globalAlpha = faint ? 0.5 : 1;
  g.fillStyle = faint ? '#9fb4c855' : '#7fd4ff55'; g.strokeStyle = faint ? '#9fb4c8' : '#7fd4ff'; g.lineWidth = 2;
  g.beginPath(); g.arc(sx, sy, r, 0, Math.PI * 2); g.fill(); g.stroke();
  const ax = Math.sin(rz), ay = -Math.cos(rz), L = r + 16;
  g.beginPath(); g.moveTo(sx + ax * r * 0.4, sy + ay * r * 0.4); g.lineTo(sx + ax * L, sy + ay * L); g.stroke();
  g.beginPath(); g.moveTo(sx + ax * (L + 4), sy + ay * (L + 4));
  g.lineTo(sx + ax * (L - 6) - ay * 6, sy + ay * (L - 6) + ax * 6); g.lineTo(sx + ax * (L - 6) + ay * 6, sy + ay * (L - 6) - ax * 6);
  g.closePath(); g.fillStyle = g.strokeStyle; g.fill();
  if (faint){ g.font = '11px sans-serif'; g.fillStyle = '#c8d4de'; g.fillText('now', sx + r + 4, sy - r); }
  g.restore();
}
function arDraw(g){
  if (W.mode !== 'arrive') return;
  const c = arCurrent(); if (c) arFigure(g, c.x, c.y, c.rz || 0, true);
  const P = AR.press;
  if (P) arFigure(g, P.x, P.y, AR.aim != null ? AR.aim : arAway(P.x, P.y));
  else if (W.mouse){ const [x, y] = toWorld(W.mouse[0], W.mouse[1]); arFigure(g, x, y, arAway(x, y)); }
}

// ----- the 3D view
function ar3Figure(color, opacity){
  const T = THREE, grp = new T.Group(), mat = new T.MeshBasicMaterial({color, transparent: true, opacity, depthTest: false});
  const body = new T.Mesh(new T.CylinderGeometry(24, 24, 120, 16, 1, true), mat);
  body.rotation.x = Math.PI / 2; body.position.z = 60; grp.add(body);
  const tip = new T.Mesh(new T.ConeGeometry(18, 46, 12), mat);
  tip.position.set(0, 58, 30); grp.add(tip);                    // (a cone points along +y: north at rz 0)
  grp.renderOrder = 999; grp.traverse(o => { o.renderOrder = 999; });
  V3.scene.add(grp);
  return grp;
}
function ar3Put(grp, x, y, z, rz){
  grp.position.set(x - V3.origin[0], y - V3.origin[1], z - V3.origin[2]);
  grp.rotation.z = -rz;
  grp.visible = true;
}
function ar3Clear(){
  for (const k of ['mark3', 'cur3']) if (AR[k]){ V3.scene && V3.scene.remove(AR[k]); AR[k] = null; }
}
// a spot on the floor under the mouse: off a wall that was clicked, out along its face
function ar3Spot(e){
  const h = v3Pick(e, true);
  if (!h || !h.world) return null;
  const p = h.world.slice(), n = h.normal;
  if (n && Math.abs(n.z) < 0.5){ p[0] += n.x * 40; p[1] += n.y * 40; p[2] -= 40; }
  return {h, p};
}
function arDown3(e){
  if (W.mode !== 'arrive' || e.button !== 0) return false;
  const s = ar3Spot(e);
  if (s && s.h.obj && s.h.obj.r && s.h.obj.r.type === 'DOOR' && typeof arriveDoor === 'function'){ arriveDoor(s.h.obj.ck, s.h.obj.r.k); return true; }
  if (!s){ toast('Click on the floor or ground where the player should arrive.'); return true; }
  AR.press = {sx: e.clientX, sy: e.clientY, x: s.p[0], y: s.p[1], z: s.p[2], three: true}; AR.aim = null;
  return true;
}
function arMove3(e){
  if (W.mode !== 'arrive' || !V3.on) return;
  const P = AR.press && AR.press.three ? AR.press : null;
  let x, y, z, rz;
  if (P){
    const dx = e.clientX - P.sx, dy = e.clientY - P.sy;
    if (Math.hypot(dx, dy) > 8){
      // (the drag on screen turned to the ground: right is the camera's right, up is the way it looks)
      const c = Math.cos(V3.yaw), s = Math.sin(V3.yaw);
      AR.aim = Math.atan2(dx * c - dy * s, -dx * s - dy * c);
    }
    x = P.x; y = P.y; z = P.z; rz = AR.aim != null ? AR.aim : arAway(x, y);
  } else {
    const s = ar3Spot(e); if (!s) return;
    [x, y, z] = s.p; rz = arAway(x, y);
  }
  if (!AR.mark3) AR.mark3 = ar3Figure(0x7fd4ff, 0.4);
  ar3Put(AR.mark3, x, y, z, rz);
  const c = arCurrent();
  if (c){ if (!AR.cur3) AR.cur3 = ar3Figure(0x9fb4c8, 0.3); ar3Put(AR.cur3, c.x, c.y, c.z - 10, c.rz || 0); }
}
function arUp3(){
  const P = AR.press; if (!P || !P.three) return false;
  AR.press = null; ar3Clear();
  if (W.mode === 'arrive') arriveAt(P.x, P.y, P.z, AR.aim);
  AR.aim = null;
  return true;
}
window.addEventListener('mousemove', arMove3);
window.addEventListener('mouseup', e => { if (e.button === 0 && AR.press && AR.press.three) arUp3(); });
function arBanner(){
  setBanner(`Click where the player arrives through <b>${esc((W.arriving || {}).name || 'the door')}</b>, or press there and drag the way they face. Click a door to link the two. Esc to cancel.${V3.on ? ' <button class="btn sm" id="ar-cam" title="Arrive exactly where the 3D camera stands, on the floor under it, facing exactly the way it looks">📷 Where the camera is</button>' : ''}`, 'arrive');
}
// (the pick over: no figures left behind; the map and 3D switched during it: the banner follows)
setInterval(() => {
  if (W.mode !== 'arrive'){ if (AR.mark3 || AR.cur3) ar3Clear(); AR.press = null; return; }
  if (!!V3.on !== !!$('#ar-cam') && $('#mapbanner').style.display !== 'none') arBanner();
}, 500);
// 📷 on the banner (3D): arrive exactly where the camera stands, on the floor under it, facing the way it looks, for
// direct control (the user, 2026-11-02)
function arCamera(){
  if (W.mode !== 'arrive' || !V3.on || !V3.pos) return;
  const x = V3.pos.x + V3.origin[0], y = V3.pos.y + V3.origin[1], z = V3.pos.z + V3.origin[2];
  ar3Clear();
  arriveAt(x, y, z - 60, ((V3.yaw % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI));
}
document.addEventListener('click', e => { if (e.target && e.target.id === 'ar-cam'){ e.preventDefault(); arCamera(); } });
