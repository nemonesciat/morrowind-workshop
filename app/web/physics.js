// ---------- Physics here: gravity and collision for loose things in the 3D view, while it's on ----------
// (Rapier, web/vendor/rapier.es.js, loaded the first time it's switched on.) The building, the furniture and
// everything fixed become solid shapes from the very triangles the view draws; loose things (the same ones
// Settle moves: settle.py's loose()) become bodies shaped like their models, with gravity, high friction and
// damping, so they fall, rest and get pushed by what you drag. Things hung with nothing near under them (a
// lantern, a sword on its pegs) stay fixed. Nothing is saved while it runs: Keep where they lie writes every
// moved thing back as one Undo; Put them back leaves the mod as it was.
const PH = {on: false, R: null, world: null, bodies: new Map(), fixed: [], acc: 0, drag: null, panel: null, loading: false, centre: null, reach: 700};
// (the reach is the panel's slider, 1 to 1000, kept for next time)
try { const r = +localStorage.getItem('ph_reach'); if (r >= 1 && r <= 1000) PH.reach = r; } catch (e) {}
const PH_G = 706;              // (9.81 m/s² in game units: 72 units to the metre)
const PH_SMALL = 140;
const PH_SUNK = /flora|plant|kelp|mushroom|shrub|grass|lilypad|moss|vine|ivy|root_|roots/;
const PH_ITEMS = new Set(['WEAP', 'ARMO', 'CLOT', 'MISC', 'BOOK', 'ALCH', 'INGR', 'APPA', 'LOCK', 'PROB', 'REPA', 'LIGH']);

// (furniture's clutter, laid loose: scrap wood, a plank, a log, bones; the user's plank in mid-air didn't fall)
const PH_CLUTTER = /scrap|plank|_log|debris|rubble|bone|skull|broken|shard|_wood_?\d/;
const PH_CLUTTER_SIZE = 320;
// (furniture that things rest in or on)
// (a bar counter, not a barrel: "_bar" alone kept every barrel out as furniture that holds things)
const PH_HOLDER = /shelf|bookcase|cupboard|cabinet|closet|wardrobe|dresser|drawers|rack|counter|table|desk|bar_|_bar(?!rel)|altar|planter/;

// (the panel's "Larger things too": barrels, kegs, crates, urns, sacks and chests take part as well, up to a big
// crate's size, even when their name files them with the building, Tamriel Data's T_Dwe_DngRuin_F_ barrels; the
// user: "I'd still like to use gravity to settle them in some cases". Kept for next time)
// (not "f-urn": furn_dwrv_bed00 and the well took part as urns)
const PH_BIG = /barrel|keg|crate|(?<!f)urn|sack|basket|chest|_box|box_|_pot|jar|bucket|cask/;
try { PH.big = localStorage.getItem('ph_big') === '1'; } catch (e) {}

// the spot the reach is measured round: what the middle of the view looks at (at most 300 ahead). A spot a
// fixed 300 ahead lay past a table close by: the user's reach of 100 took the far things on it, not the near
function phLookAt(){
  const far = V3.pos.clone().addScaledVector(v3Dir(), 300);
  try {
    V3.ray.setFromCamera(new THREE.Vector2(0, 0), V3.camera);
    const h = V3.ray.intersectObjects([V3.root, V3.ground].filter(Boolean), true)[0];
    if (h && h.distance < 300) return h.point.clone();
  } catch (e) {}
  return far;
}

function phLoose(r, chosen){
  if (!r || !r.b || ['NPC_', 'CREA', 'LEVC', 'LEVI', 'DOOR'].includes(r.type)) return false;
  const low = r.id.toLowerCase(), s = r.s || 1, size = Math.max(r.b[3] - r.b[0], r.b[4] - r.b[1], r.b[5] - r.b[2]) * s;
  const bigKind = ['CONT', 'STAT', 'ACTI'].includes(r.type) && PH_BIG.test(low);
  if (PH.big && bigKind && !PH_HOLDER.test(low) && size <= PH_CLUTTER_SIZE) return true;
  // (and without it, none of them, even small: small clutter only, the user's choice; picked ones still do)
  if (bigKind && !chosen) return false;
  if (r.arch) return false;
  if (PH_SUNK.test(low) || (r.type === 'INGR' && low.includes('flor'))) return false;
  // (what you picked takes part, furniture too, as Settle it does: up to a big crate's size; but not furniture
  // that holds things: a body is a wrapped solid, so a bookshelf picked before Physics lost its boards and the
  // books in it fell through, 13 of 14 on the user's T_Imp_FurnM_Bookshelf_02. It stays solid by its own boards)
  if (['CONT', 'STAT', 'ACTI'].includes(r.type) && PH_HOLDER.test(low)) return false;     // (a small wall shelf too)
  if (chosen && ['CONT', 'STAT', 'ACTI', 'LIGH'].includes(r.type) && size <= PH_CLUTTER_SIZE) return true;
  if (r.type === 'LIGH') return size <= 40 && !/chandelier|lantern|hang|chain|sconce/.test(low);
  if (PH_ITEMS.has(r.type)) return true;
  if (!['CONT', 'STAT', 'ACTI'].includes(r.type)) return false;
  if (low.includes('furn')) return PH_CLUTTER.test(low) && size <= PH_CLUTTER_SIZE;
  return size <= PH_SMALL;
}

