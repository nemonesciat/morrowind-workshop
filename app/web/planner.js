// ---------- Room planner for Build from pieces ----------
// Rooms are rectangles of floor tiles on a grid, on up to five floors. Drag a room to move it, drag its
// corners or the tabs on its sides to resize it. Click the wall between two rooms to put a doorway in
// it (or take it out again), click an outside wall to put the way out there. The stairs are worked out
// by the Workshop from the style's own stair pieces and drawn on both floors they join; drag them (or
// "Place by hand") to put them somewhere yourself, and they stay there. R turns them.
// "3D" shows every floor stacked up like a doll's house; drag to turn it.
const PL_FLOORS = [[2, 'Top floor'], [1, 'Upstairs'], [0, 'Ground floor'], [-1, 'Cellar'], [-2, 'Lower cellar']];
const PL_NAMES = ['Bedroom', 'Kitchen', 'Hall', 'Storeroom', 'Study', 'Dining room', 'Library', 'Shop', 'Shrine', 'Guard room', 'Bath', 'Hallway'];
const PL_SIZES = {Bedroom: [3, 3], Kitchen: [3, 2], Hall: [2, 4], Storeroom: [2, 2], Study: [2, 3], 'Dining room': [3, 3], Library: [3, 3],
  Shop: [4, 3], Shrine: [2, 3], 'Guard room': [3, 3], Bath: [2, 2], Hallway: [1, 4]};
const PL_COLS = ['#7a5a26', '#4c6634', '#2f5a70', '#6e3c5c', '#6b6526', '#3c4c78', '#7a4a2e', '#2f6b5e', '#6b3434', '#56607a'];
const PL = {view: 'plan', floor: 0, sel: null, hover: null, drag: null, z: 34, ox: 0, oy: 0, yaw: 0.7, tilt: 0.55, hist: [], fut: [], res: null, resKey: null};
const plFloorName = f => (PL_FLOORS.find(x => x[0] === f) || [0, 'Floor ' + f])[1];
let plId = 1;
const plNewId = () => 'r' + (plId++) + Math.random().toString(36).slice(2, 5);

// ----- the plan itself (kept in CR.plan, and as a draft in this browser)
function plData(){ return CR.plan; }
function plDefault(){
  const a = {id: plNewId(), name: 'Main room', x: 0, y: 0, w: 3, h: 3, floor: 0};
  return {rooms: [a], doors: [], exit: {room: a.id, x: 1, y: 0, side: 'S'}, stairs: []};
}
function plLoad(){
  if (CR.plan) return;
  try { const s = JSON.parse(localStorage.getItem('ws-plan') || 'null'); if (s && s.rooms && s.rooms.length) CR.plan = s; } catch (e){}
  if (!CR.plan) CR.plan = plDefault();
  for (const r of CR.plan.rooms) if (!r.id) r.id = plNewId();
}
function plSave(){ try { localStorage.setItem('ws-plan', JSON.stringify(CR.plan)); } catch (e){} }
function plSnap(){ PL.hist.push(JSON.stringify(CR.plan)); if (PL.hist.length > 80) PL.hist.shift(); PL.fut = []; }
function plUndo(){ if (!PL.hist.length) return; PL.fut.push(JSON.stringify(CR.plan)); CR.plan = JSON.parse(PL.hist.pop()); plChanged(); }
function plRedo(){ if (!PL.fut.length) return; PL.hist.push(JSON.stringify(CR.plan)); CR.plan = JSON.parse(PL.fut.pop()); plChanged(); }

// ----- what is where
const plRoom = id => plData().rooms.find(r => r.id === id);
// a room's tiles: its rectangle, less the ones taken away (cut), with the ones added on (add), both kept
// from its corner so they move, resize and turn with it
function plHas(r, x, y){
  const dx = x - r.x, dy = y - r.y;
  if (dx >= 0 && dx < r.w && dy >= 0 && dy < r.h) return !(r.cut || []).some(t => t[0] === dx && t[1] === dy);
  return (r.add || []).some(t => t[0] === dx && t[1] === dy);
}
function plTiles(r){
  const out = [];
  for (let x = 0; x < r.w; x++) for (let y = 0; y < r.h; y++) if (!(r.cut || []).some(t => t[0] === x && t[1] === y)) out.push([r.x + x, r.y + y]);
  for (const t of r.add || []) if (!(t[0] >= 0 && t[0] < r.w && t[1] >= 0 && t[1] < r.h) && !out.some(o => o[0] === r.x + t[0] && o[1] === r.y + t[1])) out.push([r.x + t[0], r.y + t[1]]);
  return out;
}
const plShaped = r => !!((r.add && r.add.length) || (r.cut && r.cut.length));
function plRoomAt(x, y, f, skip){ return plData().rooms.find(r => r.floor === f && r !== skip && plHas(r, x, y)); }
const PL_STEP = {N: [0, 1], E: [1, 0], S: [0, -1], W: [-1, 0]}, PL_OPP = {N: 'S', S: 'N', E: 'W', W: 'E'};
function plShared(a, b){
  // edges between rooms a and b: [{x, y, side}] with the tile in a
  if (a.floor !== b.floor) return [];
  const out = [];
  for (const [x, y] of plTiles(a))
    for (const [s, [dx, dy]] of Object.entries(PL_STEP)) if (plHas(b, x + dx, y + dy)) out.push({x, y, side: s});
  return out;
}
function plOutside(r){
  const out = [];
  for (const [x, y] of plTiles(r))
    for (const [s, [dx, dy]] of Object.entries(PL_STEP)){
      const nx = x + dx, ny = y + dy;
      if (plHas(r, nx, ny)) continue;
      if (!plRoomAt(nx, ny, r.floor)) out.push({x, y, side: s});
    }
  return out;
}
// tiles in one piece (4 sides touching)
function plJoined(tiles){
  if (tiles.length < 2) return true;
  const key = t => t[0] + ',' + t[1], all = new Set(tiles.map(key)), seen = new Set([key(tiles[0])]), todo = [tiles[0]];
  while (todo.length){ const [x, y] = todo.pop(); for (const [dx, dy] of Object.values(PL_STEP)){ const k = (x + dx) + ',' + (y + dy); if (all.has(k) && !seen.has(k)){ seen.add(k); todo.push([x + dx, y + dy]); } } }
  return seen.size === all.size;
}
const plMid = list => list.slice().sort((p, q) => p.x - q.x || p.y - q.y)[Math.floor((list.length - 1) / 2)];
const plSameEdge = (d, e) => (d.x === e.x && d.y === e.y && d.side === e.side) ||
  (d.x + PL_STEP[d.side][0] === e.x && d.y + PL_STEP[d.side][1] === e.y && PL_OPP[d.side] === e.side);
function plOverlaps(){
  const seen = {}, bad = new Set();
  for (const r of plData().rooms) for (const [x, y] of plTiles(r)){
    const k = x + ',' + y + ',' + r.floor;
    if (seen[k]){ bad.add(seen[k]); bad.add(r.id); } else seen[k] = r.id;
  }
  return bad;
}
// unique names, as the Workshop needs them (and Auto-furnish goes by them)
function plNames(){
  const seen = {}, out = {};
  plData().rooms.forEach((r, n) => {
    let name = (r.name || '').trim() || 'Room ' + (n + 1);
    const k = name.toLowerCase();
    if (seen[k]){ seen[k]++; name += ' ' + seen[k]; } else seen[k] = 1;
    out[r.id] = name;
  });
  return out;
}

// ----- keep doors, the way out and stairs sensible after every change
function plFix(){
  const P = plData();
  P.doors = P.doors.filter(d => {
    const a = plRoom(d.a), b = plRoom(d.b);
    if (!a || !b) return false;
    const sh = plShared(a, b);
    if (!sh.length) return false;
    if (d.kind !== 'open' && !sh.some(e => plSameEdge(d, e))){ const m = plMid(sh); Object.assign(d, m); }
    return true;
  });
  // a room standing alone next to others gets a doorway to the one it shares most wall with
  P.walls = (P.walls || []).filter(w => plRoom(w[0]) && plRoom(w[1]));
  for (const r of P.rooms){
    if (P.doors.some(d => d.a === r.id || d.b === r.id) || P.walls.some(w => w.includes(r.id))) continue;
    let best = null;
    for (const o of P.rooms){ if (o === r) continue; const sh = plShared(r, o); if (sh.length && (!best || sh.length > best[1].length)) best = [o, sh]; }
    if (best) P.doors.push({a: r.id, b: best[0].id, kind: 'door', ...plMid(best[1])});
  }
  // the way out: on an outside wall of its room (the ground floor if it can)
  const ex = P.exit, er = ex && plRoom(ex.room);
  if (!er || !plOutside(er).some(e => e.x === ex.x && e.y === ex.y && e.side === ex.side) || plExitBlocked(ex, er)){
    const ground = P.rooms.filter(r => r.floor === 0);
    const r = er && plOutside(er).length ? er : (ground[0] || P.rooms[0]);
    const all = r ? plOutside(r) : [], clear = r ? all.filter(e => !plExitBlocked(e, r)) : [];
    const outs = clear.length ? clear : all;
    const want = (ex && ex.side) || 'S', pick = outs.filter(e => e.side === want);
    P.exit = outs.length ? {room: r.id, ...plMid(pick.length ? pick : outs)} : null;
  }
  P.stairs = (P.stairs || []).filter(s => { const a = plRoom(s.lo), b = plRoom(s.hi); return a && b && b.floor === a.floor + 1; });
  // stairs put by hand, and "beside the rooms": only between two floors that both have rooms
  const has = f => P.rooms.some(r => r.floor === f);
  for (const k of ['stairPins', 'stairOut']){ P[k] = P[k] || {}; for (const f of Object.keys(P[k])) if (!has(+f) || !has(+f + 1)) delete P[k][f]; }
}
function plChanged(){ plFix(); plSave(); plRender(); plSide(); plAsk(); if (typeof bShells === 'function' && CR.bstyles){ clearTimeout(bShellT); bShellT = setTimeout(bShells, 600); } }

