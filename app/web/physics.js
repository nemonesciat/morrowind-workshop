// ---------- Physics here: gravity and collision for loose things in the 3D view, while it's on ----------
// (Rapier, web/vendor/rapier.es.js, loaded the first time it's switched on.) The building, the furniture and
// everything fixed become solid shapes from the very triangles the view draws; loose things (the same ones
// Settle moves: settle.py's loose()) become bodies shaped like their models, with gravity, high friction and
// damping, so they fall, rest and get pushed by what you drag. Things hung with nothing near under them (a
// lantern, a sword on its pegs) stay fixed. Nothing is saved while it runs: Keep where they lie writes every
// moved thing back as one Undo; Put them back leaves the mod as it was.
const PH = {on: false, R: null, world: null, bodies: new Map(), fixed: [], acc: 0, drag: null, panel: null, loading: false, centre: null, reach: 700};
const PH_G = 706;              // (9.81 m/s² in game units: 72 units to the metre)
const PH_SMALL = 140;
const PH_SUNK = /flora|plant|kelp|mushroom|shrub|grass|lilypad|moss|vine|ivy|root_|roots/;
const PH_ITEMS = new Set(['WEAP', 'ARMO', 'CLOT', 'MISC', 'BOOK', 'ALCH', 'INGR', 'APPA', 'LOCK', 'PROB', 'REPA', 'LIGH']);

// (furniture's clutter, laid loose: scrap wood, a plank, a log, bones; the user's plank in mid-air didn't fall)
const PH_CLUTTER = /scrap|plank|_log|debris|rubble|bone|skull|broken|shard|_wood_?\d/;
const PH_CLUTTER_SIZE = 320;