// the things selected when physics starts (W.sel, or every one of W.multi)
function phChosen(){
  const out = new Set();
  if (W.multi && W.multi.size > 1) for (const m of W.multi.values()) out.add(m.cell + '|' + m.k);
  else if (W.sel) out.add(W.sel.cell + '|' + W.sel.k);
  return out;
}

// what is selected now becomes what takes part: a group alone ("Only the N selected"), or a shelf, table or
// chest picked alone with the things on it (the user's bookshelf, half its books out of a reach of 148 stayed
// solid). force: only the selection, even one thing (the panel's "Just the selected", the user: "select a
// handful of objects and have physics only work on the selection")
async function phTakeSelection(force){
  PH.chosen = phChosen();
  if (PH.chosen.size === 1 && W.sel){
    const r = findRef(W.sel.cell, W.sel.k);
    if (r && PH_HOLDER.test(r.id.toLowerCase())){
      try {
        const c = await api('/api/ref/contents?' + new URLSearchParams({cell: W.sel.cell, ref: r.k}));
        for (const k of (c.on || [])) PH.chosen.add(W.sel.cell + '|' + k);
      } catch (e) {}
    }
  }
  PH.onlySel = PH.chosen.size > 1 || (force && PH.chosen.size > 0);
  // (the solid world round the group itself when it alone moves: round where you look, a group off to one
  // side fell through a floor that wasn't built)
  PH.group = null;
  const gs = [...PH.chosen].map(k => V3.objs.get(k)).filter(o => o && o.g);
  if (gs.length){
    const c = new THREE.Vector3(); gs.forEach(o => c.add(o.g.position)); c.divideScalar(gs.length);
    PH.group = {c, r: Math.max(...gs.map(o => Math.hypot(o.g.position.x - c.x, o.g.position.y - c.y)))};
  }
  if (PH.onlySel && PH.group) PH.centre = PH.group.c.clone();
}

// whether this one takes part: with "Only the selected" (on by itself when a group is picked: the user, "select
// a group of objects and make physics just apply to them") the picked ones alone, wherever they are, the rest
// solid; else every loose thing in reach, and the picked ones
function phPart(key, o){
  const mine = !!(PH.chosen && PH.chosen.has(key));
  if (PH.onlySel && PH.chosen && PH.chosen.size) return mine && phLoose(o.r, true);
  return phLoose(o.r, mine);
}

async function phToggle(on){
  if (on === PH.on || PH.loading) return;
  // (off, by the button, Esc or the panel's ✕: everything stays where it lies, saved as one Undo; the user:
  // "closing physics should just close", Put back is the way to undo)
  if (!on){ return phStop(true); }
  if (!V3.on || !V3.scene) return toast('Physics works in the 3D view: open it first.', true);
  PH.loading = true; toast('Starting physics…');
  try {
    if (!PH.R){
      const m = await import('/web/vendor/rapier.es.js');
      PH.R = m.default && m.default.World ? m.default : m;
      await (m.init || (m.default && m.default.init))();
    }
    PH.centre = null;                  // (round where you look now)
    PH.paused = false;
    await phTakeSelection(PH.forceSel);
    await phPreSettle();
    phBuild();
    PH.on = true;
    phPanel();
    toast(`Physics on: ${PH.bodies.size} loose things can fall and be pushed (${PH.held} hung ones stay put). Drag one to push the others.`);
  } catch (e){ toast('Physics could not start: ' + e.message, true); phClear(); }
  PH.loading = false;
  v3Tools();
}