// ----- what the Workshop gets (same shape as before: rooms, doors, exit, stairs)
function bLayout(){
  const P = plData(), N = plNames();
  const first = P.rooms.find(r => r.floor === 0) || P.rooms[0];
  return {
    rooms: P.rooms.map(r => Object.assign({name: N[r.id], x: r.x, y: r.y, w: r.w, h: r.h, floor: r.floor},
      plShaped(r) ? {add: (r.add || []).map(t => [r.x + t[0], r.y + t[1]]), cut: (r.cut || []).map(t => [r.x + t[0], r.y + t[1]])} : {})),
    doors: P.doors.map(d => d.kind === 'open' ? {rooms: [N[d.a], N[d.b]], kind: 'open'} : {rooms: [N[d.a], N[d.b]], at: {x: d.x, y: d.y, side: d.side}}),
    exit: P.exit ? {room: N[P.exit.room], side: P.exit.side, x: P.exit.x, y: P.exit.y} : {room: N[first.id], side: 'S'},
    stairs: plStairsOut(N),
    floors_as: P.join || 'auto',
  };
}
// for each floor's stairs up: which rooms they join, where they were put by hand, beside the rooms
function plStairsOut(N){
  const P = plData(), by = {};
  const at = f => (by[f] = by[f] || {floor: f});
  for (const s of P.stairs || []){ const a = plRoom(s.lo); if (a) at(a.floor).rooms = [N[s.lo], N[s.hi]]; }
  for (const [f, p] of Object.entries(P.stairPins || {})) at(+f).at = {x: p.x, y: p.y, up: p.up};
  for (const [f, v] of Object.entries(P.stairOut || {})) if (v) at(+f).outside = true;
  return Object.values(by);
}
// the stairs to draw: the Workshop's answer, or (dragging, placing, or when it said no) where you put them
const PL_TURN = {N: 'E', E: 'S', S: 'W', W: 'N'};
function plPinTiles(p, len){ const d = PL_STEP[p.up]; return Array.from({length: len}, (_, k) => [p.x + d[0] * k, p.y + d[1] * k]); }
function plStairsShown(){
  // (while the Workshop is working out the new plan: the stairs as they were, so they can still be grabbed)
  const ok = PL.res && !PL.res.error && !PL.res.busy;
  if (ok) PL.good = PL.res;
  const P = plData(), res = ok ? PL.res : PL.res && PL.res.busy ? PL.good : null, out = [];
  PL.stLen = PL.stLen || {};
  const live = PL.drag && PL.drag.kind === 'stair' ? PL.drag.floor : PL.placing ? PL.placing.floor : null;
  for (const s of res ? res.stairs : []){
    PL.stLen[s.floor] = s.tiles.length;
    if (s.floor === live) continue;
    out.push({floor: s.floor, tiles: s.tiles.map(t => [t[0], t[1]]), up: s.up, pinned: !!s.pinned, land: s.land || []});
  }
  const floors = new Set(P.rooms.map(r => r.floor));
  for (const [fs, p] of Object.entries(P.stairPins || {})){
    const f = +fs; if (out.some(s => s.floor === f) || f === live) continue;
    if (floors.has(f) && floors.has(f + 1)) out.push({floor: f, tiles: plPinTiles(p, PL.stLen[f] || 2), up: p.up, pinned: true, ghost: true, bad: !!(PL.res && PL.res.error)});
  }
  if (live != null){
    const p = PL.placing ? PL.placing : P.stairPins[live];
    if (p && p.x != null) out.push({floor: live, tiles: plPinTiles(p, PL.stLen[live] || 2), up: p.up, pinned: true, ghost: true});
  }
  return out;
}
// stairs: where the Workshop would put them (it depends on the style's stair pieces)
let plAskT = 0;
function plAsk(){
  const st = $('#cr-bstyle'), L = bLayout();
  const floors = new Set(L.rooms.map(r => r.floor));
  const key = JSON.stringify([st && st.value, L.rooms, L.stairs, L.floors_as, L.doors]);
  if (floors.size < 2){ PL.res = null; PL.resKey = key; plNote(); return; }
  if (!CR.bstyles || !st || !CR.bstyles.some(x => x.id === st.value)) return;
  if (PL.resKey === key) return;
  clearTimeout(plAskT);
  PL.res = {busy: true}; plNote();
  plAskT = setTimeout(async () => {
    try { PL.res = await post('/api/build/plan', {style: st.value, rooms: L.rooms, stairs: L.stairs, floors_as: L.floors_as, doors: L.doors}); }
    catch (e){ PL.res = {error: e.message}; }
    PL.resKey = key;
    if (plExitClear()) plSave();
    plRender(); plNote(); if (!PL.sel) plSide();
  }, 350);
}

// the way out can't open onto the stairs (or stand where they took a room's tile): move it along
function plStairAt(x, y, f){
  const res = PL.res && !PL.res.error && !PL.res.busy ? PL.res : null;
  return !!res && res.stairs.some(s => s.tiles.some(t => t[0] === x && t[1] === y && (s.floor === f || s.floor + 1 === f)));
}
function plExitBlocked(e, r){
  const d = PL_STEP[e.side];
  return plStairAt(e.x, e.y, r.floor) || plStairAt(e.x + d[0], e.y + d[1], r.floor);
}
function plExitClear(){
  const P = plData(), ex = P.exit, r = ex && plRoom(ex.room);
  if (!r || !plExitBlocked(ex, r)) return false;
  const outs = plOutside(r).filter(e => !plExitBlocked(e, r));
  if (!outs.length) return false;
  const same = outs.filter(e => e.side === ex.side);
  P.exit = {room: r.id, ...plMid(same.length ? same : outs)};
  return true;
}

// ----- the planner's own look
function plCss(){
  if ($('#pl-css')) return;
  const c = document.createElement('style'); c.id = 'pl-css';
  c.textContent = `
  .cform:has(#pl-root){max-width:1100px}
  .pl{border:1px solid var(--line);border-radius:10px;background:var(--deep)}
  .pl-body{overflow:hidden}
  .pl-bar{display:flex;gap:6px;align-items:center;flex-wrap:wrap;padding:7px 8px;border-bottom:1px solid var(--line);background:var(--bg2)}
  .pl-bar .sep{width:1px;height:20px;background:var(--line);margin:0 2px}
  .pl-tabs{display:flex;gap:2px} .pl-tabs button{border:1px solid var(--line);background:var(--bg3);color:var(--muted-d);border-radius:6px;padding:3px 8px;font-size:12px;cursor:pointer}
  .pl-tabs button.on{background:var(--sel-b);color:var(--gold2);border-color:var(--goldline)} .pl-tabs button .n{opacity:.6;margin-left:3px}
  .pl-tabs button:disabled{opacity:.35;cursor:default}
  .pl-body{display:grid;grid-template-columns:1fr 260px;min-height:480px}
  @media (max-width:900px){.pl-body{grid-template-columns:1fr}}
  .pl-stage{position:relative;min-height:480px;outline:none;touch-action:none}
  .pl-stage svg,.pl-stage canvas{position:absolute;inset:0;width:100%;height:100%;display:block}
  .pl-side{border-left:1px solid var(--line);padding:10px;background:var(--deep-c);font-size:13px;overflow:auto;max-height:520px}
  .pl-side h4{margin:4px 0 8px;font:600 14px Inter,sans-serif;color:var(--gold2)}
  .pl-side .row{display:flex;gap:6px;align-items:center;margin:6px 0} .pl-side .row > span{min-width:52px;color:var(--muted-b);font-size:12px}
  .pl-side .chips{display:flex;flex-wrap:wrap;gap:4px;margin:6px 0}
  .pl-side .chips button{font-size:11px;padding:2px 7px;border-radius:10px;border:1px solid var(--line);background:var(--bg3);color:var(--muted-c);cursor:pointer}
  .pl-side .chips button:hover{border-color:var(--goldline);color:var(--gold2)}
  .pl-side .tip{color:var(--muted-b);font-size:12px;line-height:1.5} .pl-side .tip b{color:var(--text-b)}
  .pl-side .conn{display:flex;justify-content:space-between;gap:6px;align-items:center;margin:4px 0}
  .pl-hint{position:absolute;left:10px;top:8px;font-size:12px;color:var(--text-b);background:#000a;padding:3px 8px;border-radius:6px;pointer-events:none}
  .pl-zoom{position:absolute;right:8px;bottom:8px;display:flex;gap:4px}
  .pl-zoom button{width:26px;height:26px;border-radius:6px;border:1px solid var(--line);background:color-mix(in srgb,var(--bg3) 80%,transparent);color:var(--text-b);cursor:pointer}
  .pl-note{padding:6px 10px;border-top:1px solid var(--line);font-size:12px;color:var(--muted-b);background:var(--deep-c)}
  .pl-note .err{color:#ff8a6a} .pl-note .warn{color:var(--gold2)}
  .pl-menu{position:relative} .pl-menu > div{display:none;position:absolute;z-index:20;top:100%;left:0;margin-top:4px;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:4px;min-width:200px;box-shadow:0 8px 30px #000c;max-height:min(420px,70vh);overflow-y:auto}
  .pl-menu > div .note{padding:7px 9px;border-top:1px solid var(--line);margin-top:4px;color:var(--muted-b);font-size:12px;line-height:1.45;max-width:240px}
  .pl-menu.open > div{display:block} .pl-menu > div button{display:block;width:100%;text-align:left;background:none;border:0;color:var(--text-b);padding:6px 9px;border-radius:5px;cursor:pointer;font-size:13px}
  .pl-menu > div button:hover{background:#2b241a} .pl-menu > div small{display:block;color:var(--muted-b);font-size:11px}`;
  document.head.appendChild(c);
}

// ----- mounting it in the form
function plMount(){
  const root = $('#pl-root'); if (!root) return;
  plLoad(); plCss();
  root.innerHTML = `<div class="pl">
    <div class="pl-bar">
      <div class="pl-menu" id="pl-addm"><button class="btn sm primary" id="pl-add">+ Room ▾</button><div>${PL_NAMES.map(n => `<button data-add="${esc(n)}">${esc(n)}<small>${PL_SIZES[n].join(' × ')} tiles</small></button>`).join('')}
        <div class="note"><b style="color:var(--text-b)">Stairs</b> aren't a room: put rooms on another floor (the floor tabs) and stairs are added for you. Drag them on the plan to put them where you want, or use the panel on the right.</div></div></div>
      <div class="pl-menu" id="pl-prem"><button class="btn sm" id="pl-pre">Start from ▾</button><div>${PLAN_PRESETS.map((p, i) => `<button data-pre="${i}">${esc(p.name)}<small>${esc(p.note)}</small></button>`).join('')}</div></div>
      <span class="sep"></span><div class="pl-tabs" id="pl-tabs"></div><span class="sep"></span>
      <div class="pl-tabs"><button data-v="plan">Plan</button><button data-v="3d">3D</button></div>
      <span class="sep"></span>
      <button class="btn sm" id="pl-undo" title="Undo (Ctrl+Z)">↶</button><button class="btn sm" id="pl-redo" title="Redo (Ctrl+Y)">↷</button>
      <button class="btn sm" id="pl-fit" title="Fit the plan in view">⤢ Fit</button>
    </div>
    <div class="pl-body"><div class="pl-stage" id="pl-stage" tabindex="0" data-ownkeys><svg id="pl-svg"></svg><canvas id="pl-3d" style="display:none"></canvas>
      <div class="pl-hint" id="pl-hint"></div>
      <div class="pl-zoom"><button id="pl-zin" title="Zoom in">+</button><button id="pl-zout" title="Zoom out">−</button></div></div>
      <div class="pl-side" id="pl-side"></div></div>
    <div class="pl-note" id="pl-note"></div></div>`;
  const menu = (id) => { const m = $('#' + id); m.firstElementChild.onclick = e => { e.stopPropagation(); document.querySelectorAll('.pl-menu.open').forEach(x => x !== m && x.classList.remove('open')); m.classList.toggle('open'); }; };
  menu('pl-addm'); menu('pl-prem');
  document.addEventListener('click', () => document.querySelectorAll('.pl-menu.open').forEach(x => x.classList.remove('open')));
  root.querySelectorAll('[data-add]').forEach(b => b.onclick = () => plAdd(b.dataset.add));
  root.querySelectorAll('[data-pre]').forEach(b => b.onclick = () => plPreset(+b.dataset.pre));
  root.querySelectorAll('[data-v]').forEach(b => b.onclick = () => { PL.view = b.dataset.v; plRender(); });
  $('#pl-undo').onclick = plUndo; $('#pl-redo').onclick = plRedo; $('#pl-fit').onclick = () => { plFit(); plRender(); };
  $('#pl-zin').onclick = () => plZoom(1.25); $('#pl-zout').onclick = () => plZoom(0.8);
  plBind();
  plFix(); plFit(); plRender(); plSide(); plAsk();
  if (PL.ro) PL.ro.disconnect();
  PL.ro = new ResizeObserver(() => plRender()); PL.ro.observe($('#pl-stage'));
}
// a different style: its stairs, how narrow its rooms can be
function plStyleChanged(){ PL.resKey = null; plRender(); plSide(); plAsk(); }
function plStyle(){ return (CR.bstyles || []).find(x => x.id === CR.bstyle) || null; }

