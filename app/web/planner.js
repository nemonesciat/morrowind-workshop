// ---------- Room planner for Build from pieces ----------
// Rooms are rectangles of floor tiles on a grid, on up to five floors. Drag a room to move it, drag its
// corners or the tabs on its sides to resize it. Click the wall between two rooms to put a doorway in
// it (or take it out again), click an outside wall to put the way out there. The stairs are worked out
// by the Workshop from the style's own stair pieces and drawn on both floors they join; drag them to put
// them somewhere yourself, and they stay there. R turns them.
// "3D" shows every floor stacked up like a doll's house; drag to turn it.
const PL_FLOORS = [[2, 'Top floor'], [1, 'Upstairs'], [0, 'Ground floor'], [-1, 'Cellar'], [-2, 'Lower cellar']];
const PL_NAMES = ['Bedroom', 'Kitchen', 'Hall', 'Storeroom', 'Study', 'Dining room', 'Library', 'Shop', 'Shrine', 'Guard room', 'Bath', 'Hallway'];
// (the game's own rooms, median over 11,000 of them: a bedroom, study or shop is 3 x 2 far more often than 3 x 3,
// a shrine 4 x 3, a hall two or three tiles, a corridor one tile wide and three long; see layoutsurvey.py)
const PL_SIZES = {Bedroom: [3, 2], Kitchen: [3, 2], Hall: [2, 3], Storeroom: [2, 2], Study: [3, 2], 'Dining room': [3, 3], Library: [3, 3],
  Shop: [3, 2], Shrine: [4, 3], 'Guard room': [3, 3], Bath: [2, 2], Hallway: [1, 3]};
const PL_COLS = ['#7a5a26', '#4c6634', '#2f5a70', '#6e3c5c', '#6b6526', '#3c4c78', '#7a4a2e', '#2f6b5e', '#6b3434', '#56607a'];
const PL = {view: 'plan', floor: 0, sel: null, hover: null, drag: null, z: 34, ox: 0, oy: 0, yaw: 0.7, tilt: 0.55, hist: [], fut: [], res: null, resKey: null,
  spots: null, spotsKey: null};
// a floor's name: the one you gave it (double-click its tab, or Rename in the Floors list), else the usual
const plFloorDefault = f => (PL_FLOORS.find(x => x[0] === f) || [0, 'Floor ' + f])[1];
const plFloorName = f => (typeof CR !== 'undefined' && CR.plan && CR.plan.floorNames || {})[f] || plFloorDefault(f);
// what a room is for, as Auto-furnish will read it from its name (the same words furnish.py goes by);
// shown on the plan when the name doesn't say it ("Nemo's room" is a bedroom)
const PL_KIND_WORDS = [['dining', 'dining room'], ['refectory', 'mess'], ['barracks', 'barracks'], ['bunk', 'barracks'], ['dormitory', 'barracks'],
  ['sleeping quarters', 'barracks'], ['armoury', 'armoury'], ['armory', 'armoury'], ['arms room', 'armoury'], ['weapon store', 'armoury'],
  ['training', 'training room'], ['practice', 'training room'], ['drill', 'training room'], ['sparring', 'training room'], ['mess', 'mess'], ['canteen', 'mess'],
  ['guard', 'guard room'], ['watch room', 'guard room'], ['gatehouse', 'guard room'], ['bath', 'bath'], ['washroom', 'bath'], ['privy', 'bath'], ['lavatory', 'bath'],
  ['bed', 'bedroom'], ['sleep', 'bedroom'], ['kitchen', 'kitchen'], ['cook', 'kitchen'], ['pantry', 'kitchen'], ['store', 'storeroom'], ['cellar', 'storeroom'],
  ['storage', 'storeroom'], ['study', 'study'], ['library', 'study'], ['office', 'study'], ['shop', 'shop'], ['trader', 'shop'], ['shrine', 'shrine'], ['chapel', 'shrine'],
  ['temple', 'shrine'], ['hall', 'hall'], ['corridor', 'hall'], ['landing', 'hall'], ['passage', 'hall'], ['entrance', 'hall'], ['entry', 'hall'], ['foyer', 'hall'],
  ['vestibule', 'hall'], ['gallery', 'hall'], ['tavern', 'tavern'], ['inn', 'tavern'], ['club', 'tavern'], ['bar', 'tavern'], ['living', 'living room'], ['main', 'living room'],
  ['common', 'living room'], ['parlor', 'living room'], ['parlour', 'living room'], ['camp', 'camp'], ['cave', 'camp'], ['mine', 'camp'], ['den', 'camp'], ['ruin', 'ruin'], ['vault', 'ruin']];
function plKind(r){
  const low = (r.name || '').toLowerCase();
  for (const [w, k] of PL_KIND_WORDS) if (low.includes(w)) return k;
  return Math.min(r.w, r.h) === 1 ? 'hall' : plTiles(r).length <= 4 ? 'bedroom' : 'living room';
}
// the kind worth showing beside the name: none when the name already says it ("Master bedroom")
function plKindShown(r, name){ const k = plKind(r); return (name || r.name || '').toLowerCase().includes(k) ? '' : k; }
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
// a blank slate: the drawing thrown away (rooms, doorways, floors, stairs and their pins), one room left to
// start from; a step in the planner's own undo, so ↶ brings it back
function plClear(){
  const P = plData();
  const n = (P.rooms || []).length;
  if (n > 1 || (P.doors || []).length || (P.stairs || []).length){
    if (!confirm('Throw this plan away (' + n + ' room' + (n === 1 ? '' : 's') + ') and start again from one room? Undo (↶) brings it back.')) return;
  }
  plSnap();
  CR.plan = plDefault();
  PL.floor = 0;
  plChanged(); plFit(); plRender();
  if (typeof toast === 'function') toast('Plan cleared: one room to start from. Undo brings the old plan back.');
}

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
  for (const k of ['stairPins', 'stairOut', 'stairWas']){ P[k] = P[k] || {}; for (const f of Object.keys(P[k])) if (!has(+f) || !has(+f + 1)) delete P[k][f]; }
  // one stairwell: a single spot for every floor's stairs, kept as the pin of the lowest pair of floors
  // (the flights above stand over it facing the same way, or carry on from its head in a line)
  if (P.stairwell){
    const low = plStairLow();
    if (low != null){
      const src = P.stairPins[P.stairSrc] || P.stairPins[low] || Object.values(P.stairPins)[0];
      P.stairPins = src ? {[low]: {x: src.x, y: src.y, up: src.up}} : {};
    }
  }
}
// the lowest floor that has stairs up from it (rooms on it and on the floor above)
function plStairLow(){
  const P = plData(), has = f => P.rooms.some(r => r.floor === f);
  const fs = [...new Set(P.rooms.map(r => r.floor))].sort((a, b) => a - b).filter(f => has(f + 1));
  return fs.length ? fs[0] : null;
}
// which floor's pin a stair on floor f goes by: its own, or the one stairwell's
function plPinFloor(f){ const low = plData().stairwell ? plStairLow() : null; return low == null ? f : low; }
function plChanged(){ plFix(); plSave(); plRender(); plSide(); plAsk(); if (typeof bShells === 'function' && CR.bstyles){ clearTimeout(bShellT); bShellT = setTimeout(bShells, 600); } }