// before the physics: Settle (settle.py) sets the loose things here on what's under them, out of what they're
// sunk in. A body starting half inside a floor is something a physics engine can't take: the floor is a
// surface, so a sunk crate came out 20 up, or fell through it altogether. Shown, not saved; where they were
// saved is kept, so Keep and Put back measure from there.
async function phPreSettle(){
  PH.saved = new Map();
  if (!PH.centre) PH.centre = phLookAt();
  const C = PH.centre, keys = [];
  for (const [key, o] of V3.objs){
    if (!o.g || !phPart(key, o) || o.ck !== W.key) continue;
    if (!(PH.chosen && PH.chosen.has(key)) && Math.hypot(o.g.position.x - C.x, o.g.position.y - C.y) > PH.reach) continue;
    keys.push(o.r.k);
    PH.saved.set(key, {p: o.g.position.clone(), q: o.g.quaternion.clone()});
  }
  PH.hung = new Set();
  if (!keys.length) return;
  try {
    const r = await post('/api/settle', {cell: W.key, refs: keys});
    // (what the game hangs stays fixed where it hangs, whatever is under it; hangsurvey.py)
    for (const k of (r.report && r.report.hung) || []) PH.hung.add(W.key + '|' + k);
    for (const mv of r.moves){
      const o = V3.objs.get(mv.cell + '|' + mv.ref); if (!o) continue;
      o.g.position.set(mv.p[0] - V3.origin[0], mv.p[1] - V3.origin[1], mv.p[2] - V3.origin[2]);
      o.g.updateMatrixWorld(true);
    }
  } catch (e) {}
}