// ----- view: tiles to screen pixels (y goes north, up the screen)
const plSX = x => PL.ox + x * PL.z, plSY = y => PL.oy - y * PL.z;
const plPX = sx => (sx - PL.ox) / PL.z, plPY = sy => (PL.oy - sy) / PL.z;
function plFit(){
  const st = $('#pl-stage'); if (!st) return;
  const W = st.clientWidth || 600, H = st.clientHeight || 430;
  const res = PL.res && !PL.res.error && !PL.res.busy ? PL.res : null;
  const R = plData().rooms.flatMap(r => plShaped(r) ? plTiles(r).map(t => ({x: t[0], y: t[1], w: 1, h: 1})) : [r])
    .concat(res ? res.stairs.flatMap(s => s.tiles.map(t => ({x: t[0], y: t[1], w: 1, h: 1}))) : []);
  if (!R.length){ PL.z = 34; PL.ox = W / 2; PL.oy = H / 2; return; }
  const x0 = Math.min(...R.map(r => r.x)) - 1, x1 = Math.max(...R.map(r => r.x + r.w)) + 1;
  const y0 = Math.min(...R.map(r => r.y)) - 1.6, y1 = Math.max(...R.map(r => r.y + r.h)) + 1;
  PL.z = Math.max(14, Math.min(60, Math.min(W / (x1 - x0), H / (y1 - y0))));
  PL.ox = W / 2 - (x0 + x1) / 2 * PL.z; PL.oy = H / 2 + (y0 + y1) / 2 * PL.z;
}
function plZoom(k, cx, cy){
  const st = $('#pl-stage'); if (PL.view === '3d'){ PL.k3 = Math.max(0.4, Math.min(3, (PL.k3 || 1) * k)); plRender(); return; }
  cx = cx ?? st.clientWidth / 2; cy = cy ?? st.clientHeight / 2;
  const px = plPX(cx), py = plPY(cy);
  PL.z = Math.max(10, Math.min(90, PL.z * k));
  PL.ox = cx - px * PL.z; PL.oy = cy + py * PL.z; plRender();
}