function phLoose(r, chosen){
  if (!r || r.arch || !r.b || ['NPC_', 'CREA', 'LEVC', 'LEVI', 'DOOR'].includes(r.type)) return false;
  const low = r.id.toLowerCase(), s = r.s || 1, size = Math.max(r.b[3] - r.b[0], r.b[4] - r.b[1], r.b[5] - r.b[2]) * s;
  if (PH_SUNK.test(low) || (r.type === 'INGR' && low.includes('flor'))) return false;
  // (what you picked takes part, furniture too, as Settle it does: up to a big crate's size)
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

async function phToggle(on){
  if (on === PH.on || PH.loading) return;
  if (!on){ return phAsk(); }
  if (!V3.on || !V3.scene) return toast('Physics works in the 3D view: open it first.', true);
  PH.loading = true; toast('Starting physics…');
  try {
    if (!PH.R){
      const m = await import('/web/vendor/rapier.es.js');
      PH.R = m.default && m.default.World ? m.default : m;
      await (m.init || (m.default && m.default.init))();
    }
    PH.centre = null;                  // (round where you look now)
    PH.chosen = phChosen();
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
  if (!PH.centre) PH.centre = V3.pos.clone().addScaledVector(v3Dir(), 300);
  const C = PH.centre, keys = [];
  for (const [key, o] of V3.objs){
    if (!o.g || !phLoose(o.r, PH.chosen && PH.chosen.has(key)) || o.ck !== W.key) continue;
    if (Math.hypot(o.g.position.x - C.x, o.g.position.y - C.y) > PH.reach) continue;
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
  if (!PH.centre) PH.centre = V3.pos.clone().addScaledVector(v3Dir(), 300);
  const C = PH.centre, near = (g, r) => Math.hypot(g.position.x - C.x, g.position.y - C.y) <= r && Math.abs(g.position.z - C.z) <= Math.max(r, 400);
  for (const [key, o] of V3.objs){
    if (!o.g || !o.r) continue;
    o.g.updateMatrixWorld(true);
    const mine = PH.chosen && PH.chosen.has(key);
    if (phLoose(o.r, mine)){ if (mine || near(o.g, PH.reach)) loose.push([key, o]); continue; }
    if (['NPC_', 'CREA', 'LEVC'].includes(o.r.type)) continue;
    // (the solid world reaches a little further than the bodies; big pieces always count)
    const bx = new T.Box3().setFromObject(o.g), sz = bx.getSize(new T.Vector3());
    if (!near(o.g, PH.reach + 300) && Math.max(sz.x, sz.y) < 600) continue;
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
    for (let i = 0; i < pts.length; i += 3){ pts[i] = cx + (pts[i] - cx) * 0.97; pts[i + 1] = cy + (pts[i + 1] - cy) * 0.97; }
    // hung: what the game hangs (hangsurvey.py, through Settle's report), or a thing with nothing near under
    // it that touches a wall or a ceiling (a sword on its pegs, a picture, a sign). A thing in open air with
    // nothing under it falls: that's what the user switched physics on for
    const box = new T.Box3().setFromObject(g), c = box.getCenter(new T.Vector3()), half = box.getSize(new T.Vector3()).multiplyScalar(0.5);
    // (from its middle: a crate sunk into the floor has its bottom under the floor already)
    const hit = PH.world.castRay(new R.Ray({x: c.x, y: c.y, z: c.z}, {x: 0, y: 0, z: -1}), c.z - box.min.z + 48, true);
    const touches = () => [[1, 0, 0, half.x], [-1, 0, 0, half.x], [0, 1, 0, half.y], [0, -1, 0, half.y], [0, 0, 1, half.z]]
      .some(([dx, dy, dz, h]) => PH.world.castRay(new R.Ray({x: c.x, y: c.y, z: c.z}, {x: dx, y: dy, z: dz}), h + 10, true));
    const hung = (PH.hung && PH.hung.has(key)) || (!hit && !mine && touches());
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
  if (!PH.on || !PH.world) return;
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
  while (PH.acc >= 1 / 60 && n < 2){ PH.world.step(); PH.acc -= 1 / 60; n++; if (performance.now() - t0 > 12) { PH.acc = 0; break; } }
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

function phDragStart(){
  if (!PH.on || !V3.drag || V3.drag.group) return;
  const b = PH.bodies.get(V3.drag.key); if (!b) return;
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
    toast(keep ? 'Nothing moved.' : 'Put back where they were.');
  }
}
function phAsk(){
  const n = phMoves().length;
  if (!n) return phStop(false);
  pnlMenu({x: innerWidth / 2, y: innerHeight / 3}, [
    {label: `✔ Keep where they lie (${n} moved; one Undo)`, act: () => phStop(true)},
    {label: '↶ Put them back as they were', act: () => phStop(false)},
    {label: 'Keep physics on', act: () => {}}]);
}

function phPanel(){
  if (PH.panel) PH.panel.remove();
  const p = document.createElement('div'); p.id = 'phpanel';
  p.style.cssText = 'position:absolute;left:12px;bottom:12px;z-index:25;background:var(--panel);border:1px solid var(--line2);border-radius:8px;padding:8px 10px;max-width:320px;box-shadow:0 4px 16px #0007';
  p.innerHTML = `<div style="display:flex;align-items:center;gap:8px"><b>🧲 Physics on</b><span class="msg" id="phcount"></span></div>
    <div class="msg" style="margin:4px 0 6px;line-height:1.4">Loose things fall and rest; drag one to push the others. Hung things and the building stay put. Nothing is saved until you keep it.</div>
    <div style="display:flex;gap:6px;flex-wrap:wrap"><button class="btn sm primary" data-ph="keep">✔ Keep where they lie</button><button class="btn sm" data-ph="back">↶ Put back</button>
    <button class="btn sm" data-ph="jiggle" title="A little shake: everything loose wakes and settles again">〰 Jiggle</button></div>`;
  ($('#v3wrap') || document.body).appendChild(p);
  PH.panel = p;
  p.querySelector('[data-ph=keep]').onclick = () => phStop(true);
  p.querySelector('[data-ph=back]').onclick = () => phStop(false);
  p.querySelector('[data-ph=jiggle]').onclick = () => {
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