// the solid world and the bodies, from what the view draws now
function phBuild(){
  const R = PH.R, T = THREE;
  phClear();
  PH.world = new R.World({x: 0, y: 0, z: -PH_G});
  PH.world.timestep = 1 / 60;
  const fixedBody = PH.world.createRigidBody(R.RigidBodyDesc.fixed());
  const loose = [];
  const inv = new T.Matrix4(), m = new T.Matrix4(), v = new T.Vector3();
  // here: round the spot the camera looks at (a few hundred bodies at most, or it crawls: 682 ran at 1.5 a second)
  if (!PH.centre) PH.centre = phLookAt();
  const C = PH.centre, near = (g, r) => Math.hypot(g.position.x - C.x, g.position.y - C.y) <= r && Math.abs(g.position.z - C.z) <= Math.max(r, 400);
  for (const [key, o] of V3.objs){
    if (!o.g || !o.r) continue;
    o.g.updateMatrixWorld(true);
    const mine = PH.chosen && PH.chosen.has(key);
    // (loose but out of reach: solid where it stands, or what falls near it went through a barrel left out)
    if (phPart(key, o) && (mine || near(o.g, PH.reach))){ loose.push([key, o]); continue; }
    if (['NPC_', 'CREA', 'LEVC'].includes(o.r.type)) continue;
    // (the solid world reaches a little further than the bodies; big pieces always count)
    const bx = new T.Box3().setFromObject(o.g), sz = bx.getSize(new T.Vector3());
    const solidR = (PH.onlySel && PH.group ? Math.max(PH.group.r, 100) : PH.reach) + 300;
    if (!near(o.g, solidR) && Math.max(sz.x, sz.y) < 600) continue;
    // (fixed: its triangles, in the world)
    const pos = [], idx = [];
    o.g.traverse(mesh => {
      if (!mesh.isMesh || !mesh.geometry || !mesh.geometry.attributes.position) return;
      const p = mesh.geometry.attributes.position, base = pos.length / 3;
      for (let i = 0; i < p.count; i++){ v.fromBufferAttribute(p, i).applyMatrix4(mesh.matrixWorld); pos.push(v.x, v.y, v.z); }
      const ix = mesh.geometry.index;
      if (ix) for (let i = 0; i < ix.count; i++) idx.push(base + ix.getX(i));
      else for (let i = 0; i < p.count; i++) idx.push(base + i);
    });
    if (idx.length >= 3){
      try { PH.fixed.push(PH.world.createCollider(R.ColliderDesc.trimesh(new Float32Array(pos), new Uint32Array(idx)).setFriction(1.0), fixedBody)); } catch (e) {}
    }
  }
  // the ground outdoors
  for (const c of Object.values(V3.lands || {})){
    const mesh = c.mesh; if (!mesh) continue;
    mesh.updateMatrixWorld(true);
    const p = mesh.geometry.attributes.position, pos = new Float32Array(p.count * 3);
    for (let i = 0; i < p.count; i++){ v.fromBufferAttribute(p, i).applyMatrix4(mesh.matrixWorld); pos.set([v.x, v.y, v.z], i * 3); }
    const ix = mesh.geometry.index;
    try { PH.fixed.push(PH.world.createCollider(R.ColliderDesc.trimesh(pos, new Uint32Array(ix.array)).setFriction(1.0), fixedBody)); } catch (e) {}
  }
  // (the solid world has to be in place before asking what's under each loose thing)
  PH.world.step();
  PH.held = 0;
  PH.t0 = performance.now();          // (the gentle start: see phCalm)
  for (const [key, o] of loose){
    const g = o.g, mine = PH.chosen && PH.chosen.has(key);
    inv.copy(g.matrixWorld).invert();
    // its corners in its own frame (scale baked in: a body has no scale), at most a few hundred
    const pts = [];
    g.traverse(mesh => {
      if (!mesh.isMesh || !mesh.geometry || !mesh.geometry.attributes.position) return;
      m.multiplyMatrices(inv, mesh.matrixWorld).premultiply(new T.Matrix4().makeScale(g.scale.x, g.scale.y, g.scale.z));
      const p = mesh.geometry.attributes.position, step = Math.max(1, Math.floor(p.count / 300));
      for (let i = 0; i < p.count; i += step){ v.fromBufferAttribute(p, i).applyMatrix4(m); pts.push(v.x, v.y, v.z); }
    });
    if (pts.length < 12) continue;
    // (a hair narrower, 3% towards its middle across but not up and down: books in a row touch as laid, and
    // would push at each other forever; its bottom stays exact, or everything sank a unit)
    let cx = 0, cy = 0;
    for (let i = 0; i < pts.length; i += 3){ cx += pts[i]; cy += pts[i + 1]; }
    cx /= pts.length / 3; cy /= pts.length / 3;
    // (books in a row overlap a little as laid: slimmer still, or the engine pushed the whole row apart at once,
    // the user: "they spring out like a system under compression")
    const shrink = o.r.type === 'BOOK' ? 0.94 : 0.97;
    for (let i = 0; i < pts.length; i += 3){ pts[i] = cx + (pts[i] - cx) * shrink; pts[i + 1] = cy + (pts[i + 1] - cy) * shrink; }
    // hung: what the game hangs (hangsurvey.py, through Settle's report), or a thing with nothing near under
    // it that touches a wall or a ceiling (a sword on its pegs, a picture, a sign). A thing in open air with
    // nothing under it falls: that's what the user switched physics on for
    const box = new T.Box3().setFromObject(g), c = box.getCenter(new T.Vector3()), half = box.getSize(new T.Vector3()).multiplyScalar(0.5);
    // (from its middle: a crate sunk into the floor has its bottom under the floor already)
    const hit = PH.world.castRay(new R.Ray({x: c.x, y: c.y, z: c.z}, {x: 0, y: 0, z: -1}), c.z - box.min.z + 48, true);
    const touches = () => [[1, 0, 0, half.x], [-1, 0, 0, half.x], [0, 1, 0, half.y], [0, -1, 0, half.y], [0, 0, 1, half.z]]
      .some(([dx, dy, dz, h]) => PH.world.castRay(new R.Ray({x: c.x, y: c.y, z: c.z}, {x: dx, y: dy, z: dz}), h + 10, true));
    const hung = (PH.hung && PH.hung.has(key)) || (!hit && !mine && touches());
    // (sunk into the board under it, as the game lays books and much else: started inside a thin shelf, the
    // engine pushed it out downwards, through the board, the user's video. Lifted onto it, a hair above)
    let lift = 0;
    if (hit && !hung){
      const surf = c.z - (hit.timeOfImpact ?? hit.toi ?? 0), sunk = surf - box.min.z;
      if (sunk > 0.05 && sunk < 12) lift = sunk + 0.3;
    }
    if (lift){ g.position.z += lift; g.updateMatrixWorld(true); }
    const desc = (hung ? R.RigidBodyDesc.fixed() : R.RigidBodyDesc.dynamic().setLinearDamping(0.6).setAngularDamping(2.0).setCcdEnabled(true))
      .setTranslation(g.position.x, g.position.y, g.position.z)
      .setRotation({x: g.quaternion.x, y: g.quaternion.y, z: g.quaternion.z, w: g.quaternion.w});
    const body = PH.world.createRigidBody(desc);
    let cd = R.ColliderDesc.convexHull(new Float32Array(pts));
    if (!cd){ const s = box.getSize(new T.Vector3()); cd = R.ColliderDesc.cuboid(s.x / 2, s.y / 2, s.z / 2); }
    // (high friction, no bounce: things settle where they land, as the user asked)
    PH.world.createCollider(cd.setFriction(1.2).setRestitution(0).setDensity(0.6), body);
    if (hung){ PH.held++; continue; }
    const sv = PH.saved && PH.saved.get(key);
    // (how far it may fall before it counts as fallen through: to the floor far under it, and 300 more)
    const deep = hit ? null : PH.world.castRay(new R.Ray({x: c.x, y: c.y, z: c.z}, {x: 0, y: 0, z: -1}), 6000, true);
    const drop = deep ? (deep.timeOfImpact ?? deep.toi ?? 0) : 0;
    PH.bodies.set(key, {body, o, low: g.position.z - drop - 300, start: sv || {p: g.position.clone(), q: g.quaternion.clone()}, from: {p: g.position.clone(), q: g.quaternion.clone()}});
  }
}