// ----- what the Workshop gets (same shape as before: rooms, doors, exit, stairs)
function bLayout(){
  const P = plData(), N = plNames();
  const first = P.rooms.find(r => r.floor === 0) || P.rooms[0];
  return {
    rooms: P.rooms.map(r => Object.assign({name: N[r.id], x: r.x, y: r.y, w: r.w, h: r.h, floor: r.floor}, r.tall ? {tall: true} : {},
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
  // (stairs nobody put by hand stay near where the plan showed them last, rather than jumping about
  // whenever a room changes)
  for (const [f, p] of Object.entries(P.stairWas || {})) if (!(P.stairPins || {})[f]) at(+f).near = {x: p.x, y: p.y, up: p.up};
  if (P.stairwell){
    // one stairwell: every flight stands over the one below, the same way up (the Workshop stacks them),
    // or "in a line": each flight carries on from the head of the one below
    const has = f => P.rooms.some(r => r.floor === f);
    for (const f of new Set(P.rooms.map(r => r.floor))) if (has(f + 1)) at(f).stack = P.stairRun ? 'line' : true;
  }
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
  // (one stairwell: moving or placing moves every floor's flight, so they are all drawn from the pin)
  const well = P.stairwell && live != null;
  const floors = new Set(P.rooms.map(r => r.floor));
  for (const s of res ? res.stairs : []){
    PL.stLen[s.floor] = s.tiles.length;
    if (s.floor === live || well) continue;
    const pin = s.moved && P.stairPins && P.stairPins[s.floor];
    if (pin){
      // (the Workshop would stand them elsewhere: yours stay where you put them, drawn as a ghost, and its
      // spot is a faint hint behind them)
      out.push({floor: s.floor, tiles: plPinTiles(pin, s.tiles.length), up: pin.up, pinned: true, ghost: true, bad: true});
      out.push({floor: s.floor, tiles: s.tiles.map(t => [t[0], t[1]]), up: s.up, pinned: false, hint: true, land: s.land || []});
      continue;
    }
    out.push({floor: s.floor, tiles: s.tiles.map(t => [t[0], t[1]]), up: s.up, pinned: !!s.pinned, land: s.land || []});
  }
  for (const [fs, p] of Object.entries(P.stairPins || {})){
    const f = +fs; if (out.some(s => s.floor === f) || f === live || well) continue;
    if (floors.has(f) && floors.has(f + 1)) out.push({floor: f, tiles: plPinTiles(p, PL.stLen[f] || 2), up: p.up, pinned: true, ghost: true, bad: !!(PL.res && PL.res.error)});
  }
  if (live != null){
    const p = PL.placing ? PL.placing : P.stairPins[live];
    if (p && p.x != null){
      const fl = well ? [...floors].filter(f => floors.has(f + 1)).sort((a, b) => a - b) : [live];
      // (in a line: each floor's flight starts a tile past the head of the one below)
      let q = {x: p.x, y: p.y, up: p.up};
      for (const f of fl){
        const len = PL.stLen[f] || PL.stLen[live] || 2;
        out.push({floor: f, tiles: plPinTiles(q, len), up: p.up, pinned: true, ghost: true});
        if (well && P.stairRun){ const d = PL_STEP[p.up]; q = {x: q.x + d[0] * (len + 1), y: q.y + d[1] * (len + 1), up: p.up}; }
      }
    }
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
    // stairs put by hand where the Workshop would rather stand them elsewhere (only two short flights with
    // a strip of void would fit there): the pin stays where you put it (it used to follow the Workshop's
    // choice, so the stairs jumped away after every drop); the Workshop's spot is kept as a suggestion,
    // drawn faintly, with a button in the panel to take it
    const P = plData(); PL.suggest = {};
    // (where the Workshop has the stairs nobody put by hand: they stay about there next time)
    if (PL.res && PL.res.stairs) P.stairWas = {};
    for (const s of (PL.res && PL.res.stairs) || []) if (!(P.stairPins || {})[s.floor] && !s.stacked && s.tiles.length)
      P.stairWas[s.floor] = {x: s.tiles[0][0], y: s.tiles[0][1], up: s.up};
    for (const s of (PL.res && PL.res.stairs) || []) if (s.moved && P.stairPins && P.stairPins[s.floor]){
      PL.suggest[s.floor] = {tiles: s.tiles.map(t => [t[0], t[1]]), up: s.up, note: s.note || ''};
    }
    plRender(); plNote(); if (!PL.sel) plSide();
  }, 350);
}

// where the stairs could stand (the Workshop's own reckoning, the same it places them by): shaded on the
// plan while you move or place the stairs, green where the style's whole stairwell fits, amber where only
// two short flights in line would. Asked for once per plan (the pins left out: they are what's moving)
let plSpotsT = 0;
function plSpotsAsk(){
  const st = $('#cr-bstyle'), L = bLayout();
  const floors = new Set(L.rooms.map(r => r.floor));
  if (floors.size < 2 || !CR.bstyles || !st || !CR.bstyles.some(x => x.id === st.value) || L.floors_as === 'linked'){ PL.spots = null; PL.spotsKey = null; return; }
  const stairs = L.stairs.map(s => { const o = {...s}; delete o.at; return o; });
  const key = JSON.stringify([st.value, L.rooms, stairs, L.doors]);
  if (PL.spotsKey === key) return;
  PL.spotsKey = key; PL.spots = null;
  clearTimeout(plSpotsT);
  plSpotsT = setTimeout(async () => {
    let r = null;
    try { r = await post('/api/build/stairspots', {style: st.value, rooms: L.rooms, stairs, doors: L.doors}); } catch (e){ r = {pairs: [], error: e.message}; }
    if (PL.spotsKey === key){ PL.spots = r; plRender(); }
  }, 150);
}
// the floor pair whose stairs are being moved, placed or picked (its pin floor), or null
function plLiveStair(){
  const f = PL.drag && PL.drag.kind === 'stair' ? PL.drag.floor : PL.placing ? PL.placing.floor : PL.selStair != null ? plPinFloor(PL.selStair) : null;
  return f == null || (PL.res && PL.res.linked) ? null : f;
}
// the pin a floor's stairs go by: the one put by hand, or where the Workshop has them now
function plStairPin(f){
  const P = plData(), shown = plStairsShown().find(s => s.floor === f);
  return P.stairPins[f] || (shown && {x: shown.tiles[0][0], y: shown.tiles[0][1], up: shown.up}) || null;
}
// a quarter turn, about the bottom step (the ↻ handle on the plan, R, or the button in the panel): the
// stairs stay pinned where they are from then on
function plTurnStair(f){
  const pf = plPinFloor(f), P = plData(), pin = plStairPin(pf); if (!pin) return;
  plSnap(); P.stairPins[pf] = {...pin, up: PL_TURN[pin.up]}; P.stairSrc = pf; PL.selStair = f; plChanged();
}
// stairs dropped by hand, lined up like real stairs: moved a tile at most so the tile below the bottom
// step is in a room on the lower floor and the top comes out in a room above (when a nudge does that and
// where they were didn't)
function plSnapStair(f){
  const P = plData(), pin = P.stairPins[f]; if (!pin || P.stairSnap === false) return false;
  const len = PL.stLen[f] || 2, d = PL_STEP[pin.up];
  const score = p => {
    const tiles = plPinTiles(p, len), a = tiles[0], b = tiles[tiles.length - 1];
    const lo = plRoomAt(a[0] - d[0], a[1] - d[1], f), hi = plRoomAt(b[0] + d[0], b[1] + d[1], f + 1);
    // (and the run itself not through a doorway's wall: the ends count most)
    return (lo ? 2 : 0) + (hi ? 2 : 0);
  };
  const was = score(pin);
  // (only when neither end lands in a room: a drop that has one end right is left where you put it; the
  // nudge after every drop was one more thing fighting the hand)
  if (was > 0) return false;
  let best = null;
  for (const dx of [0, 1, -1]) for (const dy of [0, 1, -1]){
    if (!dx && !dy) continue;
    const p = {x: pin.x + dx, y: pin.y + dy, up: pin.up}, s = score(p), cost = Math.abs(dx) + Math.abs(dy) + (dx && dy ? .5 : 0);
    if (s > was && (!best || s > best.s || (s === best.s && cost < best.cost))) best = {p, s, cost};
  }
  if (!best) return false;
  P.stairPins[f] = best.p; P.stairSrc = f;
  return true;
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
  .pl-hint{position:absolute;left:10px;top:8px;font-size:12px;color:var(--text);background:var(--panel);background:color-mix(in srgb,var(--panel) 88%,transparent);border:1px solid var(--line0);padding:3px 8px;border-radius:6px;pointer-events:none}
  .pl-zoom{position:absolute;right:8px;bottom:8px;display:flex;gap:4px}
  .pl-zoom button{width:26px;height:26px;border-radius:6px;border:1px solid var(--line);background:color-mix(in srgb,var(--bg3) 80%,transparent);color:var(--text-b);cursor:pointer}
  .pl-note{padding:6px 10px;border-top:1px solid var(--line);font-size:12px;color:var(--muted-b);background:var(--deep-c)}
  .pl-note .err{color:#ff8a6a} .pl-note .warn{color:var(--gold2)}
  .pl-menu{position:relative} .pl-menu > div{display:none;position:absolute;z-index:20;top:100%;left:0;margin-top:4px;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:4px;min-width:200px;box-shadow:0 8px 30px #000c;max-height:min(420px,70vh);overflow-y:auto}
  .pl-menu > div .note{padding:7px 9px;border-top:1px solid var(--line);margin-top:4px;color:var(--muted-b);font-size:12px;line-height:1.45;max-width:240px}
  .pl-menu.open > div{display:block} .pl-menu > div button{display:block;width:100%;text-align:left;background:none;border:0;color:var(--text-b);padding:6px 9px;border-radius:5px;cursor:pointer;font-size:13px}
  .pl-menu > div button:hover{background:var(--hover)} .pl-menu > div small{display:block;color:var(--muted-b);font-size:11px}
  .pl-menu .prow{display:flex;align-items:center} .pl-menu .prow > button:first-child{flex:1;min-width:0} .pl-menu .prow .x{width:auto;padding:4px 7px;color:var(--muted-b);font-size:12px} .pl-menu .prow .x:hover{color:#ff8a6a}
  .pl-menu .head{padding:7px 9px 3px;color:var(--gold2);font-size:11px;letter-spacing:.04em;text-transform:uppercase;border-top:1px solid var(--line);margin-top:4px}`;
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
      <div class="pl-menu" id="pl-prem"><button class="btn sm" id="pl-pre" title="Start from a ready-made layout, a plan you saved, or a place you built; save this plan">Plans ▾</button><div>
        <button id="pl-saveplan" title="Keep this plan under a name (rooms, floors, doorways, stairs and the style), to load again later or build elsewhere">💾 Save this plan…</button>
        <button id="pl-fromgame" title="One of the game's own houses, shops or taverns read as a plan: its rooms, doorways, floors and stairs, in its own style, to study how the game's builders laid it out and to build from">🏘 Plan from a place in the game…<small>A house the game made, read as a plan you can study and build from</small></button>
        <div class="head">Start from a layout</div>${PLAN_PRESETS.map((p, i) => `<button data-pre="${i}">${esc(p.name)}<small>${esc(p.note)}</small></button>`).join('')}
        <div class="head">My saved plans</div><div id="pl-loadl"><div class="note">Loading…</div></div><div id="pl-built"></div></div></div>
      <span class="sep"></span><div class="pl-tabs" id="pl-tabs"></div><span class="sep"></span>
      <div class="pl-tabs"><button data-v="plan">Plan</button><button data-v="3d">3D</button></div>
      <span class="sep"></span>
      <button class="btn sm" id="pl-undo" title="Undo (Ctrl+Z)">↶</button><button class="btn sm" id="pl-redo" title="Redo (Ctrl+Y)">↷</button>
      <button class="btn sm" id="pl-fit" title="Fit the plan in view">⤢ Fit</button>
      <button class="btn sm" id="pl-clear" title="Throw this drawing away and start again from one room (Undo brings it back)">🗑 Clear plan</button>
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
  // (looked up inside the planner: the World map's lighting panel has a "pl-save" of its own in the page,
  // and $('#pl-save') found that one first, so the old "Save plan…" button never had a handler)
  root.querySelector('#pl-saveplan').onclick = plSavePlan;
  root.querySelector('#pl-fromgame').onclick = plFromGame;
  $('#pl-pre').addEventListener('click', () => plPlansMenu());
  root.querySelectorAll('[data-v]').forEach(b => b.onclick = () => { PL.view = b.dataset.v; plRender(); });
  $('#pl-undo').onclick = plUndo; $('#pl-redo').onclick = plRedo; $('#pl-fit').onclick = () => { plFit(); plRender(); };
  root.querySelector('#pl-clear').onclick = plClear;
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
  PL.turnBtns = [];
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
  // where the stairs being moved could stand, going the way they go now: green for the style's whole
  // stairwell, amber where only two short flights in line fit
  const live = plLiveStair();
  if (live != null){
    plSpotsAsk();
    const pair = PL.spots && PL.spots.pairs && PL.spots.pairs.find(p => p.floor === live);
    const cur = PL.placing ? PL.placing : plStairPin(live);
    if (pair && cur && (f === live || f === live + 1)){
      const d = PL_STEP[cur.up];
      for (const sp of pair.spots){
        if (sp.up !== cur.up) continue;
        const colr = sp.pair ? '#e0a93a' : '#5fcf7a', X = plSX(sp.x), Y = plSY(sp.y + 1);
        s += `<rect x="${X + 1.5}" y="${Y + 1.5}" width="${z - 3}" height="${z - 3}" rx="3" fill="${colr}" fill-opacity=".32" stroke="${colr}" stroke-opacity=".7"/>`;
        if (z >= 22) s += `<path d="M${X + z / 2 - d[0] * z * .22} ${Y + z / 2 + d[1] * z * .22}L${X + z / 2 + d[0] * z * .22} ${Y + z / 2 - d[1] * z * .22}" stroke="${colr}" stroke-width="1.5" marker-end="url(#pl-arrow)" opacity=".8"/>`;
      }
    }
  }
  // stairs: where the Workshop put them, or where you're putting them (drag them, R turns them)
  for (const sx of plStairsShown()){
    if (sx.floor !== f && sx.floor + 1 !== f) continue;
    const up = sx.floor === f, colr = sx.hint ? '#9c917c' : sx.bad ? '#ff8a6a' : '#f0cd87', chosen = PL.selStair === sx.floor && !sx.hint;
    if (sx.hint){
      // the Workshop's own spot for stairs you put elsewhere: a faint outline, nothing to grab
      for (const t of sx.tiles) s += `<rect x="${plSX(t[0])}" y="${plSY(t[1] + 1)}" width="${z}" height="${z}" fill="none" stroke="${colr}" stroke-opacity=".55" stroke-dasharray="2 4" style="pointer-events:none"/>`;
      const a0 = sx.tiles[0];
      s += `<text x="${plSX(a0[0] + .5)}" y="${plSY(a0[1] + .5) + 4}" fill="${colr}" fill-opacity=".8" font-size="9" text-anchor="middle" style="pointer-events:none">fits here</text>`;
      continue;
    }
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
    // a turn handle on the stairs you picked (or put by hand): a click turns them a quarter turn
    if ((chosen || sx.pinned) && !sx.ghost || (chosen && sx.ghost && !PL.drag && !PL.placing)){
      const hx = plSX(Math.max(...sx.tiles.map(t => t[0])) + 1) + 9, hy = plSY(Math.max(...sx.tiles.map(t => t[1])) + 1) - 9;
      PL.turnBtns.push({x: hx, y: hy, floor: sx.floor});
      s += `<g transform="translate(${hx} ${hy})"><circle r="9" fill="${PL.hover && PL.hover.kind === 'stturn' ? '#fff0c0' : '#f0cd87'}" stroke="#000"/><text y="4" font-size="12" text-anchor="middle" fill="#000" style="pointer-events:none">↻</text></g>`;
    }
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
  // names, what the room is for (when the name doesn't say and there's room for it), and sizes
  for (const r of here){
    const [lx, ly] = plLabelAt(r), cx = plSX(lx), cy = plSY(ly), small = r.w * z < 70;
    const kind = !small && r.h * z >= 50 ? plKindShown(r, names[r.id]) : '';
    s += `<text x="${cx}" y="${cy + (small ? 4 : 0)}" fill="#fff8e8" font-size="${Math.min(13, Math.max(9, z / 3))}" font-weight="600" text-anchor="middle" style="paint-order:stroke" stroke="#0008" stroke-width="3">${esc(names[r.id].length > 16 ? names[r.id].slice(0, 15) + '…' : names[r.id])}</text>`;
    if (kind) s += `<text x="${cx}" y="${cy + 13}" fill="#f0cd87dd" font-size="10" font-style="italic" text-anchor="middle" style="paint-order:stroke" stroke="#0006" stroke-width="2">${esc(kind)}</text>`;
    if (!small && (!kind || r.h * z >= 68)) s += `<text x="${cx}" y="${cy + 14 + (kind ? 12 : 0)}" fill="#fff8e8aa" font-size="10" text-anchor="middle">${plSizeText(r)}</text>`;
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
  box.innerHTML = PL_FLOORS.slice().reverse().map(([f]) => `<button data-fl="${f}" class="${f === PL.floor ? 'on' : ''}" title="${esc(plFloorName(f))} · double-click to rename it">${esc(plFloorName(f))}${count(f) ? `<span class="n">${count(f)}</span>` : ''}</button>`).join('');
  box.querySelectorAll('[data-fl]').forEach(b => { b.onclick = () => { PL.floor = +b.dataset.fl; PL.sel = null; plRender(); plSide(); }; b.ondblclick = () => plRenameFloor(+b.dataset.fl); });
}
// ----- floors as a whole: rename one, copy one to an empty floor, mirror the plan (one Undo each)
async function plRenameFloor(f){
  const name = await askText(`A name for this floor (empty: back to "${plFloorDefault(f)}")`, plFloorName(f));
  if (name == null) return;
  plSnap(); const P = plData(); P.floorNames = P.floorNames || {};
  if (name.trim() && name.trim() !== plFloorDefault(f)) P.floorNames[f] = name.trim().slice(0, 24); else delete P.floorNames[f];
  plChanged();
}
function plDupFloor(f, g){
  const P = plData(), src = P.rooms.filter(r => r.floor === f);
  if (!src.length || g === f) return;
  if (P.rooms.some(r => r.floor === g)) return toast(plFloorName(g) + ' already has rooms. Copy onto an empty floor.', true);
  plSnap();
  const map = {};
  for (const r of src){
    const c = {...r, id: plNewId(), floor: g, add: (r.add || []).map(t => t.slice()), cut: (r.cut || []).map(t => t.slice())};
    delete c.tall;       // (a two-storey hall over its own copy would open into it)
    map[r.id] = c.id; P.rooms.push(c);
  }
  for (const d of P.doors.slice()) if (map[d.a] && map[d.b]) P.doors.push({...d, a: map[d.a], b: map[d.b]});
  P.walls = (P.walls || []).concat((P.walls || []).filter(w => map[w[0]] && map[w[1]]).map(w => [map[w[0]], map[w[1]]]));
  PL.floor = g; PL.sel = null; PL.resKey = null; PL.spotsKey = null;
  plChanged();
  toast(`${plFloorName(f)} copied to ${plFloorName(g)} (${src.length} room${src.length === 1 ? '' : 's'}, with its doorways). Undo takes it back.`);
}
// the whole plan turned over: left-right (about a north-south line) or front-back (about an east-west one);
// rooms, their shapes, doorways, the way out and the stairs you pinned all go with it
function plMirror(axis){
  const P = plData(); plSnap();
  const lr = axis === 'x', flip = s => lr ? ({E: 'W', W: 'E'}[s] || s) : ({N: 'S', S: 'N'}[s] || s);
  for (const r of P.rooms){
    const t = lr ? v => [r.w - 1 - v[0], v[1]] : v => [v[0], r.h - 1 - v[1]];
    r.add = (r.add || []).map(t); r.cut = (r.cut || []).map(t);
    if (lr) r.x = -(r.x + r.w); else r.y = -(r.y + r.h);
  }
  const edge = e => { if (!e || e.x == null) return; if (lr) e.x = -e.x - 1; else e.y = -e.y - 1; e.side = flip(e.side); };
  for (const d of P.doors) if (d.kind !== 'open') edge(d);
  edge(P.exit);
  for (const pin of Object.values(P.stairPins || {})){ if (lr) pin.x = -pin.x - 1; else pin.y = -pin.y - 1; pin.up = flip(pin.up); }
  PL.resKey = null; PL.spotsKey = null;
  plChanged(); plFit(); plRender();
  toast(`The plan is mirrored ${lr ? 'left to right' : 'front to back'}. Undo turns it back.`);
}
// the Floors list in the side panel (no room selected): names, copies, mirroring
function plFloorsHtml(){
  const P = plData(), floors = [...new Set(P.rooms.map(r => r.floor))].sort((a, b) => b - a);
  const empty = PL_FLOORS.map(x => x[0]).filter(f => !floors.includes(f)).sort((a, b) => b - a);
  return `<h4 style="margin-top:14px">Floors</h4>` + floors.map(f => `<div class="row" style="flex-wrap:wrap"><span style="min-width:0;flex:1"><b>${esc(plFloorName(f))}</b> <span style="color:var(--muted-b)">${P.rooms.filter(r => r.floor === f).length} room${P.rooms.filter(r => r.floor === f).length === 1 ? '' : 's'}</span></span>
      <button class="btn sm" data-flren="${f}" title="Give this floor a name of your own">Rename</button>
      ${empty.length ? `<select class="inp" data-fldup="${f}" style="width:auto;font-size:12px" title="Copy this floor's rooms and doorways onto an empty floor"><option value="">Copy to…</option>${empty.map(g => `<option value="${g}">${esc(plFloorName(g))}</option>`).join('')}</select>` : ''}</div>`).join('') +
    `<div style="margin-top:10px"><div style="color:var(--muted-b);margin-bottom:4px">Mirror the whole plan, every floor</div>
      <button class="btn sm" data-mirror="x" title="Turn the plan over left to right">↔ Left–right</button> <button class="btn sm" data-mirror="y" title="Turn the plan over front to back">↕ Front–back</button></div>`;
}
function plBindFloors(box){
  box.querySelectorAll('[data-flren]').forEach(b => b.onclick = () => plRenameFloor(+b.dataset.flren));
  box.querySelectorAll('[data-fldup]').forEach(s => s.onchange = () => { if (s.value !== '') plDupFloor(+s.dataset.fldup, +s.value); });
  box.querySelectorAll('[data-mirror]').forEach(b => b.onclick = () => plMirror(b.dataset.mirror));
}
function plHint(){
  const h = $('#pl-hint'); if (!h) return;
  const hv = PL.hover;
  const shade = PL.spots && PL.spots.pairs && PL.spots.pairs.some(p => p.spots.length) ? ' · green: the stairwell fits, amber: only two short flights' : '';
  h.textContent = PL.view === '3d' ? 'Drag to turn it, scroll to zoom. Edit rooms in Plan.' :
    PL.placing ? 'Click where the bottom step of the stairs goes · R turns them · Esc stops' + shade :
    PL.paint ? (PL.paint.mode === 'add' ? 'Click or drag on the marked tiles to add them to the room · Esc when done' : 'Click or drag on the room\'s tiles to take them away · Esc when done') :
    PL.drag && PL.drag.kind === 'stair' ? 'Let go to put the stairs here (they line up with the room\'s edge)' + shade :
    hv && hv.kind === 'stturn' ? 'Click: turn the stairs a quarter turn' :
    hv && hv.kind === 'stair' ? (hv.s.pinned ? 'Drag to move the stairs · ↻ or R turns them · Delete lets the Workshop choose' : 'Drag the stairs to put them where you want them · click, then ↻ turns them') + (PL.selStair != null ? shade : '') :
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
  if (floors.length > 1 && !(CR.bstyles && CR.bstyles.length)) msgs.push('The stairs come once the styles have loaded (the box above says "Loading styles…" meanwhile).');
  else if (PL.res && PL.res.busy) msgs.push('Working out where the stairs go…');
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
    const low = plStairLow(), well = !!P.stairwell && low != null && !(PL.res && PL.res.linked);
    for (const f of floors) if (floors.includes(f + 1)){
      const cur = P.stairs.find(s => plRoom(s.lo) && plRoom(s.lo).floor === f);
      const lo = P.rooms.filter(x => x.floor === f), hi = P.rooms.filter(x => x.floor === f + 1);
      const linked = PL.res && PL.res.linked, pin = (P.stairPins || {})[f], picked = PL.selStair === f;
      const shown = !linked && plStairsShown().find(s => s.floor === f);
      // (one stairwell: the flights above the lowest stand over it; only the lowest has the controls)
      if (well && f !== low){
        pairs.push(`<div style="${picked ? 'border:1px solid var(--goldline);border-radius:8px;padding:6px;margin:6px -6px;background:#f0cd870d' : ''}">
          <div class="row"><span style="min-width:100%">Stairs from the ${esc(plFloorName(f).toLowerCase())} up</span></div>
          <div class="tip">${P.stairRun ? '⇈ On from the top of the stairs below, in one long run.' : '⇅ Over the stairs below, in the same stairwell, facing the same way.'} Drag any flight to move them all; ↻ turns them all.</div></div>`);
        continue;
      }
      pairs.push(`<div style="${picked ? 'border:1px solid var(--goldline);border-radius:8px;padding:6px;margin:6px -6px;background:#f0cd870d' : ''}">
        <div class="row" style="flex-wrap:wrap"><span style="min-width:100%">${linked ? (f < 0 ? 'Trapdoor down to the ' + esc(plFloorName(f).toLowerCase()) : 'Door up from the ' + esc(plFloorName(f).toLowerCase())) : 'Stairs from the ' + esc(plFloorName(f).toLowerCase()) + ' up' + (well ? ' (and the stairwell above)' : '')}</span></div>
        ${linked ? '' : pin ? `<div class="row" style="flex-wrap:wrap"><span style="min-width:0;color:var(--muted-b)">📌 Where you put them. Drag to move, <b>R</b> turns.</span><button class="btn sm" data-stturn="${f}" title="A quarter turn, about the bottom step (R)">↻ Turn</button><button class="btn sm" data-stfree="${f}" title="Forget where you put them: the Workshop finds the best spot again, and may move them (Delete)">Let the Workshop choose</button></div>${PL.suggest && PL.suggest[f] ? `<div class="row" style="flex-wrap:wrap"><span style="min-width:0;color:var(--muted-b)">They don't quite fit there; the faint outline on the plan is where they would. Built as they are, the Workshop stands them at that spot.</span><button class="btn sm" data-stsuggest="${f}" title="Move the stairs to the spot the Workshop found">↪ Use that spot</button></div>` : ''}`
          : `<div class="row" style="flex-wrap:wrap"><span style="min-width:0;color:var(--muted-b)">Where they fit best; they stay about there while you change the rooms. Drag to move, <b>R</b> turns.</span>${shown ? `<button class="btn sm" data-stturn="${f}" title="A quarter turn, about the bottom step (R); they then stay where they are">↻ Turn</button><button class="btn sm" data-stkeep="${f}" title="Pin them where they are now, so nothing you change moves them">📌 Keep here</button>` : ''}<button class="btn sm" data-stplace="${f}" title="The stairs follow the mouse; click where the bottom step goes (R turns them first)">✥ Place by hand</button></div>`}
      </div>`);
    }
    // three floors or more: one stairwell carrying through, or stairs wherever they fit on each floor
    const wellChoice = floors.filter(f => floors.includes(f + 1)).length >= 2 && !(PL.res && PL.res.linked)
      ? `<label class="tip" style="display:flex;gap:6px;align-items:flex-start;margin:6px 0 2px"><input type="checkbox" data-stwell ${P.stairwell ? 'checked' : ''}><span><b>One stairwell</b>: every floor's stairs together. Drag any flight to move them all.</span></label>${P.stairwell ? `
        <label class="tip" style="display:flex;gap:6px;align-items:flex-start;margin:2px 0 2px 22px"><input type="radio" name="pl-strun" value="stack" ${P.stairRun ? '' : 'checked'}><span><b>Stacked</b>: each flight over the one below, all facing the same way; you walk round the landing to the next.</span></label>
        <label class="tip" style="display:flex;gap:6px;align-items:flex-start;margin:2px 0 4px 22px"><input type="radio" name="pl-strun" value="line" ${P.stairRun ? 'checked' : ''}><span><b>In a line</b>: one long climb, each flight starting just past the top of the last, with a way off at every floor. The rooms need to reach along the whole run.</span></label>` : ''}` : '';
    // (the how-to folds away once the plan has rooms; it stays a click away)
    const howto = `<details class="tip" ${P.rooms.length > 1 ? '' : 'open'} style="margin-bottom:6px"><summary style="cursor:pointer;color:var(--text-b)">How the planner works</summary>
      <b>Drag</b> a room to move it, its <b>corners or side tabs</b> to resize it.<br>
      Click the <b>wall between two rooms</b> for a doorway; click it again to take it out. Click an <b>outside wall</b> for the way out.<br>
      Use the <b>floor tabs</b> for a cellar or upstairs: the rooms below show faintly, and the stairs are put in for you where they fit best. <b>Drag the stairs</b> to put them where you want (the plan shades where they can stand); click them, then <b>↻</b> (or <b>R</b>) turns them.<br>
      Rooms needn't be rectangles: select one and use <b>✏ Add tiles</b> or <b>⌫ Take away</b>.<br>
      Under <b>Floors</b>: rename a floor (or double-click its tab), copy one onto an empty floor, mirror the plan.<br>
      <b>Keys:</b> Delete, R turns, arrows move, Ctrl+D copies, Ctrl+Z undoes.</details>`;
    box.innerHTML = `<h4>Planning the rooms</h4>${howto}
      ${pairs.length ? plJoinChoice() : ''}
      ${pairs.length ? '<h4 style="margin-top:14px">' + (PL.res && PL.res.linked ? 'Between floors' : 'Stairs') + '</h4>' + wellChoice + pairs.join('') : ''}
      ${plFloorsHtml()}`;
    plBindFloors(box);
    box.querySelectorAll('[name=pl-join]').forEach(r => r.onchange = () => { plSnap(); P.join = r.value; PL.resKey = null; plChanged(); });
    box.querySelectorAll('[data-stwell]').forEach(c => c.onchange = () => { plSnap(); P.stairwell = c.checked; PL.resKey = null; plChanged(); });
    box.querySelectorAll('[name=pl-strun]').forEach(r => r.onchange = () => { plSnap(); P.stairRun = r.value === 'line'; PL.resKey = null; plChanged(); });
    box.querySelectorAll('[data-stturn]').forEach(b => b.onclick = () => plTurnStair(+b.dataset.stturn));
    box.querySelectorAll('[data-stair]').forEach(s => s.onchange = () => {
      plSnap(); const f = +s.dataset.stair;
      P.stairs = P.stairs.filter(x => !(plRoom(x.lo) && plRoom(x.lo).floor === f));
      P.stairOut = P.stairOut || {};
      if (s.value === 'out') P.stairOut[f] = true; else delete P.stairOut[f];
      if (s.value && s.value !== 'out'){ const [lo, hi] = s.value.split('|'); P.stairs.push({lo, hi}); }
      plChanged();
    });
    box.querySelectorAll('[data-stfree]').forEach(b => b.onclick = () => {
      // (forgotten too: where they were last, so the Workshop looks afresh rather than leaving them there)
      const f = plPinFloor(+b.dataset.stfree); plSnap(); delete P.stairPins[f]; if (P.stairWas) delete P.stairWas[f]; plChanged();
      toast('The Workshop is choosing where the stairs go; if they stay put, that spot was already its best.');
    });
    box.querySelectorAll('[data-stsuggest]').forEach(b => b.onclick = () => {
      const f = +b.dataset.stsuggest, sg = PL.suggest && PL.suggest[f]; if (!sg) return;
      plSnap(); P.stairPins[f] = {x: sg.tiles[0][0], y: sg.tiles[0][1], up: sg.up}; P.stairSrc = f; PL.selStair = f; plChanged();
    });
    box.querySelectorAll('[data-stkeep]').forEach(b => b.onclick = () => {
      const f = plPinFloor(+b.dataset.stkeep), s = plStairsShown().find(x => x.floor === f); if (!s) return;
      plSnap(); P.stairPins[f] = {x: s.tiles[0][0], y: s.tiles[0][1], up: s.up}; P.stairSrc = f; PL.selStair = f; plChanged();
      toast('The stairs stay there now, whatever you change. Drag them to move them.');
    });
    box.querySelectorAll('[data-stplace]').forEach(b => b.onclick = () => {
      const f = plPinFloor(+b.dataset.stplace), s = plStairsShown().find(x => x.floor === f);
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
    <div class="tip" style="margin-bottom:6px">Auto-furnish goes by the name: this one is furnished as a <b>${esc(plKind(r))}</b>.</div>
    <div class="row"><span>Size</span><input class="inp" type="number" min="1" max="16" id="pl-w" value="${r.w}" style="width:58px"><span style="min-width:0">×</span><input class="inp" type="number" min="1" max="16" id="pl-h" value="${r.h}" style="width:58px"><span style="min-width:0">tiles</span></div>
    <div class="row" style="flex-wrap:wrap"><span>Shape</span><button class="btn sm${PL.paint && PL.paint.mode === 'add' ? ' primary' : ''}" id="pl-padd" title="Click or drag on tiles next to the room to make them part of it">✏ Add tiles</button><button class="btn sm${PL.paint && PL.paint.mode === 'cut' ? ' primary' : ''}" id="pl-pcut" title="Click or drag on the room's tiles to take them away">⌫ Take away</button>${plShaped(r) ? '<button class="btn sm" id="pl-prect" title="Back to its plain rectangle">▭ Rectangle again</button>' : ''}</div>
    ${PL.paint ? `<div class="tip">${PL.paint.mode === 'add' ? 'Click or drag on the tiles marked round the room to add them' : 'Click or drag on the room\'s tiles to take them away'}. <b>Esc</b> or the button again when you're done.</div>` : ''}
    <div class="row"><span>Floor</span><select class="inp" id="pl-floor" style="flex:1">${PL_FLOORS.map(([v]) => `<option value="${v}" ${v === r.floor ? 'selected' : ''}>${esc(plFloorName(v))}</option>`).join('')}</select></div>
    <label class="tip" style="display:flex;gap:6px;align-items:flex-start;margin:4px 0"><input type="checkbox" id="pl-tall" ${r.tall ? 'checked' : ''}><span><b>Two storeys tall</b>: open to the floor above wherever no room is drawn over it, the way the game builds its guild halls: a ceiling slab at the top, pillars at the opening's corners, and the rooms you draw round it upstairs become a gallery with a railing. Draw the upstairs rooms round the part you want open.</span></label>
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
  $('#pl-tall').onchange = () => { plSnap(); if ($('#pl-tall').checked) r.tall = true; else delete r.tall; plChanged(); };
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
  // the turn handle on the picked stairs
  for (const b of PL.turnBtns || []) if (Math.hypot(sx - b.x, sy - b.y) <= 11) return {kind: 'stturn', f: b.floor};
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
  // the stairs (on either floor they join): grab them to move them. Anywhere inside their tiles but a thin
  // band at the very edge is the stairs, not the wall line beside them (the wall's band used to reach a
  // fifth of the way into each tile, so a grab near the stairs' side panned the map or made a doorway)
  const tx = Math.floor(px), ty = Math.floor(py);
  const stair = plStairsShown().find(s => (s.floor === f || s.floor + 1 === f) && s.tiles.some(t => t[0] === tx && t[1] === ty));
  const edgeBand = Math.min(0.08, 3 / PL.z);
  if (stair && !stair.hint && dv >= edgeBand && dh >= edgeBand) return {kind: 'stair', s: stair};
  cands.sort((a, b) => a[0] - b[0]);
  for (const [, vertical] of cands){ const h = tryEdge(vertical); if (h) return plEdgeHit(h); }
  if (stair && !stair.hint) return {kind: 'stair', s: stair};
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
      const p = PL.placing, pf = plPinFloor(p.floor); plSnap();
      P.stairPins[pf] = {x: p.x, y: p.y, up: p.up}; P.stairSrc = pf;
      if (plSnapStair(pf)) toast('Lined the stairs up with the room\'s edge.');
      PL.selStair = p.floor; PL.placing = null; PL.sel = null; plChanged(); return;
    }
    if (w.kind === 'stturn'){ plTurnStair(w.f); return; }
    if (w.kind === 'stair'){
      // grab the stairs: moving them puts them there for good (until you hand them back)
      // (one stairwell: every floor's flight goes by the lowest pair's pin, so they all move together)
      const s = w.s, pf = plPinFloor(s.floor), base = plStairsShown().find(x => x.floor === pf) || s;
      const pin = P.stairPins[pf] || {x: base.tiles[0][0], y: base.tiles[0][1], up: base.up};
      PL.selStair = s.floor; PL.sel = null; plSnap();
      PL.drag = {kind: 'stair', floor: pf, sx, sy, orig: {...pin}, had: !!P.stairPins[pf], moved: false};
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
      if (d.moved){ plData().stairPins[d.floor] = {x: d.orig.x + dx, y: d.orig.y + dy, up: d.orig.up}; plData().stairSrc = d.floor; plRender(); }
      return;
    }
    if (!d){ if (PL.view === 'plan'){ const w = plWhat(sx, sy); const k = JSON.stringify([w.kind, w.e, w.k, w.r && w.r.id, w.remove]);
      if (k !== PL.hoverKey){ PL.hoverKey = k; PL.hover = w; st.style.cursor = w.kind === 'door' || w.kind === 'exit' || w.kind === 'stturn' ? 'pointer' : w.kind === 'room' || w.kind === 'stair' ? 'move' :
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
      if (plSnapStair(d.floor)) toast('Lined the stairs up with the room\'s edge.');
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
      const f = plPinFloor(PL.selStair), P = plData(), pin = plStairPin(f);
      if (pin && (k === 'r' || k === 'R')){ e.preventDefault(); plTurnStair(PL.selStair); return; }
      if (pin && k.startsWith('Arrow')){
        e.preventDefault(); plSnap();
        P.stairPins[f] = {...pin, x: pin.x + (k === 'ArrowRight' ? 1 : k === 'ArrowLeft' ? -1 : 0), y: pin.y + (k === 'ArrowUp' ? 1 : k === 'ArrowDown' ? -1 : 0)};
        P.stairSrc = f; plChanged(); return;
      }
      if ((k === 'Delete' || k === 'Backspace') && P.stairPins[f]){ e.preventDefault(); plSnap(); delete P.stairPins[f]; if (P.stairWas) delete P.stairWas[f]; plChanged(); return; }
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
// (the game's commonest layouts, from a survey of all 2,600 of its hand-made interiors: the way in opens into the
// main room, which has the bed in it; a study, shop or storeroom beside it; more bedrooms in the cellar or upstairs;
// a manor is a living room with bedrooms and a study off it, never a long hall with rooms on both sides)
const PLAN_PRESETS = [
  {name: 'Dunmer house', note: 'A main room with the bed, a study beside it (Hlaalu, Velothi, Redoran)', make: () => plBuild(
    [['Bedroom', 0, 0, 3, 2, 0], ['Study', 3, 0, 2, 2, 0]], [[0, 1]])},
  // (no stairs pinned: the Workshop puts them where they fit best, and they can be dragged from there)
  {name: 'Dunmer house with a cellar', note: 'The same over a cellar bedroom', make: () => plBuild(
    [['Bedroom', 0, 0, 3, 2, 0], ['Study', 3, 0, 2, 2, 0], ['Cellar bedroom', 0, 0, 3, 2, -1]], [[0, 1]], [[2, 0]])},
  {name: 'Common house', note: 'Living room below, bedroom upstairs (two storeys, like most Common and Mournhold houses)', make: () => plBuild(
    [['Living room', 0, 0, 3, 2, 0], ['Bedroom', 0, 0, 3, 2, 1]], [], [[0, 1]])},
  {name: 'Gold Coast house', note: 'A big main room and a sitting room, bedroom above', make: () => plBuild(
    [['Bedroom', 0, 0, 3, 3, 0], ['Living room', 3, 0, 2, 2, 0], ['Bedroom', 0, 0, 3, 2, 1]], [[0, 1]], [[0, 2]])},
  {name: 'Shop', note: 'Shop at the way in, storeroom beside it, bedroom upstairs', make: () => plBuild(
    [['Shop', 0, 0, 3, 2, 0], ['Storeroom', 3, 0, 2, 2, 0], ['Bedroom', 0, 0, 3, 2, 1]], [[0, 1]], [[0, 2]])},
  {name: 'Tavern', note: 'Tavern at the way in, two bedrooms off a hallway upstairs', make: () => plBuild(
    [['Tavern', 0, 0, 4, 3, 0], ['Hallway', 0, 0, 4, 1, 1], ['Bedroom', 0, 1, 2, 2, 1], ['Bedroom', 2, 1, 2, 2, 1]], [[1, 2], [1, 3]], [[0, 1]])},
  {name: 'Rooms along a hallway', note: 'A hallway with three rooms off it (the Imperial way)', make: () => plBuild(
    [['Hallway', 0, 0, 7, 1, 0], ['Kitchen', 0, 1, 2, 3, 0], ['Bedroom', 2, 1, 3, 3, 0], ['Storeroom', 5, 1, 2, 3, 0]], [[0, 1], [0, 2], [0, 3]])},
  {name: 'Manor', note: 'A living room in the middle with a bedroom and a study off it, the same again upstairs', make: () => plBuild(
    [['Living room', 3, 0, 3, 3, 0], ['Bedroom', 0, 0, 3, 3, 0], ['Study', 6, 0, 3, 3, 0],
     ['Living room', 3, 0, 3, 3, 1], ['Bedroom', 0, 0, 3, 3, 1], ['Bedroom', 6, 0, 3, 3, 1]], [[0, 1], [0, 2], [3, 4], [3, 5]], [[0, 3]])},
  {name: 'Tower', note: 'One room on each of four floors, one stairwell carrying through', make: () => plBuild(
    [['Cellar', 0, 0, 3, 3, -1], ['Hall', 0, 0, 3, 3, 0], ['Study', 0, 0, 3, 3, 1], ['Bedroom', 0, 0, 3, 3, 2]], [], [], null, true)},
];
// pins: {floor: {x, y, up}}, the stairs put by hand (a spot that builds clean for the layout's style family,
// found by building each layout and looking it through); well: one stairwell carrying through every floor
function plBuild(rooms, doors, stairs, pins, well){
  const R = rooms.map(([name, x, y, w, h, floor]) => ({id: plNewId(), name, x, y, w, h, floor}));
  const D = doors.map(([a, b]) => ({a: R[a].id, b: R[b].id, kind: 'door', ...plMid(plShared(R[a], R[b]))}));
  const g = R.find(r => r.floor === 0);
  const out = {rooms: R, doors: D, exit: {room: g.id, ...plMid(plOutsideOf(g, R).filter(e => e.side === 'S'))},
          stairs: (stairs || []).map(([a, b]) => ({lo: R[a].id, hi: R[b].id}))};
  if (pins){ out.stairPins = {}; for (const [f, p] of Object.entries(pins)) out.stairPins[f] = {x: p.x, y: p.y, up: p.up}; }
  if (well) out.stairwell = true;
  return out;
}
// "Start from the stairs": the style's stairwell on the ground floor, pinned where it stands best, with a hall
// at its foot and a bedroom at its head (the Workshop tries every way round and keeps the one that costs
// least: the whole-storey piece, no landings, the game's pieces round it). Rooms are then added round it
async function plSeedStairs(){
  const st = $('#cr-bstyle'), sty = plStyle();
  if (!st || !sty) return toast('Pick a style first.');
  if (!sty.floors) return toast(`${sty.name} has no stair pieces: pick a style with stairs (⇅), like Hlaalu.`, true);
  let r;
  try { r = await post('/api/build/stairseed', {style: st.value}); } catch (e){ return toast(e.message, true); }
  plSnap();
  CR.plan = plBuild(r.rooms.map(x => [x.name, x.x, x.y, x.w, x.h, x.floor]), [], [[0, 1]], {0: r.pin});
  CR.plan.stairSrc = 0;
  PL.sel = null; PL.selStair = 0; PL.placing = null; PL.paint = null; PL.floor = 0; PL.resKey = null;
  plChanged(); plFit(); plRender();
  const d = {N: 'north', E: 'east', S: 'south', W: 'west'}[r.pin.up];
  toast(`Started from the stairs: the ${sty.name} stairwell going ${d}, pinned, with a hall at its foot and a bedroom at its head. Add rooms round it (+ Room ▾); the stairs stay put.`);
}
// "Fit together": the Workshop tries the plan shuffled a little (each room nudged a tile each way, the
// stairs turned, moved a tile or handed back) and keeps the one where the stairs sit best; for a small
// plan the best few are built in a scratch place and looked through for holes. Undo puts it back
async function plShuffle(){
  const st = $('#cr-bstyle'), sty = plStyle(), b = $('#pl-shuffle');
  if (!st || !sty) return toast('Pick a style first.');
  const L = bLayout();
  if (new Set(L.rooms.map(r => r.floor)).size < 2) return toast('Fit together works out where the stairs sit best: it needs rooms on two floors.', true);
  if (L.floors_as === 'linked' || (PL.res && PL.res.linked)) return toast('The floors are joined by doors here, so there are no stairs to fit. Choose "Stairs" under Floors joined by.', true);
  if (plOverlaps().size) return toast('Rooms overlap: move them apart first.', true);
  if (b){ b.disabled = true; b.textContent = '⚄ Trying…'; }
  let r;
  try { r = await post('/api/build/fit', {style: st.value, rooms: L.rooms, stairs: L.stairs, doors: L.doors, floors_as: L.floors_as}); }
  catch (e){ r = {error: e.message}; }
  if (b){ b.disabled = false; b.textContent = '⚄ Fit together'; }
  if (r.error) return toast(r.error, true);
  if (!r.changed) return toast(r.note || 'Nothing fits better: the plan stays as it is.');
  plSnap();
  const P = plData();
  for (const m of r.rooms || []){ const room = P.rooms[m.i]; if (room){ room.x = m.x; room.y = m.y; } }
  P.stairPins = P.stairPins || {};
  for (const [f, p] of Object.entries(r.pins || {})){ P.stairPins[f] = {x: p.x, y: p.y, up: p.up}; P.stairSrc = +f; }
  for (const f of r.unpin || []) delete P.stairPins[f];
  PL.resKey = null; plChanged(); plMaybeFit();
  toast(r.note || 'Fitted together.');
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

// ----- saved plans (JSON files under the Workshop home, settings/plans), and the plans of places you built
// the "Load plan" menu, and the "Places you built" part of "Start from" (filled when either opens)
async function plPlansMenu(){
  const box = $('#pl-loadl'), built = $('#pl-built'); if (!box) return;
  let d;
  try { d = await api('/api/build/plans'); } catch (e){ d = {plans: [], built: [], error: e.message}; }
  if (!box.isConnected) return;
  const styleName = id => ((CR.bstyles || []).find(x => x.id === id) || {}).name || id;
  const count = (n, what) => `${n} ${what}${n === 1 ? '' : 's'}`;
  box.innerHTML = (d.plans.length ? d.plans.map(p => `<div class="prow"><button data-plan="${esc(p.name)}">${esc(p.name)}<small>${count(p.rooms, 'room')}, ${count(p.floors, 'floor')}${p.style ? ' · ' + esc(styleName(p.style)) : ''} · ${esc(p.saved)}</small></button><button class="x" data-plandel="${esc(p.name)}" title="Forget this plan">✕</button></div>`).join('')
    : `<div class="note">${d.error ? esc(d.error) : 'None yet. <b style="color:var(--text-b)">Save this plan…</b> (above) keeps the plan you have now under a name, with its style, to load again later or build elsewhere.'}</div>`);
  box.querySelectorAll('[data-plan]').forEach(b => b.onclick = async () => {
    try { const r = await api('/api/build/plans/get?name=' + encodeURIComponent(b.dataset.plan)); plUsePlan(r.plan, r.style, r.options, 'Loaded the plan "' + r.name + '".'); }
    catch (e){ toast(e.message, true); }
  });
  box.querySelectorAll('[data-plandel]').forEach(b => b.onclick = async e => {
    e.stopPropagation();
    if (!confirm('Forget the saved plan "' + b.dataset.plandel + '"?')) return;
    try { await post('/api/build/plans/delete', {name: b.dataset.plandel}); toast('Forgot the plan "' + b.dataset.plandel + '".'); plPlansMenu(); }
    catch (err){ toast(err.message, true); }
  });
  if (built) built.innerHTML = d.built.length ? '<div class="head">A place you built</div>' + d.built.map(c => `<button data-cell="${esc(c.key)}">${esc(c.name)}<small>${count(c.rooms, 'room')}, ${count(c.floors, 'floor')}${c.style ? ' · ' + esc(styleName(c.style)) : ''}</small></button>`).join('') : '';
  if (built) built.querySelectorAll('[data-cell]').forEach(b => b.onclick = async () => {
    try {
      const r = await api('/api/build/plans/cell?key=' + encodeURIComponent(b.dataset.cell));
      plUsePlan(r.plan, r.style, null, r.remembered ? 'Started from the plan of ' + b.textContent.split('\n')[0] + '.' :
        'Started from the rooms of ' + b.textContent.split('\n')[0] + ' (built before plans were kept: its doorways and stairs are worked out afresh).');
    } catch (e){ toast(e.message, true); }
  });
}
// "Plan from a place in the game": one of the game's own interiors (built from a kit's tiles) read back as a
// plan: its rooms named by what stands in them, the doorways between them, the way out, its floors and the
// stairs pinned where the game has them, in its own style. A box lists every such place, by style, with a
// search; nothing in the mod changes (route /api/build/plan_from_cell)
// Only places that pass the Workshop's gate are listed (the game's tombs, caves and sewers are out, so are
// sets with no stair pieces; the rest are tried in a dry run of the builder's planning, in a background pass
// kept on disk): best first, each with a word on how close it is ("builds as it is", "close: 2 pieces
// approximated"). While the pass runs the box fills up as places are looked at
async function plFromGame(){
  let d;
  try { d = await api('/api/build/plan_from_cell/places'); } catch (e){ return toast(e.message, true); }
  let list = d.places;
  const kitName = id => ((CR.bstyles || []).find(x => x.id === id) || {}).name || id;
  const bg = document.createElement('div'); bg.className = 'modal-bg';
  bg.innerHTML = `<div class="modal" style="width:min(620px,94vw)"><h2>Plan from a place in the game</h2>
    <div class="msg">One of the game's houses, shops or taverns as a plan: its rooms, doorways, floors and stairs, in its own style. Only places the Workshop can rebuild are listed, closest first. Nothing in your mod changes until you build.</div>
    <div style="display:flex;gap:6px;margin-top:10px;flex-wrap:wrap"><select class="inp" id="pfg-style" style="max-width:220px"></select>
      <input class="inp" id="pfg-find" placeholder="Find… (e.g. Balmora, inn, manor)" style="flex:1;min-width:160px" autocomplete="off"></div>
    <div class="msg" id="pfg-prog" style="margin-top:6px;display:none"></div>
    <div id="pfg-list" style="max-height:min(380px,55vh);overflow-y:auto;margin-top:8px;border:1px solid var(--line);border-radius:8px;padding:3px"></div>
    <div class="foot"><span class="msg" id="pfg-msg" style="flex:1;align-self:center"></span><button class="btn" id="pfg-no">Cancel</button></div></div>`;
  const sel = bg.querySelector('#pfg-style'), find = bg.querySelector('#pfg-find'), box = bg.querySelector('#pfg-list'), msg = bg.querySelector('#pfg-msg'), prog = bg.querySelector('#pfg-prog');
  const fillStyles = () => {
    const styles = [...new Set(list.map(p => p.style))].sort(), was = sel.value;
    sel.innerHTML = `<option value="">Every style (${list.length} places)</option>` + styles.map(s => `<option value="${esc(s)}">${esc(s)} (${list.filter(p => p.style === s).length})</option>`).join('');
    if (styles.includes(was)) sel.value = was;
  };
  fillStyles();
  const st = plStyle();
  // (the style picked in the form first, when the game has places in it)
  if (st){ const own = list.find(p => p.kit === st.id); if (own) sel.value = own.style; }
  const progress = () => {
    prog.style.display = d.ready ? 'none' : '';
    if (!d.ready) prog.innerHTML = `<span class="spin"></span> Looking the game's places through for ones the Workshop can build (${d.done} of ${d.total} so far; a few minutes the first time, kept from then on). The list fills up as it goes.`;
  };
  progress();
  const show = () => {
    const words = find.value.toLowerCase().split(/\s+/).filter(Boolean);
    const match = p => words.every(w => (p.name + ' ' + p.style + ' ' + kitName(p.kit) + ' ' + p.word).toLowerCase().includes(w));
    let rows = list.filter(p => (!sel.value || p.style === sel.value) && match(p));
    // (a name typed that no place of this style has: look in every style)
    if (!rows.length && words.length && sel.value){ sel.value = ''; rows = list.filter(match); }
    const count = (n, what) => `${n} ${what}${n === 1 ? '' : 's'}`;
    box.innerHTML = rows.slice(0, 300).map(p => `<button class="pfg-row" data-key="${esc(p.key)}" style="display:block;width:100%;text-align:left;background:none;border:0;color:var(--text-b);padding:5px 9px;border-radius:5px;cursor:pointer;font-size:13px">${esc(p.name)}<small style="display:block;color:var(--muted-b);font-size:11px"><span style="color:${p.rough ? 'var(--muted-b)' : p.approx ? 'var(--gold2)' : '#7fcf8a'}">${esc(p.word)}</span> · ${esc(kitName(p.kit))} · ${count(p.rooms, 'room')}, ${count(p.floors, 'floor')}</small></button>`).join('')
      + (rows.length > 300 ? `<div class="msg" style="padding:6px 9px">…and ${rows.length - 300} more: type a name to narrow it down.</div>` : '')
      + (rows.length ? '' : `<div class="msg" style="padding:8px 9px">${list.length ? 'No place matches.' : 'Nothing yet: the first places show up in a moment.'}</div>`);
    box.querySelectorAll('.pfg-row').forEach(b => {
      b.onmouseenter = () => b.style.background = '#2b241a'; b.onmouseleave = () => b.style.background = 'none';
      b.onclick = async () => {
        msg.textContent = 'Reading ' + b.textContent.split('\n')[0] + '…';
        box.querySelectorAll('.pfg-row').forEach(x => x.disabled = true);
        let r;
        try { r = await api('/api/build/plan_from_cell?cell=' + encodeURIComponent(b.dataset.key)); }
        catch (e){ msg.textContent = ''; box.querySelectorAll('.pfg-row').forEach(x => x.disabled = false); return toast(e.message, true); }
        bg.remove();
        plUsePlan(r.plan, r.style, null, null);
        // (a name for the build: the game's place keeps its own, so this one is "… (rebuilt)")
        const name = $('#cr-name'); if (name && (!name.value.trim() || / \(rebuilt\)$/.test(name.value))) name.value = (r.name + ' (rebuilt)').slice(0, 63);
        plLongToast(r.note);
      };
    });
  };
  sel.onchange = show; find.oninput = show; show();
  // (while the background pass runs: fetch again every few seconds and fill the list up)
  const again = async () => {
    if (!bg.isConnected || d.ready) return;
    try { d = await api('/api/build/plan_from_cell/places'); } catch (e){ return; }
    if (!bg.isConnected) return;
    list = d.places; fillStyles(); progress(); show();
    setTimeout(again, 4000);
  };
  if (!d.ready) setTimeout(again, 4000);
  bg.querySelector('#pfg-no').onclick = () => bg.remove();
  bg.onclick = e => { if (e.target === bg) bg.remove(); };
  find.onkeydown = e => { if (e.key === 'Escape'){ e.preventDefault(); bg.remove(); } };
  document.body.appendChild(bg); find.focus();
}
// a toast that stays long enough to read a sentence or two (what was read from a place, and what was left out)
function plLongToast(text){
  const t = document.createElement('div'); t.className = 'toast'; t.textContent = text; t.style.maxWidth = '520px';
  t.title = 'Click to dismiss'; t.onclick = () => t.remove();
  document.body.appendChild(t); setTimeout(() => t.remove(), 12000);
}
// a plan loaded or started from: it takes the place of the one on the screen (undo brings that back)
function plUsePlan(plan, style, options, note){
  if (!plan || !plan.rooms || !plan.rooms.length) return toast('That plan has no rooms in it.', true);
  plSnap();
  CR.plan = JSON.parse(JSON.stringify(plan));
  for (const r of CR.plan.rooms) if (!r.id) r.id = plNewId();
  CR.plan.doors = CR.plan.doors || []; CR.plan.stairs = CR.plan.stairs || [];
  PL.sel = null; PL.selStair = null; PL.placing = null; PL.paint = null; PL.floor = CR.plan.rooms.some(r => r.floor === 0) ? 0 : CR.plan.rooms[0].floor;
  const st = $('#cr-bstyle');
  if (style && st && (CR.bstyles || []).some(x => x.id === style) && st.value !== style){ st.value = style; CR.bstyle = style; if (st.onchange) st.onchange(); }
  if (options){
    const li = $('#cr-blight'), la = $('#cr-blamps'), fu = $('#cr-bfurnish');
    if (li && options.lighting) li.value = options.lighting;
    if (la && options.lights != null) la.checked = !!options.lights;
    if (fu && options.furnish != null) fu.checked = !!options.furnish;
  }
  PL.resKey = null; plChanged(); plFit(); plRender();
  if (note) toast(note);
}
async function plSavePlan(){
  const P = plData(); if (!P.rooms.length) return toast('Nothing to save yet: add a room first.', true);
  const name = await askText('A name for this plan:', (PL.lastSaved || ($('#cr-name') || {}).value || 'My plan').trim().slice(0, 60));
  if (!name || !name.trim()) return;
  const val = id => ($('#' + id) || {}).value, chk = id => { const e = $('#' + id); return e ? !!e.checked : null; };
  try {
    await post('/api/build/plans/save', {name: name.trim(), plan: P, style: CR.bstyle || val('cr-bstyle') || '',
      options: {lighting: val('cr-blight') || 'normal', lights: chk('cr-blamps'), furnish: chk('cr-bfurnish')}});
    PL.lastSaved = name.trim();
    toast('Saved the plan "' + name.trim() + '". It\'s under Plans ▾ from now on.');
    plPlansMenu();
  } catch (e){ toast(e.message, true); }
}
