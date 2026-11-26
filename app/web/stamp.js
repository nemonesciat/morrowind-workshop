// Placing as a stamp, and nudging. With ✚ Place on in an Object list, a click on a row picks the thing up: a
// see-through copy follows the mouse in 3D and every click puts one down. While placing: the wheel turns it
// (Shift: fine), X or Y held + wheel tilts it, Alt + wheel sizes it, Backspace sets it straight again; the next
// one keeps the last turn, tilt and size. Lean with the ground stands it on the slope; Random turn turns each one
// its own way. Afterwards the arrow keys nudge what's selected over the ground (the way the camera looks,
// along the grid), Page Up and Page Down raise and lower it, , and . turn it; Shift goes further. A run of nudges
// is one Undo. (The user, 2026-11-26: "the selected item draws a preview on the screen, and places with a click.
// and certain hotkeys apply easy to access transformations to it for fine tuning")
const STAMP = {on: false, lean: false, rand: false, rx: 0, ry: 0, s: 1};
try { const k = JSON.parse(localStorage.getItem('ws-stamp') || '{}'); STAMP.on = !!k.on; STAMP.lean = !!k.lean; STAMP.rand = !!k.rand; } catch (e){}
function stampSave(){ try { localStorage.setItem('ws-stamp', JSON.stringify({on: STAMP.on, lean: STAMP.lean, rand: STAMP.rand})); } catch (e){} }

const STAMP_WRAP = a => Math.atan2(Math.sin(a), Math.cos(a));
// the turn, tilt and size the preview and the next one take (h: what the mouse is over, for leaning)
function stampNow(h){
  let rx = STAMP.rx, ry = STAMP.ry;
  const n = h && h.normal;
  if (STAMP.lean && n && n.z > 0.5){
    // (the thing's up along the ground's: the game's turns are applied x, then y, then z)
    rx += -Math.atan2(-n.y, n.z);
    ry += -Math.asin(Math.max(-1, Math.min(1, n.x)));
  }
  return {rx, ry, s: STAMP.s};
}
// the wheel while placing: X or Y held tilts, Alt sizes; anything else is the turn, as before
function stampWheel(e){
  if (!V3.ghost || W.mode !== 'place') return false;
  const held = V3.held || {}, dir = e.deltaY < 0 ? 1 : -1, step = (e.shiftKey ? 1 : 15) * Math.PI / 180;
  if (held.x) STAMP.rx = STAMP_WRAP(STAMP.rx + dir * step);
  else if (held.y) STAMP.ry = STAMP_WRAP(STAMP.ry + dir * step);
  else if (e.altKey) STAMP.s = Math.max(0.5, Math.min(2, Math.round(STAMP.s * (dir > 0 ? 1.05 : 1 / 1.05) * 100) / 100));
  else return false;
  stampRedraw();
  return true;
}
function stampRedraw(){ if (V3.lastMouse && typeof v3GhostMove === 'function') v3GhostMove(V3.lastMouse); if (typeof v3PlaceHint === 'function') v3PlaceHint(); }
function stampReset(){
  STAMP.rx = STAMP.ry = 0; STAMP.s = 1;
  if (V3.ghost) V3.ghost.yaw = 0;
  stampRedraw();
}
// after each one is put down: Random turn gives the next its own way
function stampPlaced(){
  if (STAMP.rand && V3.ghost){ V3.ghost.yaw = Math.random() * Math.PI * 2; stampRedraw(); }
}
// a short line of what the keys do, for the placing banner
function stampHint(){
  const bits = [];
  if (STAMP.rx || STAMP.ry) bits.push(`tilt ${Math.round(STAMP.rx * 180 / Math.PI)}°/${Math.round(STAMP.ry * 180 / Math.PI)}°`);
  if (STAMP.s !== 1) bits.push('×' + STAMP.s);
  return (bits.length ? ' (' + bits.join(', ') + ')' : '') + '; <b>X</b>/<b>Y</b> + wheel tilts, <b>Alt</b> + wheel sizes, <b>Backspace</b> straightens';
}
window.addEventListener('keydown', e => {
  ND.shift = e.shiftKey;
  if (e.key === 'Backspace' && W.mode === 'place' && typeof V3 !== 'undefined' && V3.on && V3.ghost && !(typeof cfTyping === 'function' && cfTyping(e))){
    e.preventDefault(); e.stopPropagation(); stampReset();
  }
}, true);
window.addEventListener('keyup', e => { ND.shift = e.shiftKey; }, true);

// ----- nudging what's selected
const ND = {pend: new Map(), t: null, shift: false};
function ndSel(){ return typeof selectionRefs === 'function' ? selectionRefs() : (W.sel ? [[W.sel.cell, findRef(W.sel.cell, W.sel.k)]].filter(x => x[1]) : []); }
// forward and right along the grid: the world's axis nearest the way the camera looks (north and east on the map)
function ndAxes(){
  let fx = 0, fy = 1;
  if (typeof V3 !== 'undefined' && V3.on){
    const a = V3.yaw;
    if (Math.abs(Math.sin(a)) > Math.abs(Math.cos(a))){ fx = Math.sign(Math.sin(a)); fy = 0; } else { fx = 0; fy = Math.sign(Math.cos(a)) || 1; }
  }
  return {f: [fx, fy], r: [fy, -fx]};
}
function ndDo(dx, dy, dz, dr){
  const list = ndSel(); if (!list.length) return false;
  for (const [cell, r] of list){
    if (!r || !r.p) continue;
    r.p[0] += dx; r.p[1] += dy; r.p[2] += dz;
    if (dr) r.p[5] = STAMP_WRAP((r.p[5] || 0) + dr);
    ND.pend.set(cell + '|' + r.k, {cell, ref: r.k, r});
  }
  if (typeof V3 !== 'undefined' && V3.on) v3Refresh(); else drawMap();
  clearTimeout(ND.t); ND.t = setTimeout(ndFlush, 700);
  return true;
}
function ndStep(){ return (typeof V3 !== 'undefined' && V3.grid ? V3.grid : 8) * (ND.shift ? 8 : 1); }
function ndMove(f, rt){ const A = ndAxes(), s = ndStep(); return ndDo((A.f[0] * f + A.r[0] * rt) * s, (A.f[1] * f + A.r[1] * rt) * s, 0, 0); }
function ndRaise(d){ return ndDo(0, 0, d * ndStep(), 0); }
function ndTurn(d){ const a = (typeof V3 !== 'undefined' && V3.angle ? V3.angle : 5) * (ND.shift ? 3 : 1); return ndDo(0, 0, 0, d * a * Math.PI / 180); }
async function ndFlush(){
  const moves = [...ND.pend.values()]; ND.pend.clear();
  if (!moves.length) return;
  if (moves.length === 1){
    const m = moves[0];
    await refAction('/api/ref/move', {cell: m.cell, ref: m.ref, p: m.r.p.slice(), s: m.r.s || 1}, m.cell, m.ref, 'Nudged ' + (m.r.name || m.r.id));
  } else {
    await groupAction('/api/group/move', {moves: moves.map(m => ({cell: m.cell, ref: m.ref, p: m.r.p.slice(), s: m.r.s || 1}))}, `Nudged ${moves.length} things`);
  }
  if (typeof renderWside === 'function') renderWside();
}