function phClear(){
  if (PH.world){ try { PH.world.free(); } catch (e) {} }
  PH.world = null; PH.bodies.clear(); PH.fixed = []; PH.acc = 0; PH.drag = null;
}

// a step a frame (fixed 1/60 s steps, at most four a frame); the view follows the bodies
function phTick(dt){
  if (!PH.on || !PH.world || PH.paused) return;
  const D = PH.drag;
  if (D){
    // (what's dragged pushes: moved where the handles have it, as a kinematic body)
    const g = D.o.g;
    D.body.setNextKinematicTranslation({x: g.position.x, y: g.position.y, z: g.position.z});
    D.body.setNextKinematicRotation({x: g.quaternion.x, y: g.quaternion.y, z: g.quaternion.z, w: g.quaternion.w});
  }
  // (up to two steps a frame; when a step is slow, one: slow motion rather than a stuck view)
  PH.acc = Math.min(PH.acc + dt, 2 / 60);
  let n = 0;
  const t0 = performance.now();
  while (PH.acc >= 1 / 60 && n < 2){ PH.world.step(); phCalm(D); PH.acc -= 1 / 60; n++; if (performance.now() - t0 > 12) { PH.acc = 0; break; } }
  if (!n) return;
  let awake = 0;
  for (const [key, b] of PH.bodies){
    if (D && D.key === key) continue;
    if (b.body.isSleeping()) continue;
    awake++;
    const t = b.body.translation(), q = b.body.rotation();
    b.o.g.position.set(t.x, t.y, t.z);
    b.o.g.quaternion.set(q.x, q.y, q.z, q.w);
    b.o.g.updateMatrixWorld(true);
    // (fallen through what should hold it: back where physics found it, and held there)
    if (t.z < (b.low ?? b.from.p.z - 300)){
      b.body.setBodyType(PH.R.RigidBodyType.Fixed, false);
      b.body.setTranslation(b.from.p, false); b.body.setRotation(b.from.q, false);
      b.o.g.position.copy(b.from.p); b.o.g.quaternion.copy(b.from.q); b.o.g.updateMatrixWorld(true);
      PH.fell = (PH.fell || 0) + 1;
    }
  }
  PH.awake = awake;
  if (V3.selBox && V3.selBox.visible && V3.tc && V3.tc.object) V3.selBox.setFromObject(V3.tc.object);
  phPanelCount();
}

// no springing: what overlaps as laid is pushed apart by the engine all at once. For the first two seconds
// every body is held to a crawl, so leftovers ease apart; after that nothing may shoot upwards faster than
// a hop (falling and being pushed sideways are left alone; Jiggle's hop of 40-60 is under it).
const PH_CALM_S = 2.0;
function phCalm(D){
  const R = PH.R, early = (performance.now() - (PH.t0 || 0)) / 1000 < PH_CALM_S;
  for (const [key, b] of PH.bodies){
    if (D && D.key === key) continue;
    const body = b.body;
    if (body.isSleeping()) continue;
    const v = body.linvel(), w = body.angvel();
    let vx = v.x, vy = v.y, vz = v.z;
    if (early){
      const sp = Math.hypot(vx, vy, Math.max(0, vz)), cap = 30;
      if (sp > cap){ const k = cap / sp; vx *= k; vy *= k; if (vz > 0) vz *= k; }
      const ws = Math.hypot(w.x, w.y, w.z);
      if (ws > 1.5){ const k = 1.5 / ws; body.setAngvel({x: w.x * k, y: w.y * k, z: w.z * k}, false); }
    } else if (vz > 120) vz = 120;
    if (vx !== v.x || vy !== v.y || vz !== v.z) body.setLinvel({x: vx, y: vy, z: vz}, false);
    // (at rest: the engine's own sleep is set for metres, and in the game's units a leaning row of books crept
    // a unit every few seconds and never slept, each waking its neighbours. Slower than this for most of a
    // second, it is held still by heavy damping until a drag or a Jiggle lets everything go again: phLoosen)
    if (!b.calm && Math.hypot(vx, vy, vz) < 4 && Math.hypot(w.x, w.y, w.z) < 0.15){
      b.still = (b.still || 0) + 1;
      if (b.still > 45){ body.setLinearDamping(40); body.setAngularDamping(40); b.calm = true; }
    } else if (!b.calm) b.still = 0;
  }
}
function phLoosen(){
  for (const b of PH.bodies.values()){
    if (!b.calm) continue;
    b.body.setLinearDamping(0.6); b.body.setAngularDamping(2.0); b.calm = false; b.still = 0;
  }
}