// ----- drawing the plan
// adding or taking away tiles only goes on while that room is the selected one, on its own floor: click
// elsewhere, pick another room or floor, and the mode ends (its buttons went with the room's panel)
function plPaintCheck(){
  if (!PL.paint) return;
  const r = plRoom(PL.paint.id);
  if (!r || PL.sel !== PL.paint.id || r.floor !== PL.floor) PL.paint = null;
}
function plRender(){
  plPaintCheck();
  const st = $('#pl-stage'); if (!st) return;
  const svg = $('#pl-svg'), cv = $('#pl-3d');
  document.querySelectorAll('#pl-root [data-v]').forEach(b => b.classList.toggle('on', b.dataset.v === PL.view));
  plTabs();
  $('#pl-undo').disabled = !PL.hist.length; $('#pl-redo').disabled = !PL.fut.length;
  if (PL.view === '3d'){ svg.style.display = 'none'; cv.style.display = 'block'; plRender3D(); plHint(); return; }
  svg.style.display = 'block'; cv.style.display = 'none';
  const W = st.clientWidth, H = st.clientHeight, z = PL.z, f = PL.floor, P = plData();
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const bad = plOverlaps(), names = plNames(), col = r => PL_COLS[P.rooms.indexOf(r) % PL_COLS.length];
  let s = '';
  // grid
  const gx0 = Math.floor(plPX(0)), gx1 = Math.ceil(plPX(W)), gy0 = Math.floor(plPY(H)), gy1 = Math.ceil(plPY(0));
  if (z >= 12){
    let d = '';
    for (let x = gx0; x <= gx1; x++) d += `M${plSX(x)} 0V${H}`;
    for (let y = gy0; y <= gy1; y++) d += `M0 ${plSY(y)}H${W}`;
    s += `<path d="${d}" stroke="#ffffff0d" stroke-width="1"/>`;
  }
  // the floor below, faintly, to line rooms up over it
  for (const r of P.rooms.filter(r => r.floor === f - 1))
    s += `<rect x="${plSX(r.x)}" y="${plSY(r.y + r.h)}" width="${r.w * z}" height="${r.h * z}" fill="none" stroke="#bfb19655" stroke-dasharray="4 4"/>` +
      `<text x="${plSX(r.x) + 4}" y="${plSY(r.y + r.h) + 12}" fill="#bfb19655" font-size="10">${esc(names[r.id])} (below)</text>`;
  const here = P.rooms.filter(r => r.floor === f);
  for (const r of here){
    const op = PL.sel === r.id ? .95 : .78;
    if (!plShaped(r)) s += `<rect x="${plSX(r.x)}" y="${plSY(r.y + r.h)}" width="${r.w * z}" height="${r.h * z}" fill="${col(r)}" fill-opacity="${op}"/>`;
    else for (const [x, y] of plTiles(r)) s += `<rect x="${plSX(x) - .3}" y="${plSY(y + 1) - .3}" width="${z + .6}" height="${z + .6}" fill="${col(r)}" fill-opacity="${op}"/>`;
    if (bad.has(r.id)) for (const [x, y] of plTiles(r)) s += `<rect x="${plSX(x)}" y="${plSY(y + 1)}" width="${z}" height="${z}" fill="url(#pl-bad)"/>`;
  }
  // tiles you could paint onto the selected room (touching it, not another room's)
  const pr_ = PL.paint && plRoom(PL.paint.id);
  if (pr_ && pr_.floor === f && PL.paint.mode === 'add'){
    const seen = new Set();
    for (const [x, y] of plTiles(pr_)) for (const [dx, dy] of Object.values(PL_STEP)){
      const nx = x + dx, ny = y + dy, k = nx + ',' + ny;
      if (seen.has(k) || plRoomAt(nx, ny, f)) continue; seen.add(k);
      s += `<rect x="${plSX(nx) + 2}" y="${plSY(ny + 1) + 2}" width="${z - 4}" height="${z - 4}" fill="${col(pr_)}" fill-opacity=".18" stroke="#f0cd8766" stroke-dasharray="3 3"/>`;
    }
  }
  // tile seams, then walls where a room ends (not between rooms joined into one space)
  let seams = '', walls = '', opens = '';
  const openJoin = (a, b) => P.doors.some(d => d.kind === 'open' && ((d.a === a.id && d.b === b.id) || (d.a === b.id && d.b === a.id)));
  for (const r of here){
    for (const [x, y] of plTiles(r)){
      if (plHas(r, x + 1, y)) seams += `M${plSX(x + 1)} ${plSY(y)}V${plSY(y + 1)}`;
      if (plHas(r, x, y + 1)) seams += `M${plSX(x)} ${plSY(y + 1)}H${plSX(x + 1)}`;
    }
    for (const e of plOutside(r).concat(...here.filter(o => o !== r).map(o => plShared(r, o).map(x => ({...x, o}))))){
      const [x1, y1, x2, y2] = plEdgeLine(e);
      const seg = `M${plSX(x1)} ${plSY(y1)}L${plSX(x2)} ${plSY(y2)}`;
      if (e.o && openJoin(r, e.o)) opens += seg; else walls += seg;
    }
  }
  s += `<path d="${seams}" stroke="#ffffff1a"/><path d="${walls}" stroke="#ebe2cf" stroke-width="2.5" stroke-linecap="square"/>`;
  s += `<path d="${opens}" stroke="#ebe2cf88" stroke-width="1.5" stroke-dasharray="3 4"/>`;
  // stairs: where the Workshop put them, or where you're putting them (drag them, R turns them)
  for (const sx of plStairsShown()){
    if (sx.floor !== f && sx.floor + 1 !== f) continue;
    const up = sx.floor === f, colr = sx.bad ? '#ff8a6a' : '#f0cd87', chosen = PL.selStair === sx.floor;
    // a landing the stairs needed, joined to the room beside it
    for (const t of sx.land || []) if (t[2] === f) s += `<rect x="${plSX(t[0])}" y="${plSY(t[1] + 1)}" width="${z}" height="${z}" fill="#f0cd8722" stroke="#f0cd8766" stroke-dasharray="3 3"/>`;
    for (const t of sx.tiles){
      const X = plSX(t[0]), Y = plSY(t[1] + 1), vert = sx.up === 'N' || sx.up === 'S';
      s += `<rect x="${X}" y="${Y}" width="${z}" height="${z}" fill="#2a2620" fill-opacity="${sx.ghost ? .7 : 1}" stroke="${colr}" stroke-width="${chosen ? 2.5 : 1}" ${sx.ghost ? 'stroke-dasharray="4 3"' : ''}/>`;
      for (let k = 1; k < 5; k++) s += vert ? `<path d="M${X + 3} ${Y + k * z / 5}H${X + z - 3}" stroke="${colr}99"/>` : `<path d="M${X + k * z / 5} ${Y + 3}V${Y + z - 3}" stroke="${colr}99"/>`;
    }
    const a = sx.tiles[0], b = sx.tiles[sx.tiles.length - 1], d = PL_STEP[sx.up];
    const ax = plSX(a[0] + .5 - d[0] * .3), ay = plSY(a[1] + .5 - d[1] * .3), bx = plSX(b[0] + .5 + d[0] * .3), by = plSY(b[1] + .5 + d[1] * .3);
    s += `<path d="M${ax} ${ay}L${bx} ${by}" stroke="${colr}" stroke-width="2" marker-end="url(#pl-arrow)"/>`;
    s += `<text x="${(ax + bx) / 2}" y="${(ay + by) / 2 - 6}" fill="${colr}" font-size="10" text-anchor="middle">${sx.pinned ? '📌 ' : ''}${up ? 'up' : 'from below'}</text>`;
  }
  // doorways
  for (const d of P.doors){
    const a = plRoom(d.a); if (!a || a.floor !== f || d.kind === 'open') continue;
    s += plDoorMark(d, '#f0cd87', 1);
  }
  // the way out
  const ex = P.exit, er = ex && plRoom(ex.room);
  if (er && er.floor === f) s += plExitMark(ex, '#ff8a5c', 1);
  // what a click would do here
  const hv = PL.hover;
  if (hv && hv.kind === 'door') s += plDoorMark(hv.e, hv.remove ? '#ff6a5a' : '#f0cd87', .55);
  if (hv && hv.kind === 'exit') s += plExitMark(hv.e, '#ff8a5c', .5);
  // names and sizes
  for (const r of here){
    const [lx, ly] = plLabelAt(r), cx = plSX(lx), cy = plSY(ly), small = r.w * z < 70;
    s += `<text x="${cx}" y="${cy + (small ? 4 : 0)}" fill="#fff8e8" font-size="${Math.min(13, Math.max(9, z / 3))}" font-weight="600" text-anchor="middle" style="paint-order:stroke" stroke="#0008" stroke-width="3">${esc(names[r.id].length > 16 ? names[r.id].slice(0, 15) + '…' : names[r.id])}</text>`;
    if (!small) s += `<text x="${cx}" y="${cy + 14}" fill="#fff8e8aa" font-size="10" text-anchor="middle">${plSizeText(r)}</text>`;
  }
  // the selected room: an outline and handles to resize it
  const sr = PL.sel && plRoom(PL.sel);
  if (sr && sr.floor === f){
    if (!plShaped(sr)) s += `<rect x="${plSX(sr.x) - 2}" y="${plSY(sr.y + sr.h) - 2}" width="${sr.w * z + 4}" height="${sr.h * z + 4}" fill="none" stroke="#f0cd87" stroke-width="2" stroke-dasharray="6 3"/>`;
    else {
      // round its own outline: every side of a tile that isn't another of its tiles
      let d = '';
      for (const [x, y] of plTiles(sr)) for (const [side, [dx, dy]] of Object.entries(PL_STEP)) if (!plHas(sr, x + dx, y + dy)){
        const [x1, y1, x2, y2] = plEdgeLine({x, y, side}); d += `M${plSX(x1)} ${plSY(y1)}L${plSX(x2)} ${plSY(y2)}`;
      }
      s += `<path d="${d}" fill="none" stroke="#f0cd87" stroke-width="3" stroke-dasharray="6 3"/>`;
    }
    if (!PL.paint) for (const h of plHandles(sr)) s += h.tab
      ? `<rect x="${h.x - 9}" y="${h.y - 5}" width="18" height="10" rx="3" transform="rotate(${h.rot} ${h.x} ${h.y})" fill="#f0cd87" stroke="#000" stroke-width="1"/>`
      : `<rect x="${h.x - 5}" y="${h.y - 5}" width="10" height="10" fill="#f0cd87" stroke="#000" stroke-width="1"/>`;
  }
  // north
  s += `<g transform="translate(${W - 26} 26)"><circle r="14" fill="#000a" stroke="#ffffff22"/><path d="M0 -10L5 3L0 0L-5 3Z" fill="#f0cd87"/><text y="12" fill="#e6d8b8" font-size="8" text-anchor="middle">N</text></g>`;
  svg.innerHTML = `<defs><pattern id="pl-bad" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="4" height="8" fill="#ff3b2b88"/></pattern>
    <marker id="pl-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M0 0L10 5L0 10Z" fill="#f0cd87"/></marker></defs>` + s;
  plHint();
}
// where a room's name goes: the middle, or for a shaped room the middle of its tile nearest the middle
function plLabelAt(r){
  if (!plShaped(r)) return [r.x + r.w / 2, r.y + r.h / 2];
  const T = plTiles(r), mx = T.reduce((s, t) => s + t[0], 0) / T.length + .5, my = T.reduce((s, t) => s + t[1], 0) / T.length + .5;
  const best = T.slice().sort((a, b) => Math.hypot(a[0] + .5 - mx, a[1] + .5 - my) - Math.hypot(b[0] + .5 - mx, b[1] + .5 - my))[0];
  return [best[0] + .5, best[1] + .5];
}
function plSizeText(r){
  if (!plShaped(r)) return `${r.w} × ${r.h}`;
  const cut = (r.cut || []).length, added = plTiles(r).length - (r.w * r.h - cut);
  return `${r.w} × ${r.h}${added ? ' + ' + added : ''}${cut ? ' − ' + cut : ''}`;
}
// an edge of a tile as a line: (x1, y1, x2, y2) in tiles
function plEdgeLine(e){
  const {x, y, side} = e;
  return side === 'N' ? [x, y + 1, x + 1, y + 1] : side === 'S' ? [x, y, x + 1, y] : side === 'E' ? [x + 1, y, x + 1, y + 1] : [x, y, x, y + 1];
}
function plDoorMark(e, colr, op){
  const [x1, y1, x2, y2] = plEdgeLine(e), z = PL.z, vert = x1 === x2;
  const cx = plSX((x1 + x2) / 2), cy = plSY((y1 + y2) / 2), L = z * 0.62, T = Math.max(5, z * 0.16);
  return vert ? `<rect x="${cx - T / 2}" y="${cy - L / 2}" width="${T}" height="${L}" rx="2" fill="${colr}" fill-opacity="${op}" stroke="#000" stroke-opacity="${op}"/>`
    : `<rect x="${cx - L / 2}" y="${cy - T / 2}" width="${L}" height="${T}" rx="2" fill="${colr}" fill-opacity="${op}" stroke="#000" stroke-opacity="${op}"/>`;
}
function plExitMark(e, colr, op){
  const [x1, y1, x2, y2] = plEdgeLine(e), z = PL.z, d = PL_STEP[e.side];
  const cx = plSX((x1 + x2) / 2), cy = plSY((y1 + y2) / 2), a = Math.atan2(-d[1], d[0]) * 180 / Math.PI;
  return `<g transform="translate(${cx} ${cy}) rotate(${a})" opacity="${op}"><rect x="-3" y="${-z * .3}" width="6" height="${z * .6}" fill="${colr}"/>` +
    `<path d="M6 ${-z * .22}L${6 + z * .32} 0L6 ${z * .22}Z" fill="${colr}" stroke="#000" stroke-width="1"/></g>` +
    (op === 1 ? `<text x="${cx + d[0] * z * .75}" y="${cy - d[1] * z * .75 + 4}" fill="${colr}" font-size="10" text-anchor="middle">way out</text>` : '');
}
function plHandles(r){
  const L = plSX(r.x), R = plSX(r.x + r.w), T = plSY(r.y + r.h), B = plSY(r.y), mx = (L + R) / 2, my = (T + B) / 2;
  return [{k: 'nw', x: L, y: T}, {k: 'ne', x: R, y: T}, {k: 'sw', x: L, y: B}, {k: 'se', x: R, y: B},
    {k: 'n', x: mx, y: T - 10, tab: 1, rot: 0}, {k: 's', x: mx, y: B + 10, tab: 1, rot: 0}, {k: 'e', x: R + 10, y: my, tab: 1, rot: 90}, {k: 'w', x: L - 10, y: my, tab: 1, rot: 90}];
}
function plTabs(){
  const box = $('#pl-tabs'); if (!box) return;
  const st = plStyle(), P = plData();
  const count = f => P.rooms.filter(r => r.floor === f).length;
  box.innerHTML = PL_FLOORS.slice().reverse().map(([f, n]) => `<button data-fl="${f}" class="${f === PL.floor ? 'on' : ''}" title="${esc(n)}">${esc(n)}${count(f) ? `<span class="n">${count(f)}</span>` : ''}</button>`).join('');
  box.querySelectorAll('[data-fl]').forEach(b => b.onclick = () => { PL.floor = +b.dataset.fl; PL.sel = null; plRender(); plSide(); });
}
function plHint(){
  const h = $('#pl-hint'); if (!h) return;
  const hv = PL.hover;
  h.textContent = PL.view === '3d' ? 'Drag to turn it, scroll to zoom. Edit rooms in Plan.' :
    PL.placing ? 'Click where the bottom step of the stairs goes · R turns them · Esc stops' :
    PL.paint ? (PL.paint.mode === 'add' ? 'Click or drag on the marked tiles to add them to the room · Esc when done' : 'Click or drag on the room\'s tiles to take them away · Esc when done') :
    PL.drag && PL.drag.kind === 'stair' ? 'Let go to put the stairs here' :
    hv && hv.kind === 'stair' ? (hv.s.pinned ? 'Drag to move the stairs · click, then R turns them · Delete lets the Workshop choose' : 'Drag the stairs to put them where you want them') :
    hv && hv.kind === 'door' ? (hv.remove ? 'Click: take this doorway out' : 'Click: a doorway here') :
    hv && hv.kind === 'exit' ? 'Click: the way out goes here' :
    hv && hv.kind === 'handle' ? 'Drag to resize' : hv && hv.kind === 'room' ? 'Drag to move · double-click to rename' :
    'Drag rooms to move them · click a wall for a doorway · drag the background to pan, scroll to zoom';
}
function plNote(){
  const n = $('#pl-note'); if (!n) return;
  const P = plData(), st = plStyle(), msgs = [];
  const floors = [...new Set(P.rooms.map(r => r.floor))].sort((a, b) => a - b);
  if (plOverlaps().size) msgs.push('<span class="err">Rooms overlap (striped red). Move them apart.</span>');
  for (let i = 1; i < floors.length; i++) if (floors[i] !== floors[i - 1] + 1) msgs.push(`<span class="err">There's no room on a floor between the ${plFloorName(floors[i - 1]).toLowerCase()} and the ${plFloorName(floors[i]).toLowerCase()}.</span>`);
  if (st && !st.small_rooms && P.rooms.some(r => Math.min(r.w, r.h) < 2)) msgs.push(`<span class="warn">Rooms in the ${esc(st.name)} style need to be at least 2 tiles wide.</span>`);
  const lost = plUnreachable();
  if (lost.length) msgs.push(`<span class="warn">No way to get to ${lost.map(r => '"' + esc(plNames()[r.id]) + '"').join(', ')}: put a doorway in a wall it shares with another room.</span>`);
  if (PL.res && PL.res.busy) msgs.push('Working out where the stairs go…');
  else if (PL.res && PL.res.error) msgs.push(`<span class="err">${esc(PL.res.error)}</span>`);
  else if (PL.res && PL.res.notes && PL.res.notes.length) msgs.push((PL.res.linked ? '<span class="warn">' : '<span>') + esc(PL.res.notes.join(' ')) + '</span>');
  const tiles = P.rooms.reduce((s, r) => s + plTiles(r).length, 0), m = (st ? st.tile : 256) / 72;
  n.innerHTML = (msgs.length ? msgs.join(' · ') + ' · ' : '') + `${P.rooms.length} room${P.rooms.length === 1 ? '' : 's'}, ${tiles} tiles (about ${Math.round(tiles * m * m)} m²)${floors.length > 1 ? ', ' + floors.length + ' floors' : ''}. One tile is about ${m.toFixed(1)} m.`;
}
// rooms you couldn't walk to from the way out (stairs join floors)
function plUnreachable(){
  const P = plData(); if (!P.exit) return [];
  const seen = new Set([P.exit.room]), todo = [P.exit.room];
  while (todo.length){
    const id = todo.pop(), r = plRoom(id);
    const next = P.doors.filter(d => d.a === id || d.b === id).map(d => d.a === id ? d.b : d.a);
    // stairs: chosen ones, or any room on the floor next to this one (the Workshop picks)
    for (const o of P.rooms) if (Math.abs(o.floor - r.floor) === 1){
      const pick = P.stairs.find(s => (s.lo === id && s.hi === o.id) || (s.hi === id && s.lo === o.id));
      const chosen = P.stairs.some(s => plRoom(s.lo) && plRoom(s.lo).floor === Math.min(o.floor, r.floor));
      if (pick || !chosen) next.push(o.id);
    }
    for (const n of next) if (!seen.has(n)){ seen.add(n); todo.push(n); }
  }
  return P.rooms.filter(r => !seen.has(r.id));
}