function phDragStart(){
  if (!PH.on || !V3.drag || V3.drag.group) return;
  const b = PH.bodies.get(V3.drag.key); if (!b) return;
  phLoosen();
  b.body.setBodyType(PH.R.RigidBodyType.KinematicPositionBased, true);
  PH.drag = {key: V3.drag.key, body: b.body, o: b.o};
}
// let go: it falls and rests; nothing is saved (true: the 3D view's own save is skipped)
function phDragEnd(D){
  if (!PH.on) return false;
  if (PH.drag){
    PH.drag.body.setBodyType(PH.R.RigidBodyType.Dynamic, true);
    PH.drag.body.setLinvel({x: 0, y: 0, z: 0}, true); PH.drag.body.setAngvel({x: 0, y: 0, z: 0}, true);
    PH.drag = null;
    for (const b of PH.bodies.values()) b.body.wakeUp();
    return true;
  }
  // (a fixed thing or a group moved by hand: saved as ever, and the solid world built again round it)
  setTimeout(() => { if (PH.on) phRebuildKeep(); }, 1500);
  return false;
}
// the solid world again (after a fixed piece moved), keeping where the loose things lie now
function phRebuildKeep(){
  const now = new Map([...PH.bodies].map(([k, b]) => [k, {p: b.o.g.position.clone(), q: b.o.g.quaternion.clone(), start: b.start}]));
  phBuild();
  for (const [k, b] of PH.bodies){
    const n = now.get(k); if (!n) continue;
    b.body.setTranslation(n.p, true); b.body.setRotation(n.q, true); b.start = n.start;
    b.o.g.position.copy(n.p); b.o.g.quaternion.copy(n.q);
  }
}

// what moved, as the game keeps it
function phMoves(){
  const moves = [];
  for (const [key, b] of PH.bodies){
    const g = b.o.g;
    if (g.position.distanceTo(b.start.p) < 0.3 && g.quaternion.angleTo(b.start.q) < 0.009) continue;
    const r = b.o.r, p = r.p.slice(), e = new THREE.Euler().setFromQuaternion(g.quaternion, 'XYZ');
    p[0] = g.position.x + V3.origin[0]; p[1] = g.position.y + V3.origin[1]; p[2] = g.position.z + V3.origin[2];
    p[3] = -e.x; p[4] = -e.y; p[5] = ((-e.z) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI);
    moves.push({cell: b.o.ck, ref: r.k, p, s: r.s || 1});
  }
  return moves;
}

async function phStop(keep){
  const moves = keep ? phMoves() : [];
  PH.on = false;
  phClear();
  PH.centre = null;
  if (PH.panel){ PH.panel.remove(); PH.panel = null; }
  v3Tools();
  if (keep && moves.length){
    if (!await needProject()){ v3Refresh(); return; }
    await groupAction('/api/group/move', {moves}, `Physics: kept where ${moves.length} thing${moves.length === 1 ? ' lies' : 's lie'}`);
  } else {
    v3Refresh();                        // (back where they were saved)
    toast(keep ? 'Physics off: nothing moved.' : 'Put back where they were.');
  }
}
// the panel's Put back: everything taking part back where it was saved, and held there (paused) until Run;
// the panel stays (the user: "put back should just put back the items, not close the menu")
function phPutBack(){
  if (!PH.on) return;
  for (const b of PH.bodies.values()){
    const s = b.start;
    b.o.g.position.copy(s.p); b.o.g.quaternion.copy(s.q); b.o.g.updateMatrixWorld(true);
    if (b.body.isFixed && b.body.isFixed()) continue;
    b.body.setTranslation(s.p, false); b.body.setRotation(s.q, false);
    b.body.setLinvel({x: 0, y: 0, z: 0}, false); b.body.setAngvel({x: 0, y: 0, z: 0}, false);
    b.from = {p: s.p.clone(), q: s.q.clone()};
  }
  phLoosen();
  PH.paused = true;
  phPanel();
  toast('Put back where they were. Press Run to let them fall again.');
}
// Pause / Run: the bodies held where they are, or let go again (with the gentle start)
function phPauseToggle(){
  if (!PH.on) return;
  PH.paused = !PH.paused;
  if (!PH.paused){ PH.t0 = performance.now(); PH.acc = 0; phLoosen(); for (const b of PH.bodies.values()) b.body.wakeUp(); }
  phPanel();
}
// the panel's Keep: where they lie saved (one Undo), and physics carries on from there with the same things
async function phKeepGoing(){
  const moves = phMoves();
  if (!moves.length) return toast('Nothing has moved yet.');
  if (!await needProject()) return;
  const force = PH.onlySel;
  PH.on = false; phClear();
  await groupAction('/api/group/move', {moves}, `Physics: kept where ${moves.length} thing${moves.length === 1 ? ' lies' : 's lie'}`);
  PH.forceSel = force;
  await phToggle(true);
  PH.forceSel = false;
}

// the reach changed: the bodies again round the same spot, those still in reach where they lie now, those
// left out back where they were saved (Keep only writes what takes part)
function phSetReach(r){
  PH.reach = Math.max(1, Math.min(1000, Math.round(r)));
  try { localStorage.setItem('ph_reach', String(PH.reach)); } catch (e) {}
  if (!PH.on || !PH.world) return;
  const old = new Map(PH.bodies);
  phRebuildKeep();
  for (const [k, b] of old){
    if (PH.bodies.has(k)) continue;
    b.o.g.position.copy(b.start.p); b.o.g.quaternion.copy(b.start.q); b.o.g.updateMatrixWorld(true);
  }
  phPanelCount();
}

// Esc while physics is on: off, put back, nothing saved (not while typing in a box)
document.addEventListener('keydown', e => {
  if (e.key !== 'Escape' || !PH.on || PH.loading) return;
  const t = e.target; if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable) && !(PH.panel && PH.panel.contains(t))) return;
  e.preventDefault(); e.stopPropagation();
  phStop(true);
}, true);

function phPanel(){
  // (drawn again after Pause, Put back or Keep: where you dragged it stays)
  const was = PH.panel ? {left: PH.panel.style.left, top: PH.panel.style.top, bottom: PH.panel.style.bottom} : null;
  if (PH.panel) PH.panel.remove();
  const p = document.createElement('div'); p.id = 'phpanel';
  p.style.cssText = 'position:absolute;left:12px;bottom:12px;z-index:25;background:var(--panel);border:1px solid var(--line2);border-radius:8px;padding:8px 10px;max-width:320px;box-shadow:0 4px 16px #0007';
  if (was){ p.style.left = was.left; p.style.top = was.top; p.style.bottom = was.bottom; }
  p.innerHTML = `<div data-ph="grip" style="display:flex;align-items:center;gap:8px;cursor:move;user-select:none" title="Drag to move this panel"><b>🧲 Physics</b><button class="btn sm ${PH.paused ? 'primary' : ''}" data-ph="pause" style="padding:0 8px" title="${PH.paused ? 'Let them fall again' : 'Hold everything where it is'}">${PH.paused ? '▶ Run' : '⏸ Pause'}</button><span class="msg" id="phcount"></span>
      <button class="btn sm" data-ph="close" style="margin-left:auto;padding:0 6px" title="Close; everything stays where it lies (Esc)">✕</button></div>
    <div class="msg" style="margin:4px 0 6px;line-height:1.4">Loose things fall; drag one to push others. Closing (✕ or Esc) leaves them where they lie, as one Undo. A picked shelf or table brings everything on it.</div>
    <label class="msg" style="display:flex;align-items:center;gap:6px;margin:0 0 6px" title="How far from the spot you looked at loose things take part">Reach
      <input type="range" min="1" max="1000" step="1" value="${PH.reach}" data-ph="reach" style="flex:1"><span data-ph="reachv" style="min-width:3.2em;text-align:right">${PH.reach}</span></label>
    <div style="display:flex;gap:6px;align-items:center;margin:0 0 6px"><button class="btn sm" data-ph="sel" title="Select things (Shift+click or drag a box), then press this: only they move">◎ Just the selected</button>${PH.onlySel ? '' : '<span class="msg">or all in reach</span>'}</div>
    ${PH.chosen && (PH.chosen.size > 1 || PH.onlySel) ? `<label class="msg" style="display:flex;align-items:center;gap:6px;margin:0 0 6px" title="On: only the things you picked move, wherever they are; everything else stays solid. Off: every loose thing in reach takes part, these too"><input type="checkbox" data-ph="only" ${PH.onlySel ? 'checked' : ''}> Only the ${PH.chosen.size} selected</label>` : ''}
    <label class="msg" style="display:flex;align-items:center;gap:6px;margin:0 0 6px" title="Off: only small loose things (cups, books, bones). On: barrels, kegs, crates, urns, sacks and chests fall and settle too"><input type="checkbox" data-ph="big" ${PH.big ? 'checked' : ''}> Larger things too (barrels, crates)</label>
    <div style="display:flex;gap:6px;flex-wrap:wrap"><button class="btn sm primary" data-ph="keep" title="Save where they lie now, and carry on">✔ Keep where they lie</button><button class="btn sm" data-ph="back" title="Back where they were saved, held still until Run">↶ Put back</button>
    <button class="btn sm" data-ph="jiggle" title="A little shake: everything loose wakes and settles again">〰 Jiggle</button></div>`;
  ($('#v3wrap') || document.body).appendChild(p);
  PH.panel = p;
  p.querySelector('[data-ph=keep]').onclick = () => phKeepGoing();
  p.querySelector('[data-ph=back]').onclick = () => phPutBack();
  p.querySelector('[data-ph=pause]').onclick = () => phPauseToggle();
  p.querySelector('[data-ph=close]').onclick = () => phStop(true);
  const rs = p.querySelector('[data-ph=reach]'), rv = p.querySelector('[data-ph=reachv]');
  rs.oninput = () => { rv.textContent = rs.value; };
  rs.onchange = () => phSetReach(+rs.value);           // (on letting go: a rebuild takes a moment)
  // (bigger things in or out: the same rebuild as a new reach)
  const only = p.querySelector('[data-ph=only]');
  if (only) only.onchange = e => {
    PH.onlySel = e.target.checked;
    // (round the group again, or round where you look)
    PH.centre = PH.onlySel && PH.group ? PH.group.c.clone() : phLookAt();
    phSetReach(PH.reach);
  };
  p.querySelector('[data-ph=sel]').onclick = async () => {
    if (!W.sel && !(W.multi && W.multi.size)) return toast('Select what should move first: Shift+click, or drag a box on empty space.');
    await phTakeSelection(true);
    phSetReach(PH.reach);
    phPanel();
  };
  p.querySelector('[data-ph=big]').onchange = e => { PH.big = e.target.checked; try { localStorage.setItem('ph_big', PH.big ? '1' : '0'); } catch (x) {} phSetReach(PH.reach); };
  // (moved by its title row, kept inside the view)
  const grip = p.querySelector('[data-ph=grip]');
  grip.onmousedown = e => {
    if (e.button !== 0 || e.target.closest('button')) return;
    e.preventDefault();
    const host = p.parentElement.getBoundingClientRect(), r0 = p.getBoundingClientRect(), dx = e.clientX - r0.left, dy = e.clientY - r0.top;
    const mv = ev => {
      const x = Math.max(0, Math.min(host.width - r0.width, ev.clientX - host.left - dx));
      const y = Math.max(0, Math.min(host.height - r0.height, ev.clientY - host.top - dy));
      p.style.left = x + 'px'; p.style.top = y + 'px'; p.style.bottom = 'auto';
    };
    const up = () => { removeEventListener('mousemove', mv); removeEventListener('mouseup', up); };
    addEventListener('mousemove', mv); addEventListener('mouseup', up);
  };
  p.querySelector('[data-ph=jiggle]').onclick = () => {
    phLoosen();
    for (const b of PH.bodies.values()){
      // (a hop of a few units and a little turn, whatever it weighs)
      b.body.setLinvel({x: (Math.random() - 0.5) * 30, y: (Math.random() - 0.5) * 30, z: 40 + Math.random() * 20}, true);
      b.body.setAngvel({x: (Math.random() - 0.5) * 1.5, y: (Math.random() - 0.5) * 1.5, z: (Math.random() - 0.5) * 1.5}, true);
    }
  };
}
function phPanelCount(){
  const c = PH.panel && PH.panel.querySelector('#phcount'); if (!c) return;
  const txt = `${PH.bodies.size} loose · ${PH.awake || 0} moving`;
  if (c.textContent !== txt) c.textContent = txt;
}

if (typeof CF_ACT !== 'undefined') CF_ACT.push({id: 'physics', label: 'Physics here (gravity and collision for loose things, while it\'s on)', keys: [], world: true, run: () => phToggle(!PH.on)});