// ----- the panel beside the plan: the selected room, or what you can do
function plSide(){
  plPaintCheck();
  const box = $('#pl-side'); if (!box) return;
  const P = plData(), r = PL.sel && plRoom(PL.sel), names = plNames();
  if (!r){
    const pairs = [];
    const floors = [...new Set(P.rooms.map(x => x.floor))].sort((a, b) => a - b);
    for (const f of floors) if (floors.includes(f + 1)){
      const cur = P.stairs.find(s => plRoom(s.lo) && plRoom(s.lo).floor === f);
      const lo = P.rooms.filter(x => x.floor === f), hi = P.rooms.filter(x => x.floor === f + 1);
      const linked = PL.res && PL.res.linked, pin = (P.stairPins || {})[f], picked = PL.selStair === f;
      const shown = !linked && plStairsShown().find(s => s.floor === f);
      pairs.push(`<div style="${picked ? 'border:1px solid var(--goldline);border-radius:8px;padding:6px;margin:6px -6px;background:#f0cd870d' : ''}">
        <div class="row" style="flex-wrap:wrap"><span style="min-width:100%">${linked ? (f < 0 ? 'Trapdoor down to the ' + esc(plFloorName(f).toLowerCase()) : 'Door up from the ' + esc(plFloorName(f).toLowerCase())) : 'Stairs from the ' + esc(plFloorName(f).toLowerCase()) + ' up'}</span>
        ${pin && !linked ? '' : `<select class="inp" data-stair="${f}" style="font-size:12px"><option value="">${linked ? 'The biggest rooms' : 'Wherever they fit best'}</option>${lo.flatMap(a => hi.map(b => `<option value="${a.id}|${b.id}" ${cur && cur.lo === a.id && cur.hi === b.id ? 'selected' : ''}>${esc(names[a.id])} → ${esc(names[b.id])}</option>`)).join('')}</select>`}</div>
        ${linked ? '' : pin ? `<div class="tip">📌 <b>Put here by hand.</b> Drag them on the plan; <b>R</b> turns them, arrows move them.</div>
            <div class="row"><button class="btn sm" data-stfree="${f}" title="Let the Workshop choose where they go again (Delete)">Let the Workshop choose</button></div>`
          : `<label class="tip" style="display:flex;gap:6px;align-items:center;margin:4px 0"><input type="checkbox" data-stout="${f}" ${(P.stairOut || {})[f] ? 'checked' : ''}> Rather beside the rooms, in a stairwell of their own</label>
            <div class="row" style="flex-wrap:wrap">${shown ? `<button class="btn sm" data-stkeep="${f}" title="Keep them just where they are now, whatever you change">📌 Keep them here</button>` : ''}
            <button class="btn sm" data-stplace="${f}" title="Click on the plan where the bottom step goes; R turns them first">✋ Place by hand</button></div>`}
      </div>`);
    }
    box.innerHTML = `<h4>Planning the rooms</h4><div class="tip">
      <b>Drag</b> a room to move it, its <b>corners or side tabs</b> to resize it.<br>
      Click the <b>wall between two rooms</b> for a doorway; click it again to take it out.<br>
      Click an <b>outside wall</b> to put the way out there.<br>
      Use the <b>floor tabs</b> for a cellar or upstairs: the rooms below show faintly, and stairs are added for you.<br>
      <b>Drag the stairs</b> to put them where you want them (they stay there); click them and press <b>R</b> to turn them.<br>
      Rooms needn't be rectangles: select one and use <b>✏ Add tiles</b> or <b>⌫ Take away</b> to give it a nook, an anteroom or an L shape.<br>
      <b>Keys:</b> Delete, R turns a room, arrows move it, Ctrl+D copies it, Ctrl+Z undoes.</div>
      ${pairs.length ? plJoinChoice() : ''}
      ${pairs.length ? '<h4 style="margin-top:14px">' + (PL.res && PL.res.linked ? 'Between floors' : 'Stairs') + '</h4>' + pairs.join('') + plLearnedHtml() : ''}`;
    box.querySelectorAll('[name=pl-join]').forEach(r => r.onchange = () => { plSnap(); P.join = r.value; PL.resKey = null; plChanged(); });
    box.querySelectorAll('[data-stair]').forEach(s => s.onchange = () => {
      plSnap(); const f = +s.dataset.stair;
      P.stairs = P.stairs.filter(x => !(plRoom(x.lo) && plRoom(x.lo).floor === f));
      if (s.value){ const [lo, hi] = s.value.split('|'); P.stairs.push({lo, hi}); }
      plChanged();
    });
    box.querySelectorAll('[data-stout]').forEach(c => c.onchange = () => { plSnap(); P.stairOut = P.stairOut || {}; if (c.checked) P.stairOut[c.dataset.stout] = true; else delete P.stairOut[c.dataset.stout]; plChanged(); });
    box.querySelectorAll('[data-stfree]').forEach(b => b.onclick = () => { plSnap(); delete P.stairPins[b.dataset.stfree]; plChanged(); });
    box.querySelectorAll('[data-stkeep]').forEach(b => b.onclick = () => {
      const f = +b.dataset.stkeep, s = plStairsShown().find(x => x.floor === f); if (!s) return;
      plSnap(); P.stairPins[f] = {x: s.tiles[0][0], y: s.tiles[0][1], up: s.up}; PL.selStair = f; plChanged();
      toast('The stairs stay there now, whatever you change. Drag them to move them.');
    });
    box.querySelectorAll('[data-stplace]').forEach(b => b.onclick = () => {
      const f = +b.dataset.stplace, s = plStairsShown().find(x => x.floor === f);
      PL.placing = {floor: f, up: s ? s.up : 'N', x: null, y: null};
      if (PL.floor !== f && PL.floor !== f + 1) PL.floor = f;
      $('#pl-stage').focus(); plRender();
      toast('Click where the bottom step goes. R turns them first, Esc stops.');
    });
    return;
  }
  const touching = P.rooms.filter(o => o !== r && plShared(r, o).length);
  const link = o => { const d = P.doors.find(d => (d.a === r.id && d.b === o.id) || (d.a === o.id && d.b === r.id)); return d ? d.kind || 'door' : 'wall'; };
  box.innerHTML = `<h4>${esc(names[r.id])}</h4>
    <div class="row"><span>Name</span><input class="inp" id="pl-name" value="${esc(r.name)}" style="flex:1"></div>
    <div class="chips">${PL_NAMES.map(n => `<button data-nm="${esc(n)}">${esc(n)}</button>`).join('')}</div>
    <div class="tip" style="margin-bottom:6px">Auto-furnish goes by the name.</div>
    <div class="row"><span>Size</span><input class="inp" type="number" min="1" max="16" id="pl-w" value="${r.w}" style="width:58px"><span style="min-width:0">×</span><input class="inp" type="number" min="1" max="16" id="pl-h" value="${r.h}" style="width:58px"><span style="min-width:0">tiles</span></div>
    <div class="row" style="flex-wrap:wrap"><span>Shape</span><button class="btn sm${PL.paint && PL.paint.mode === 'add' ? ' primary' : ''}" id="pl-padd" title="Click or drag on tiles next to the room to make them part of it">✏ Add tiles</button><button class="btn sm${PL.paint && PL.paint.mode === 'cut' ? ' primary' : ''}" id="pl-pcut" title="Click or drag on the room's tiles to take them away">⌫ Take away</button>${plShaped(r) ? '<button class="btn sm" id="pl-prect" title="Back to its plain rectangle">▭ Rectangle again</button>' : ''}</div>
    ${PL.paint ? `<div class="tip">${PL.paint.mode === 'add' ? 'Click or drag on the tiles marked round the room to add them' : 'Click or drag on the room\'s tiles to take them away'}. <b>Esc</b> or the button again when you're done.</div>` : ''}
    <div class="row"><span>Floor</span><select class="inp" id="pl-floor" style="flex:1">${PL_FLOORS.map(([v, l]) => `<option value="${v}" ${v === r.floor ? 'selected' : ''}>${l}</option>`).join('')}</select></div>
    ${touching.length ? `<h4 style="margin-top:12px">Next door</h4>${touching.map(o => `<div class="conn"><span>${esc(names[o.id])}</span><select class="inp" data-link="${o.id}" style="max-width:130px;font-size:12px">
      <option value="door" ${link(o) === 'door' ? 'selected' : ''}>Doorway</option><option value="open" ${link(o) === 'open' ? 'selected' : ''}>Open, no wall</option><option value="wall" ${link(o) === 'wall' ? 'selected' : ''}>Wall</option></select></div>`).join('')}
      <div class="tip">"Open, no wall" makes one space of both, like an L-shaped room.</div>` : ''}
    <div class="row" style="margin-top:12px;flex-wrap:wrap"><button class="btn sm" id="pl-dup">Copy</button><button class="btn sm" id="pl-rot">Turn</button><button class="btn sm" id="pl-del" style="color:#ff8a6a">Delete</button></div>`;
  const nm = $('#pl-name');
  nm.oninput = () => { r.name = nm.value; plSave(); plRender(); plNote(); };
  nm.onfocus = () => plSnap();
  nm.onchange = () => plChanged();
  box.querySelectorAll('[data-nm]').forEach(b => b.onclick = () => { plSnap(); r.name = b.dataset.nm; plChanged(); });
  const size = () => { plSnap(); r.w = Math.max(1, Math.min(16, +$('#pl-w').value || 1)); r.h = Math.max(1, Math.min(16, +$('#pl-h').value || 1)); plChanged(); };
  $('#pl-w').onchange = size; $('#pl-h').onchange = size;
  $('#pl-floor').onchange = () => { plSnap(); r.floor = +$('#pl-floor').value; PL.floor = r.floor; plChanged(); };
  box.querySelectorAll('[data-link]').forEach(s => s.onchange = () => {
    plSnap(); const o = plRoom(s.dataset.link);
    P.doors = P.doors.filter(d => !((d.a === r.id && d.b === o.id) || (d.a === o.id && d.b === r.id)));
    if (s.value !== 'wall') P.doors.push({a: r.id, b: o.id, kind: s.value, ...plMid(plShared(r, o))});
    plFix2(r, o, s.value); plChanged();
  });
  $('#pl-dup').onclick = () => plDuplicate(r); $('#pl-rot').onclick = () => plRotate(r); $('#pl-del').onclick = () => plDelete(r);
  const paint = mode => { PL.paint = PL.paint && PL.paint.mode === mode ? null : {mode, id: r.id}; $('#pl-stage').focus(); plRender(); plSide(); };
  $('#pl-padd').onclick = () => paint('add'); $('#pl-pcut').onclick = () => paint('cut');
  const pr = $('#pl-prect'); if (pr) pr.onclick = () => { plSnap(); r.add = []; r.cut = []; PL.paint = null; plChanged(); };
}
// painting a tile onto (or off) the room being shaped; false when it can't be
function plPaintAt(x, y){
  const r = PL.paint && plRoom(PL.paint.id); if (!r || r.floor !== PL.floor) return false;
  const dx = x - r.x, dy = y - r.y, inRect = dx >= 0 && dx < r.w && dy >= 0 && dy < r.h;
  r.add = r.add || []; r.cut = r.cut || [];
  if (PL.paint.mode === 'add'){
    if (plHas(r, x, y) || plRoomAt(x, y, r.floor)) return false;
    if (!Object.values(PL_STEP).some(([sx, sy]) => plHas(r, x + sx, y + sy))) return false;      // (it has to touch the room)
    if (plTiles(r).length >= 200) return false;
    if (inRect) r.cut = r.cut.filter(t => !(t[0] === dx && t[1] === dy)); else r.add.push([dx, dy]);
    return true;
  }
  if (!plHas(r, x, y)) return false;
  const left = plTiles(r).filter(t => !(t[0] === x && t[1] === y));
  if (!left.length) return false;
  if (!plJoined(left)){ if (!PL.paintWarned){ PL.paintWarned = true; toast('That would cut the room in two. Take away a tile at its edge instead.', true); } return false; }
  if (inRect) r.cut.push([dx, dy]); else r.add = r.add.filter(t => !(t[0] === dx && t[1] === dy));
  return true;
}
// what the game's own places do round their stairs, in this style (or in all of them, for a style the
// game never builds with): the survey the builder goes by
const PL_ROLE = {centre: 'open floor', side: 'a wall on one side', corner: 'a corner', hall: 'a hall', end: 'a dead end', closed: 'walled in'};
function plLearnedHtml(){
  const st = plStyle(); if (!st) return '';
  const S = PL.survey && PL.survey[st.id];
  if (S === undefined){
    PL.survey = PL.survey || {}; PL.survey[st.id] = null;
    api('/api/build/stairsurvey?style=' + encodeURIComponent(st.id)).then(async r => {
      PL.survey[st.id] = r.n ? {own: true, r} : {own: false, r: await api('/api/build/stairsurvey')};
      if (!PL.sel) plSide();
    }).catch(() => {});
    return '';
  }
  if (!S) return '';
  const r = S.own ? (S.r.styles[st.id] || {}) : S.r.all, n = S.own ? r.n : S.r.n;
  const share = (list, test) => { const tot = (list || []).reduce((a, x) => a + x[1], 0); return tot ? Math.round(100 * (list || []).filter(x => test(x[0])).reduce((a, x) => a + x[1], 0) / tot) : 0; };
  // (the kinds of piece at the foot, most common first, and how often it's a small landing of its own)
  const kinds = {}; let land = 0, all = 0;
  for (const [k, c] of r.foot || []){ const m = /'(\w+)', '(\w+)'/.exec(k); if (!m) continue; kinds[m[1]] = (kinds[m[1]] || 0) + c; all += c; if (m[2] === 'landing') land += c; }
  const top = Object.entries(kinds).sort((a, b) => b[1] - a[1]).slice(0, 2).map(([k]) => PL_ROLE[k] || k);
  if (top.length && all) top[top.length - 1] += `, ${Math.round(100 * land / all)}% of them a small landing`;
  return `<details class="tip" style="margin-top:8px"><summary style="cursor:pointer;color:var(--gold2)">What the game does</summary>
    <div style="margin-top:4px">${S.own ? `From ${n} staircases in the game's own ${esc(st.name)} places:` : `No place in your game is built in ${esc(st.name)}, so the Workshop goes by all ${n} staircases in the game's places:`}
    <ul style="margin:4px 0 0 16px;padding:0">
      <li>at the foot, mostly ${esc(top.join(', or ') || 'a room')}; almost never a dead end</li>
      <li>${share(r.sides_low, k => /'none', 'none'/.test(k))}% have no floor beside them: along an outside wall or in a stairwell of their own</li>
      <li>${share(r.over, k => k === 'nothing')}% are open above, with nothing built over them</li>
      <li>${share(r.posts, k => k === '0')}% have no post or column by them</li></ul></div></details>`;
}
// stairs inside one place, or a place per floor joined by doors (styles without stairs: only that)
function plJoinChoice(){
  const P = plData(), st = plStyle(), can = st ? st.floors : true, v = P.join || 'auto';
  const dflt = st && st.stairs_default === false ? 'linked' : (can ? 'stairs' : 'linked');
  const opt = (val, label, hint, dis) => `<label class="tip" style="display:flex;gap:6px;align-items:flex-start;margin:4px 0;${dis ? 'opacity:.45' : ''}"><input type="radio" name="pl-join" value="${val}" ${dis ? 'disabled' : ''} ${(v === val || (v === 'auto' && val === dflt)) ? 'checked' : ''}><span><b>${label}</b><br>${hint}</span></label>`;
  return '<h4 style="margin-top:14px">Floors joined by</h4>' +
    opt('stairs', 'Stairs', !can ? 'This style has no stair pieces.' : dflt === 'linked' ? 'Only ramps meant for halls: they may leave gaps in rooms.' : 'All floors in one place, with the style\'s own stairs.', !can) +
    opt('linked', 'Doors', 'Each floor is a place of its own, joined by a door (a trapdoor to a cellar), like many houses in the game.', false);
}
// a wall chosen on purpose stays a wall (not filled in with a doorway again by plFix)
function plFix2(r, o, v){
  const P = plData();
  P.walls = (P.walls || []).filter(w => !((w[0] === r.id && w[1] === o.id) || (w[0] === o.id && w[1] === r.id)));
  if (v === 'wall') P.walls.push([r.id, o.id]);
}

// ----- editing
function plFree(w, h, f, near){
  // a spot for a new room: beside the one given (east, north, west, south), or anywhere free
  const P = plData(), fits = (x, y) => { for (let i = x; i < x + w; i++) for (let j = y; j < y + h; j++) if (plRoomAt(i, j, f)) return false; return true; };
  const cands = [];
  for (const r of near ? [near] : P.rooms.filter(r => r.floor === f)){
    cands.push([r.x + r.w, r.y], [r.x, r.y + r.h], [r.x - w, r.y], [r.x, r.y - h], [r.x + r.w, r.y + r.h - h], [r.x + r.w - w, r.y + r.h]);
  }
  for (const [x, y] of cands) if (fits(x, y)) return [x, y];
  if (!P.rooms.some(r => r.floor === f)){
    // the first room on a new floor: over (or under) the rooms of the floor next to it
    const o = P.rooms.filter(r => Math.abs(r.floor - f) === 1);
    if (o.length) return [Math.min(...o.map(r => r.x)), Math.min(...o.map(r => r.y))];
    return [0, 0];
  }
  for (let rad = 1; rad < 30; rad++) for (let x = -rad; x <= rad; x++) for (let y = -rad; y <= rad; y++) if (fits(x, y)) return [x, y];
  return [0, 0];
}
function plAdd(name){
  plSnap();
  const [w, h] = PL_SIZES[name] || [2, 3], f = PL.floor, near = PL.sel && plRoom(PL.sel);
  const [x, y] = plFree(w, h, f, near && near.floor === f ? near : null);
  const r = {id: plNewId(), name, x, y, w, h, floor: f};
  plData().rooms.push(r); PL.sel = r.id;
  if (near && near.floor === f && plShared(r, near).length) plData().doors.push({a: near.id, b: r.id, kind: 'door', ...plMid(plShared(near, r))});
  plChanged(); plMaybeFit();
}
function plDuplicate(r){
  plSnap();
  const [x, y] = plFree(r.w, r.h, r.floor, r);
  const c = {...r, id: plNewId(), x, y, add: (r.add || []).map(t => t.slice()), cut: (r.cut || []).map(t => t.slice())};
  plData().rooms.push(c); PL.sel = c.id; plChanged(); plMaybeFit();
}
function plRotate(r){
  plSnap();
  // a quarter turn: a tile dx, dy from the corner goes to dy, (old width - 1 - dx)
  const turn = t => [t[1], r.w - 1 - t[0]];
  r.add = (r.add || []).map(turn); r.cut = (r.cut || []).map(turn);
  [r.w, r.h] = [r.h, r.w]; plChanged();
}
// the room's corner moved (resizing from the west or south): its added and taken-away tiles stay put
function plKeepShape(r, o){
  const dx = o.x - r.x, dy = o.y - r.y;
  r.add = (o.add || []).map(t => [t[0] + dx, t[1] + dy]).filter(t => !(t[0] >= 0 && t[0] < r.w && t[1] >= 0 && t[1] < r.h));
  r.cut = (o.cut || []).map(t => [t[0] + dx, t[1] + dy]).filter(t => t[0] >= 0 && t[0] < r.w && t[1] >= 0 && t[1] < r.h);
}
function plDelete(r){
  if (plData().rooms.length < 2) return toast('A building needs at least one room.', true);
  plSnap(); const P = plData();
  P.rooms = P.rooms.filter(x => x !== r); P.doors = P.doors.filter(d => d.a !== r.id && d.b !== r.id);
  PL.sel = null; plChanged();
}
function plMaybeFit(){
  const st = $('#pl-stage'), R = plData().rooms;
  const out = R.some(r => plSX(r.x) < 0 || plSX(r.x + r.w) > st.clientWidth || plSY(r.y + r.h) < 0 || plSY(r.y) > st.clientHeight);
  if (out){ plFit(); plRender(); }
}

// ----- pointer and keys
function plWhat(sx, sy){
  const P = plData(), f = PL.floor, px = plPX(sx), py = plPY(sy);
  const sr = PL.sel && plRoom(PL.sel);
  if (sr && sr.floor === f) for (const h of plHandles(sr)) if (Math.abs(sx - h.x) <= (h.tab ? 10 : 7) && Math.abs(sy - h.y) <= (h.tab ? 10 : 7)) return {kind: 'handle', k: h.k, r: sr};
  // near a wall line: a doorway between two rooms, or the way out on an outside wall
  const tol = Math.min(0.22, 7 / PL.z);
  const vx = Math.round(px), hy = Math.round(py), dv = Math.abs(px - vx), dh = Math.abs(py - hy);
  const tryEdge = (vertical) => {
    if (vertical){
      const ty = Math.floor(py), a = plRoomAt(vx - 1, ty, f), b = plRoomAt(vx, ty, f);
      if (a && b && a !== b) return {kind: 'door', a, b, e: {x: vx - 1, y: ty, side: 'E'}};
      if (a && !b) return {kind: 'exit', r: a, e: {x: vx - 1, y: ty, side: 'E'}};
      if (b && !a) return {kind: 'exit', r: b, e: {x: vx, y: ty, side: 'W'}};
    } else {
      const tx = Math.floor(px), a = plRoomAt(tx, hy - 1, f), b = plRoomAt(tx, hy, f);
      if (a && b && a !== b) return {kind: 'door', a, b, e: {x: tx, y: hy - 1, side: 'N'}};
      if (a && !b) return {kind: 'exit', r: a, e: {x: tx, y: hy - 1, side: 'N'}};
      if (b && !a) return {kind: 'exit', r: b, e: {x: tx, y: hy, side: 'S'}};
    }
    return null;
  };
  const cands = [];
  if (dv < tol) cands.push([dv, true]);
  if (dh < tol) cands.push([dh, false]);
  // the stairs (on either floor they join): grab them to move them
  const tx = Math.floor(px), ty = Math.floor(py);
  const stair = plStairsShown().find(s => (s.floor === f || s.floor + 1 === f) && s.tiles.some(t => t[0] === tx && t[1] === ty));
  cands.sort((a, b) => a[0] - b[0]);
  for (const [, vertical] of cands){ const h = tryEdge(vertical); if (h) return plEdgeHit(h); }
  if (stair) return {kind: 'stair', s: stair};      // (after the walls, so a doorway beside them can still be clicked)
  const r = plRoomAt(Math.floor(px), Math.floor(py), f);
  if (r) return {kind: 'room', r};
  return {kind: 'bg'};
}
function plEdgeHit(h){
  const P = plData();
  if (h.kind === 'door'){
    const ex = P.doors.find(d => ((d.a === h.a.id && d.b === h.b.id) || (d.a === h.b.id && d.b === h.a.id)));
    if (ex && ex.kind === 'open') return {kind: 'room', r: h.a};
    h.remove = !!(ex && plSameEdge(ex, h.e));
    h.move = ex && !h.remove ? ex : null;
  }
  return h;
}
function plBind(){
  const st = $('#pl-stage');
  const pos = e => { const b = st.getBoundingClientRect(); return [e.clientX - b.left, e.clientY - b.top]; };
  st.onpointerdown = e => {
    st.focus(); const [sx, sy] = pos(e);
    if (PL.view === '3d'){ PL.drag = {kind: 'turn', sx, sy, yaw: PL.yaw, tilt: PL.tilt}; st.setPointerCapture(e.pointerId); return; }
    const w = plWhat(sx, sy), P = plData();
    // shaping a room: paint tiles on (or off) by clicking or dragging
    if (PL.paint){
      plSnap(); PL.paintWarned = false;
      const did = plPaintAt(Math.floor(plPX(sx)), Math.floor(plPY(sy)));
      PL.drag = {kind: 'paint', did}; st.setPointerCapture(e.pointerId); plRender(); return;
    }
    // "Place by hand": the stairs follow the mouse; a click puts them down
    if (PL.placing){
      const p = PL.placing; plSnap();
      P.stairPins[p.floor] = {x: p.x, y: p.y, up: p.up};
      PL.selStair = p.floor; PL.placing = null; PL.sel = null; plChanged(); return;
    }
    if (w.kind === 'stair'){
      // grab the stairs: moving them puts them there for good (until you hand them back)
      const s = w.s, pin = P.stairPins[s.floor] || {x: s.tiles[0][0], y: s.tiles[0][1], up: s.up};
      PL.selStair = s.floor; PL.sel = null; plSnap();
      PL.drag = {kind: 'stair', floor: s.floor, sx, sy, orig: {...pin}, had: !!P.stairPins[s.floor], moved: false};
      st.setPointerCapture(e.pointerId); plRender(); plSide(); return;
    }
    if (PL.selStair != null && w.kind !== 'stair'){ PL.selStair = null; }
    if (w.kind === 'door'){
      plSnap();
      if (w.remove){ P.doors = P.doors.filter(d => d !== P.doors.find(d => plSameEdge(d, w.e))); plFix2(w.a, w.b, 'wall'); }
      else if (w.move) Object.assign(w.move, w.e, {a: w.a.id, b: w.b.id});
      else { P.doors.push({a: w.a.id, b: w.b.id, kind: 'door', ...w.e}); plFix2(w.a, w.b, 'door'); }
      PL.hover = null; plChanged(); return;
    }
    if (w.kind === 'exit'){ plSnap(); P.exit = {room: w.r.id, ...w.e}; PL.hover = null; plChanged(); return; }
    if (w.kind === 'room' || w.kind === 'handle'){
      PL.sel = w.r.id; plSnap();
      PL.drag = {kind: w.kind, k: w.k, r: w.r, sx, sy, orig: {...w.r}, moved: false};
      st.setPointerCapture(e.pointerId); plRender(); plSide(); return;
    }
    PL.drag = {kind: 'pan', sx, sy, ox: PL.ox, oy: PL.oy, moved: false};
    st.setPointerCapture(e.pointerId);
  };
  st.onpointermove = e => {
    const [sx, sy] = pos(e), d = PL.drag;
    if (PL.placing && PL.view === 'plan'){
      // the bottom step under the mouse
      const x = Math.floor(plPX(sx)), y = Math.floor(plPY(sy));
      if (x !== PL.placing.x || y !== PL.placing.y){ PL.placing.x = x; PL.placing.y = y; plRender(); }
      st.style.cursor = 'copy'; return;
    }
    if (d && d.kind === 'paint'){ if (plPaintAt(Math.floor(plPX(sx)), Math.floor(plPY(sy)))){ d.did = true; plRender(); } return; }
    if (!d && PL.paint && PL.view === 'plan'){ st.style.cursor = 'crosshair'; return; }
    if (d && d.kind === 'stair'){
      const dx = Math.round((sx - d.sx) / PL.z), dy = Math.round(-(sy - d.sy) / PL.z);
      if (dx || dy) d.moved = true;
      if (d.moved){ plData().stairPins[d.floor] = {x: d.orig.x + dx, y: d.orig.y + dy, up: d.orig.up}; plRender(); }
      return;
    }
    if (!d){ if (PL.view === 'plan'){ const w = plWhat(sx, sy); const k = JSON.stringify([w.kind, w.e, w.k, w.r && w.r.id, w.remove]);
      if (k !== PL.hoverKey){ PL.hoverKey = k; PL.hover = w; st.style.cursor = w.kind === 'door' || w.kind === 'exit' ? 'pointer' : w.kind === 'room' || w.kind === 'stair' ? 'move' :
        w.kind === 'handle' ? ({n: 'ns-resize', s: 'ns-resize', e: 'ew-resize', w: 'ew-resize', ne: 'nesw-resize', sw: 'nesw-resize', nw: 'nwse-resize', se: 'nwse-resize'})[w.k] : 'grab'; plRender(); } } return; }
    if (d.kind === 'turn'){ PL.yaw = d.yaw + (sx - d.sx) * 0.008; PL.tilt = Math.max(0.15, Math.min(1.2, d.tilt + (sy - d.sy) * 0.004)); plRender(); return; }
    if (d.kind === 'pan'){ PL.ox = d.ox + sx - d.sx; PL.oy = d.oy + sy - d.sy; d.moved = true; plRender(); return; }
    const dx = Math.round((sx - d.sx) / PL.z), dy = Math.round(-(sy - d.sy) / PL.z), r = d.r, o = d.orig;
    if (d.kind === 'room'){ r.x = o.x + dx; r.y = o.y + dy; }
    else {
      const k = d.k;
      if (k.includes('e')) r.w = Math.max(1, Math.min(16, o.w + dx));
      if (k.includes('w')){ const w = Math.max(1, Math.min(16, o.w - dx)); r.x = o.x + o.w - w; r.w = w; }
      if (k.includes('n')) r.h = Math.max(1, Math.min(16, o.h + dy));
      if (k.includes('s')){ const h = Math.max(1, Math.min(16, o.h - dy)); r.y = o.y + o.h - h; r.h = h; }
      if (plShaped(o)) plKeepShape(r, o);
    }
    if (dx || dy) d.moved = true;
    plRender(); plNote();             // (doors and the way out follow when it's dropped)
  };
  st.onpointerup = e => {
    const d = PL.drag; PL.drag = null;
    if (!d) return;
    if (d.kind === 'paint'){ if (!d.did) PL.hist.pop(); else plChanged(); return; }
    if (d.kind === 'stair'){
      if (!d.moved){ PL.hist.pop(); plRender(); return; }      // (just picked: the panel shows what you can do)
      plChanged(); return;
    }
    if (d.kind === 'pan' && !d.moved){ PL.sel = null; PL.selStair = null; plSide(); plRender(); return; }
    if ((d.kind === 'room' || d.kind === 'handle')){
      if (!d.moved){ PL.hist.pop(); return; }
      // dropped on top of another room: back where it was
      if (plOverlaps().has(d.r.id)){ Object.assign(d.r, d.orig); toast('Rooms can\'t overlap: it went back.', true); }
      plChanged();
    }
  };
  st.ondblclick = () => { const n = $('#pl-name'); if (n){ n.focus(); n.select(); } };
  st.onpointerleave = () => { if (!PL.drag && PL.hover){ PL.hover = null; PL.hoverKey = null; plRender(); } };
  st.onwheel = e => { e.preventDefault(); const [sx, sy] = pos(e); plZoom(e.deltaY < 0 ? 1.12 : 0.89, sx, sy); };
  st.onkeydown = e => {
    const r = PL.sel && plRoom(PL.sel), k = e.key, ctrl = e.ctrlKey || e.metaKey;
    if (ctrl && k.toLowerCase() === 'z'){ e.preventDefault(); e.shiftKey ? plRedo() : plUndo(); return; }
    if (ctrl && k.toLowerCase() === 'y'){ e.preventDefault(); plRedo(); return; }
    if (k === 'PageUp' || k === 'PageDown'){ e.preventDefault(); PL.floor = Math.max(-2, Math.min(2, PL.floor + (k === 'PageUp' ? 1 : -1))); PL.sel = null; plRender(); plSide(); return; }
    if (PL.paint && k === 'Escape'){ PL.paint = null; plRender(); plSide(); return; }
    // stairs being placed, or picked: R turns them, arrows move them, Delete hands them back to the Workshop
    if (PL.placing){
      if (k === 'r' || k === 'R'){ e.preventDefault(); PL.placing.up = PL_TURN[PL.placing.up]; plRender(); }
      else if (k === 'Escape'){ PL.placing = null; plRender(); plSide(); }
      return;
    }
    if (PL.selStair != null){
      const f = PL.selStair, P = plData(), shown = plStairsShown().find(s => s.floor === f);
      const pin = P.stairPins[f] || (shown && {x: shown.tiles[0][0], y: shown.tiles[0][1], up: shown.up});
      if (pin && (k === 'r' || k === 'R')){ e.preventDefault(); plSnap(); P.stairPins[f] = {...pin, up: PL_TURN[pin.up]}; plChanged(); return; }
      if (pin && k.startsWith('Arrow')){
        e.preventDefault(); plSnap();
        P.stairPins[f] = {...pin, x: pin.x + (k === 'ArrowRight' ? 1 : k === 'ArrowLeft' ? -1 : 0), y: pin.y + (k === 'ArrowUp' ? 1 : k === 'ArrowDown' ? -1 : 0)};
        plChanged(); return;
      }
      if ((k === 'Delete' || k === 'Backspace') && P.stairPins[f]){ e.preventDefault(); plSnap(); delete P.stairPins[f]; plChanged(); return; }
      if (k === 'Escape'){ PL.selStair = null; plRender(); plSide(); return; }
    }
    if (!r) return;
    if (k === 'Delete' || k === 'Backspace'){ e.preventDefault(); plDelete(r); }
    else if (k === 'r' || k === 'R'){ e.preventDefault(); plRotate(r); }
    else if (ctrl && k.toLowerCase() === 'd'){ e.preventDefault(); plDuplicate(r); }
    else if (k.startsWith('Arrow')){
      e.preventDefault(); plSnap();
      const o = {...r}; r.x += k === 'ArrowRight' ? 1 : k === 'ArrowLeft' ? -1 : 0; r.y += k === 'ArrowUp' ? 1 : k === 'ArrowDown' ? -1 : 0;
      if (plOverlaps().has(r.id)){ Object.assign(r, o); PL.hist.pop(); return; }
      plChanged();
    } else if (k === 'Escape'){ PL.sel = null; plRender(); plSide(); }
  };
}

// ----- the doll's house: every floor stacked up, turned and tilted
function plRender3D(){
  const st = $('#pl-stage'), cv = $('#pl-3d'), dpr = window.devicePixelRatio || 1;
  const W = st.clientWidth, H = st.clientHeight;
  cv.width = W * dpr; cv.height = H * dpr;
  const g = cv.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, H);
  const P = plData(), R = P.rooms; if (!R.length) return;
  const col = r => PL_COLS[R.indexOf(r) % PL_COLS.length];
  const x0 = Math.min(...R.map(r => r.x)), x1 = Math.max(...R.map(r => r.x + r.w)), y0 = Math.min(...R.map(r => r.y)), y1 = Math.max(...R.map(r => r.y + r.h));
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, floors = [...new Set(R.map(r => r.floor))].sort((a, b) => a - b);
  const gap = 2.6, wallH = 0.75, span = Math.max(x1 - x0, y1 - y0, 3);
  const k = Math.min(W, H * 1.3) / (span * 1.6) * (PL.k3 || 1), cs = Math.cos(PL.yaw), sn = Math.sin(PL.yaw), ct = PL.tilt;
  const fz = f => (f - (floors[0] + floors[floors.length - 1]) / 2) * gap;
  // screen point and depth (bigger: farther away)
  const pr = (x, y, z) => { const rx = (x - cx) * cs - (y - cy) * sn, ry = (x - cx) * sn + (y - cy) * cs;
    return [W / 2 + rx * k, H / 2 - ry * k * ct - z * k * Math.sqrt(1 - ct * ct * 0.6), ry]; };
  const faces = [];
  const quad = (pts, fill, stroke, depth, lvl) => faces.push({pts, fill, stroke, depth, lvl});
  const res = PL.res && !PL.res.error && !PL.res.busy ? PL.res : null;
  const stairTiles = new Set((res ? res.stairs : []).flatMap(s => s.tiles.flatMap(t => [t[0] + ',' + t[1] + ',' + s.floor, t[0] + ',' + t[1] + ',' + (s.floor + 1)])));
  const openJoin = (a, b) => P.doors.some(d => d.kind === 'open' && ((d.a === a.id && d.b === b.id) || (d.a === b.id && d.b === a.id)));
  for (const r of R){
    const z = fz(r.floor), dim = r.floor !== PL.floor;
    for (const [x, y] of plTiles(r)){
      if (stairTiles.has(x + ',' + y + ',' + r.floor)) continue;
      const p = [pr(x, y, z), pr(x + 1, y, z), pr(x + 1, y + 1, z), pr(x, y + 1, z)];
      quad(p, col(r), '#00000055', Math.max(...p.map(q => q[2])) + 1000, r.floor);
    }
    // walls where the room ends, with gaps for doorways and the way out
    const edges = plOutside(r).concat(...R.filter(o => o !== r && o.floor === r.floor).map(o => plShared(r, o).map(e => ({...e, o}))));
    for (const e of edges){
      if (e.o && openJoin(r, e.o)) continue;
      const door = P.doors.some(d => d.kind !== 'open' && plSameEdge(d, e)) || (P.exit && P.exit.room === r.id && P.exit.x === e.x && P.exit.y === e.y && P.exit.side === e.side);
      const [ax, ay, bx, by] = plEdgeLine(e);
      // pulled in a little so walls of rooms side by side don't fight
      const d = PL_STEP[e.side], ix = -d[0] * 0.04, iy = -d[1] * 0.04;
      const h = door ? wallH * 0.25 : wallH;
      const p = [pr(ax + ix, ay + iy, z), pr(bx + ix, by + iy, z), pr(bx + ix, by + iy, z + h), pr(ax + ix, ay + iy, z + h)];
      const shade = e.side === 'N' || e.side === 'S' ? '#d9ccb0' : '#b8aa8c';
      quad(p, door ? '#f0cd87' : shade, '#00000066', (p[0][2] + p[1][2]) / 2, r.floor);
    }
  }
  // stairs: a ramp from one floor to the next
  for (const s of res ? res.stairs : []){
    const a = s.tiles[0], b = s.tiles[s.tiles.length - 1], d = PL_STEP[s.up], z0 = fz(s.floor), z1 = fz(s.floor + 1);
    const lo = [Math.min(a[0], b[0]), Math.min(a[1], b[1])], hi = [Math.max(a[0], b[0]) + 1, Math.max(a[1], b[1]) + 1];
    const n = 6;
    for (let i = 0; i < n; i++){
      const t0 = i / n, t1 = (i + 1) / n, zz = z0 + (z1 - z0) * (i + 1) / n;
      let p;
      if (d[0]){ const xa = d[0] > 0 ? lo[0] + (hi[0] - lo[0]) * t0 : hi[0] - (hi[0] - lo[0]) * t0, xb = d[0] > 0 ? lo[0] + (hi[0] - lo[0]) * t1 : hi[0] - (hi[0] - lo[0]) * t1;
        p = [pr(xa, lo[1], zz), pr(xb, lo[1], zz), pr(xb, hi[1], zz), pr(xa, hi[1], zz)]; }
      else { const ya = d[1] > 0 ? lo[1] + (hi[1] - lo[1]) * t0 : hi[1] - (hi[1] - lo[1]) * t0, yb = d[1] > 0 ? lo[1] + (hi[1] - lo[1]) * t1 : hi[1] - (hi[1] - lo[1]) * t1;
        p = [pr(lo[0], ya, zz), pr(hi[0], ya, zz), pr(hi[0], yb, zz), pr(lo[0], yb, zz)]; }
      quad(p, '#8a7650', '#00000088', Math.max(...p.map(q => q[2])) + 999, s.floor);
    }
  }
  // lower floors first; within a floor, the floor itself, then walls from the back to the front
  faces.sort((a, b) => a.lvl - b.lvl || b.depth - a.depth);
  for (const f of faces){
    g.globalAlpha = f.lvl === PL.floor ? 1 : f.lvl < PL.floor ? 0.55 : 0.28;
    g.beginPath(); f.pts.forEach((p, i) => i ? g.lineTo(p[0], p[1]) : g.moveTo(p[0], p[1])); g.closePath();
    g.fillStyle = f.fill; g.fill(); g.strokeStyle = f.stroke; g.lineWidth = 1; g.stroke();
  }
  g.globalAlpha = 1;
  // labels on the floor that's being edited
  const names = plNames();
  g.font = '600 12px Inter, sans-serif'; g.textAlign = 'center';
  for (const r of R.filter(r => r.floor === PL.floor)){
    const [lx, ly] = plLabelAt(r), [sx, sy] = pr(lx, ly, fz(r.floor));
    g.fillStyle = '#000a'; g.fillText(names[r.id], sx + 1, sy + 1); g.fillStyle = '#fff8e8'; g.fillText(names[r.id], sx, sy);
  }
  g.font = '11px Inter, sans-serif'; g.textAlign = 'left'; g.fillStyle = '#a99d84';
  floors.slice().reverse().forEach((f, i) => g.fillText((f === PL.floor ? '▶ ' : '   ') + plFloorName(f), 12, H - 14 - (floors.length - 1 - i) * 15));
}

// ----- ready-made layouts to start from
const PLAN_PRESETS = [
  {name: 'Small house', note: 'A main room and a bedroom', make: () => plBuild([['Main room', 0, 0, 3, 3, 0], ['Bedroom', 3, 0, 2, 3, 0]], [[0, 1]])},
  {name: 'House with a cellar', note: 'Main room, bedroom, a storeroom below', make: () => plBuild([['Main room', 0, 0, 3, 3, 0], ['Bedroom', 3, 0, 2, 3, 0], ['Cellar', 0, 0, 3, 3, -1]], [[0, 1]])},
  {name: 'Shop with rooms upstairs', note: 'Shop and storeroom, bedroom and study above', make: () => plBuild(
    [['Shop', 0, 0, 4, 3, 0], ['Storeroom', 4, 0, 2, 3, 0], ['Bedroom', 0, 0, 3, 3, 1], ['Study', 3, 0, 3, 3, 1]], [[0, 1], [2, 3]])},
  {name: 'Rooms along a hallway', note: 'A hallway with three rooms off it', make: () => plBuild(
    [['Hallway', 0, 0, 7, 1, 0], ['Kitchen', 0, 1, 2, 3, 0], ['Bedroom', 2, 1, 3, 3, 0], ['Storeroom', 5, 1, 2, 3, 0]], [[0, 1], [0, 2], [0, 3]])},
  {name: 'Manor', note: 'A hall in the middle, two floors of rooms', make: () => plBuild(
    [['Hall', 3, 0, 2, 5, 0], ['Dining room', 0, 0, 3, 3, 0], ['Kitchen', 0, 3, 3, 2, 0], ['Library', 5, 0, 3, 3, 0], ['Study', 5, 3, 3, 2, 0],
     ['Hall', 3, 0, 2, 5, 1], ['Bedroom', 0, 0, 3, 3, 1], ['Bedroom', 5, 0, 3, 3, 1], ['Bath', 0, 3, 3, 2, 1]], [[0, 1], [0, 2], [0, 3], [0, 4], [5, 6], [5, 7], [5, 8]], [[0, 5]])},
  {name: 'Tower', note: 'One room on each of four floors', make: () => plBuild(
    [['Cellar', 0, 0, 3, 3, -1], ['Hall', 0, 0, 3, 3, 0], ['Study', 0, 0, 3, 3, 1], ['Bedroom', 0, 0, 3, 3, 2]], [])},
];
function plBuild(rooms, doors, stairs){
  const R = rooms.map(([name, x, y, w, h, floor]) => ({id: plNewId(), name, x, y, w, h, floor}));
  const D = doors.map(([a, b]) => ({a: R[a].id, b: R[b].id, kind: 'door', ...plMid(plShared(R[a], R[b]))}));
  const g = R.find(r => r.floor === 0);
  return {rooms: R, doors: D, exit: {room: g.id, ...plMid(plOutsideOf(g, R).filter(e => e.side === 'S'))},
          stairs: (stairs || []).map(([a, b]) => ({lo: R[a].id, hi: R[b].id}))};
}
function plOutsideOf(r, R){
  const keep = CR.plan; CR.plan = {rooms: R, doors: [], stairs: []};
  try { return plOutside(r); } finally { CR.plan = keep; }
}
function plPreset(i){
  plSnap(); CR.plan = PLAN_PRESETS[i].make(); PL.sel = null; PL.floor = 0;
  plChanged(); plFit(); plRender();
  const st = plStyle();
  if (st && !st.floors && new Set(CR.plan.rooms.map(r => r.floor)).size > 1) toast(`${PLAN_PRESETS[i].name} has more than one floor: pick a style with stairs (⇅), like Hlaalu.`);
}
