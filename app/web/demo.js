// ---------- Demo mode: the Workshop shows itself (for videos) ----------
// Open the Workshop with #demo=furnish and it builds a house with Create → Build from pieces, then
// furnishes it with Auto-furnish in the 3D view, using the real menus: a pointer moves to each
// button and clicks it, text is typed into the fields, and captions say what's happening.
// It only runs when asked for with that link, in a mod that's open (it's a normal edit, so Undo works).
const DEMO = {on: false};
const demoSleep = ms => new Promise(r => setTimeout(r, ms));

function demoSetup(){
  if (DEMO.cursor) return;
  const css = document.createElement('style');
  css.textContent = `
    .demo-cursor{position:fixed;left:0;top:0;width:26px;height:26px;z-index:9999;pointer-events:none;
      transition:transform .9s cubic-bezier(.45,.05,.25,1);filter:drop-shadow(0 2px 4px #000c)}
    .demo-cursor.click::after{content:"";position:absolute;left:-14px;top:-14px;width:28px;height:28px;border-radius:50%;
      border:3px solid #f0cd87;animation:demo-ring .5s ease-out forwards}
    @keyframes demo-ring{from{transform:scale(.3);opacity:1}to{transform:scale(1.6);opacity:0}}
    .demo-cap{position:fixed;left:50%;bottom:34px;transform:translateX(-50%);z-index:9998;pointer-events:none;
      background:#1b1813ee;border:1px solid #d2a85a;border-radius:12px;padding:12px 22px;color:#f0e2bf;
      font:600 21px Inter,sans-serif;box-shadow:0 10px 40px #000c;max-width:80vw;text-align:center;transition:opacity .4s}
    .demo-cap small{display:block;font-weight:400;font-size:15px;color:#c9bb9b;margin-top:3px}
    .demo-cap.shot{font-size:27px;padding:16px 30px;bottom:44px;max-width:70vw}
    .demo-cap.shot small{font-size:18px;margin-top:6px;line-height:1.4}
    .demo-title{position:fixed;inset:0;z-index:9997;display:flex;flex-direction:column;align-items:center;justify-content:center;
      background:radial-gradient(#221d16,#0d0b08);color:#f0cd87;font-family:Cinzel,serif;transition:opacity .8s}
    .demo-title h1{font-size:64px;margin:0;font-weight:600} .demo-title p{font:400 24px Inter,sans-serif;color:#cdbf9f;margin:14px 0 0}`;
  document.head.appendChild(css);
  DEMO.cursor = document.createElement('div');
  DEMO.cursor.className = 'demo-cursor';
  DEMO.cursor.innerHTML = '<svg viewBox="0 0 24 24" width="26" height="26"><path d="M3 2l7 19 2.6-7.4L20 11z" fill="#fff" stroke="#000" stroke-width="1.4" stroke-linejoin="round"/></svg>';
  DEMO.cursor.style.transform = `translate(${innerWidth / 2}px, ${innerHeight / 2}px)`;
  document.body.appendChild(DEMO.cursor);
  DEMO.cap = document.createElement('div'); DEMO.cap.className = 'demo-cap'; DEMO.cap.style.opacity = 0;
  document.body.appendChild(DEMO.cap);
}
function demoCaption(text, sub){
  DEMO.cap.innerHTML = esc(text) + (sub ? `<small>${esc(sub)}</small>` : '');
  DEMO.cap.style.opacity = text ? 1 : 0;
}
async function demoMoveTo(el, dx = 0.5, dy = 0.5){
  if (typeof el === 'string') el = $(el);
  if (!el) throw new Error('demo: element not found');
  el.scrollIntoView({block: 'nearest', inline: 'nearest'});
  await demoSleep(150);
  const b = el.getBoundingClientRect();
  DEMO.cursor.style.transform = `translate(${b.left + b.width * dx}px, ${b.top + b.height * dy}px)`;
  await demoSleep(950);
  return el;
}
async function demoClick(el){
  el = await demoMoveTo(el);
  DEMO.cursor.classList.remove('click'); void DEMO.cursor.offsetWidth; DEMO.cursor.classList.add('click');
  await demoSleep(180);
  el.click();
  await demoSleep(450);
  return el;
}
async function demoType(el, text){
  el = await demoMoveTo(el, 0.15);
  el.focus(); el.value = '';
  el.dispatchEvent(new Event('input', {bubbles: true}));
  for (const ch of text){
    el.value += ch;
    el.dispatchEvent(new Event('input', {bubbles: true}));
    await demoSleep(55 + Math.random() * 45);
  }
  el.dispatchEvent(new Event('change', {bubbles: true}));
  await demoSleep(300);
}
async function demoWaitFor(test, ms = 30000){
  const t0 = Date.now();
  while (Date.now() - t0 < ms){ const v = test(); if (v) return v; await demoSleep(150); }
  throw new Error('demo: timed out');
}
function demoTitle(h, p){
  const d = document.createElement('div'); d.className = 'demo-title';
  d.innerHTML = `<h1>${esc(h)}</h1>${p ? `<p>${esc(p)}</p>` : ''}`;
  document.body.appendChild(d);
  return d;
}

// the furniture appears piece by piece: hide what Auto-furnish added, then drop it in one at a time
async function demoReveal(before, ms){
  await demoWaitFor(() => V3.objs.size > before.size, 20000);
  // wait until no more arrive (the models load over a moment), hiding them as they come
  let last = -1, still = 0;
  while (still < 6){
    for (const [k, o] of V3.objs) if (!before.has(k)) o.g.visible = false;
    if (V3.objs.size === last) still++; else { still = 0; last = V3.objs.size; }
    await demoSleep(150);
  }
  const fresh = [...V3.objs.entries()].filter(([k]) => !before.has(k)).map(([, o]) => o);
  // big things first, like someone moving in: beds, tables and shelves, then the small things
  const size = o => { const b = new THREE.Box3().setFromObject(o.g); return (b.max.x - b.min.x) * (b.max.y - b.min.y) * (b.max.z - b.min.z); };
  fresh.sort((a, b) => size(b) - size(a));
  for (const o of fresh) o.g.visible = false;
  const step = ms / Math.max(1, fresh.length);
  for (const o of fresh){
    const z = o.g.position.z, s = o.g.scale.clone();
    o.g.visible = true;
    const t0 = performance.now(), dur = 380;
    (function fall(){
      const k = Math.min(1, (performance.now() - t0) / dur), e = 1 - Math.pow(1 - k, 3);
      o.g.position.z = z + (1 - e) * 60;
      o.g.scale.set(s.x * (0.6 + 0.4 * e), s.y * (0.6 + 0.4 * e), s.z * (0.6 + 0.4 * e));
      if (k < 1) requestAnimationFrame(fall); else { o.g.position.z = z; o.g.scale.copy(s); }
    })();
    await demoSleep(step);
  }
  return fresh.length;
}
// glide the 3D camera to a spot over ms
async function demoFly(to, ms){
  const from = {x: V3.pos.x, y: V3.pos.y, z: V3.pos.z, yaw: V3.yaw, pitch: V3.pitch};
  const t0 = performance.now();
  while (true){
    const k = Math.min(1, (performance.now() - t0) / ms), e = k < .5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
    V3.pos.set(from.x + (to.x - from.x) * e, from.y + (to.y - from.y) * e, from.z + (to.z - from.z) * e);
    V3.yaw = from.yaw + (to.yaw - from.yaw) * e; V3.pitch = from.pitch + (to.pitch - from.pitch) * e;
    if (k >= 1) break;
    await demoSleep(16);
  }
}

async function demoFurnish(opts = {}){
  DEMO.on = true;
  demoSetup();
  const name = opts.name || "Balmora, Ilvi's House";
  // 0. title
  const title = demoTitle('Morrowind Workshop', 'Build a house, then Auto-furnish it');
  await demoSleep(3200); title.style.opacity = 0; await demoSleep(800); title.remove();
  // 1. Create → Build from pieces
  showView('browse'); await demoSleep(600);
  demoCaption('Create → Build from pieces', 'Lay out rooms; the Workshop builds them from the game\'s own wall and floor pieces');
  await demoClick('nav [data-view="createv"]');
  await demoWaitFor(() => $('[data-ck="build"]'));
  await demoClick('[data-ck="build"]');
  await demoWaitFor(() => $('#cr-name') && $('#cr-bstyle option[value]'));
  await demoType('#cr-name', name);
  await demoMoveTo('#cr-bstyle'); await demoSleep(700);
  // 2. rooms: the main room, a bedroom and a kitchen
  demoCaption('Three rooms: a main room, a bedroom and a kitchen', 'Names tell Auto-furnish what each room is for');
  CR.plan = plDefault(); CR.plan.rooms[0].w = 4; PL.sel = CR.plan.rooms[0].id; plChanged(); plFit(); plRender();
  await demoSleep(600);
  for (const name of ['Bedroom', 'Kitchen']){
    await demoClick('#pl-add'); await demoSleep(400);
    await demoClick(`[data-add="${name}"]`); await demoSleep(700);
    PL.sel = CR.plan.rooms[0].id;              // (the next one goes beside the main room too)
  }
  plFit(); plRender(); PL.sel = null; plSide(); plRender();
  await demoMoveTo('#pl-stage'); await demoSleep(1500);
  const furnishToo = $('#cr-bfurnish'); if (furnishToo && furnishToo.checked) await demoClick(furnishToo);   // (that's the next step)
  // 3. build it
  demoCaption('Build it', 'Floors, walls, ceilings, doorways, lanterns and a door out');
  const before3d = Date.now();
  await demoClick('#cr-go');
  await demoWaitFor(() => W.key === name.toLowerCase() && W.cells[W.key], 60000);
  demoCaption('');
  await demoSleep(1800);
  // 4. into 3D, standing in the main room
  demoCaption('The new house in 3D', 'Empty, the way it was built');
  await demoClick('[data-view3d="1"]');
  await demoWaitFor(() => V3.on && V3.objs.size > 5, 30000);
  V3.lightMode = 'bright'; v3ApplyLighting(); v3Tools();
  V3.view.cells = V3.view.grid = V3.view.wire = false; v3ApplyView();
  // the camera stays inside the main room (the rooms' outlines come from Auto-furnish's own room finder)
  const rooms = (await api('/api/furnish/rooms?key=' + encodeURIComponent(W.key))).rooms;
  const m = rooms[0], o = V3.origin, eye = m.floor + 160 - o[2];
  const hx = (Math.min(...rooms.map(r => r.x_min)) + Math.max(...rooms.map(r => r.x_max))) / 2;
  const hy = (Math.min(...rooms.map(r => r.y_min)) + Math.max(...rooms.map(r => r.y_max))) / 2;
  const at = (x, y, z, lookX, lookY, pitch) => ({x: x - o[0], y: y - o[1], z, yaw: Math.atan2(lookX - x, lookY - y), pitch});
  const mw = m.x_max - m.x_min, mh = m.y_max - m.y_min;
  const corner = at(m.x_min + mw * 0.28, m.y_min + mh * 0.2, eye + 20, hx, hy, -0.3);   // (clear of the walls' supports)
  V3.pos.set(corner.x, corner.y, corner.z); V3.yaw = corner.yaw; V3.pitch = corner.pitch;
  await demoSleep(3000);
  // 5. Auto-furnish
  demoCaption('Auto-furnish', 'It looks at how similar places in your game are furnished');
  await demoClick('#w-furnish');
  await demoWaitFor(() => $('#fu-go'));
  await demoSleep(900);
  await demoMoveTo('.modal [data-fr]'); await demoSleep(1200);
  await demoMoveTo('#fu-walls'); await demoSleep(900);
  const before = new Map(V3.objs);
  demoCaption('Furnishing…', 'Beds and shelves against the walls, a table with chairs, things on the tables, tapestries on the walls');
  await demoClick('#fu-go');
  const n = await demoReveal(before, 9000);
  demoCaption(`${n} things placed in 3 rooms`, 'All in one change: one Undo takes it back');
  await demoSleep(2500);
  // 6. a look around
  demoCaption('');
  // look at what was placed in the main room: glide across, facing the middle of the new furniture
  const inMain = W.cells[W.key].refs.filter(r => !r.arch && r.p[0] > m.x_min && r.p[0] < m.x_max && r.p[1] > m.y_min && r.p[1] < m.y_max);
  const fx = inMain.length ? inMain.reduce((s, r) => s + r.p[0], 0) / inMain.length : (m.x_min + m.x_max) / 2;
  const fy = inMain.length ? inMain.reduce((s, r) => s + r.p[1], 0) / inMain.length : (m.y_min + m.y_max) / 2;
  const across = at(m.x_max - mw * 0.25, m.y_min + mh * 0.25, eye + 30, fx, fy, -0.36);
  const back = at(m.x_min + mw * 0.5, m.y_max - mh * 0.22, eye + 30, fx, fy, -0.36);
  await demoFly(across, 7000);
  await demoFly(back, 7000);
  await demoFly(Object.assign({}, back, {yaw: back.yaw + Math.PI * 0.6}), 6000);          // and a look round
  demoCaption('Try it in the game straight away', '▶ OpenMW → Start the game, or Play here: the live link shows changes as you make them');
  await demoSleep(3500);
  demoCaption('');
  const end = demoTitle('Morrowind Workshop', 'For OpenMW · free on Nexus Mods');
  await demoSleep(4000);
  DEMO.done = true;
  document.title = 'Morrowind Workshop demo finished';     // (a recorder watching the window knows to stop)
  return {placed: n, seconds: Math.round((Date.now() - before3d) / 1000)};
}

// ---------- Screenshots: #demo=shot&s=<scene> sets up one scene and captions it ----------
// (the rest of the link opens the place first, e.g. #cell=...&3d=1&demo=shot&s=edit3d)
const DEMO_SHOTS = {
  async edit3d(){
    V3.view.grid = true; V3.view.cells = V3.view.wire = false; v3ApplyView();
    await demoSleep(12000);
    // select something near the middle of the view: the handles show how it's moved
    // (something not part of the buildings, in front of the camera and not too far, as big as possible)
    let best = null, bestScore = 0;
    for (const [key, ob] of V3.objs){
      if (ob.r.arch || !ob.g.visible || ['NPC_', 'CREA', 'LEVC', 'LIGH'].includes(ob.r.type)) continue;
      const b = new THREE.Box3().setFromObject(ob.g), c = b.getCenter(new THREE.Vector3()), sz = b.getSize(new THREE.Vector3());
      const d = c.distanceTo(V3.camera.position), p = c.clone().project(V3.camera);
      if (p.z > 1 || Math.abs(p.x) > 0.45 || p.y < -0.55 || p.y > 0.25 || d > 2600 || d < 400) continue;
      const score = Math.min(sz.length(), 400) / d;
      if (score > bestScore){ bestScore = score; best = [key, ob]; }
    }
    if (!best && DEMO.arg){             // or whatever is under that spot of the view (arg=0.55,0.42), buildings too
      const [fx, fy] = DEMO.arg.split(',').map(Number), c = V3.renderer.domElement.getBoundingClientRect();
      const h = v3Pick({clientX: c.left + c.width * fx, clientY: c.top + c.height * fy}, true);
      if (h && h.key && h.obj) best = [h.key, h.obj];
    }
    if (best){ selectRef(best[1].ck, best[0].slice(best[1].ck.length + 1)); v3Refresh(); }
    return ['Edit the world in 3D', 'Click to select, drag the handles to move or turn. Snap to the grid, drop things to the ground, and see it lit like the game'];
  },
  async furnished(){
    V3.view.cells = V3.view.grid = V3.view.wire = false; v3ApplyView();
    const rooms = (await api('/api/furnish/rooms?key=' + encodeURIComponent(W.key))).rooms;
    const m = rooms[0], o = V3.origin, mw = m.x_max - m.x_min, mh = m.y_max - m.y_min;
    const inMain = W.cells[W.key].refs.filter(r => !r.arch && r.p[0] > m.x_min && r.p[0] < m.x_max && r.p[1] > m.y_min && r.p[1] < m.y_max);
    const fx = inMain.reduce((s, r) => s + r.p[0], 0) / inMain.length, fy = inMain.reduce((s, r) => s + r.p[1], 0) / inMain.length;
    const x = m.x_max - mw * 0.25, y = m.y_min + mh * 0.25;
    V3.pos.set(x - o[0], y - o[1], m.floor + 190 - o[2]); V3.yaw = Math.atan2(fx - x, fy - y); V3.pitch = -0.36;
    await demoSleep(12000);
    return ['Auto-furnish', 'Build a house from pieces, then fill it in one click: furniture and decorations in the style of similar places in your game'];
  },
  async build(){
    showView('createv');
    await demoWaitFor(() => $('[data-ck="build"]')); $('[data-ck="build"]').click();
    await demoWaitFor(() => $('#cr-name') && $('#cr-bstyle option[value]'));
    const set = (el, v) => { el.value = v; el.dispatchEvent(new Event('input', {bubbles: true})); el.dispatchEvent(new Event('change', {bubbles: true})); };
    set($('#cr-name'), 'Balmora, Ilvi Manor');
    await demoWaitFor(() => $('#pl-stage'));
    const [pre, view] = String(DEMO.arg || '4').split(',');
    plPreset(+pre); PL.sel = null; await demoSleep(3500);
    if (view === '3d'){ PL.view = '3d'; PL.yaw = 0.5; PL.tilt = 0.6; }
    plFit(); plRender(); plSide();
    $('#pl-root').scrollIntoView({block: 'center'});
    await demoSleep(1000);
    return ['Plan your rooms', 'Drag rooms into place on every floor, click walls for doorways; stairs, walls and doors are built from the game\'s own pieces'];
  },
  async room(){
    // the biggest room of the place, seen from one corner across to the other
    V3.view.cells = V3.view.grid = V3.view.wire = false; v3ApplyView();
    V3.lightMode = 'bright'; v3ApplyLighting(); v3Tools();
    let rooms = [];
    try { rooms = (await api('/api/furnish/rooms?key=' + encodeURIComponent(W.key))).rooms; } catch (e){}
    const o = V3.origin;
    if (rooms.length){
      const m = rooms.slice().sort((a, b) => (b.x_max - b.x_min) * (b.y_max - b.y_min) - (a.x_max - a.x_min) * (a.y_max - a.y_min))[0];
      // from the middle of the room, a step back from its furniture, looking at it
      const cx = (m.x_min + m.x_max) / 2, cy = (m.y_min + m.y_max) / 2;
      const inside = W.cells[W.key].refs.filter(r => !r.arch && r.p[0] > m.x_min && r.p[0] < m.x_max && r.p[1] > m.y_min && r.p[1] < m.y_max);
      const fx = inside.length ? inside.reduce((s, r) => s + r.p[0], 0) / inside.length : cx + 1;
      const fy = inside.length ? inside.reduce((s, r) => s + r.p[1], 0) / inside.length : cy;
      const yaw = Math.atan2(fx - cx, fy - cy);
      V3.pos.set(cx - Math.sin(yaw) * 120 - o[0], cy - Math.cos(yaw) * 120 - o[1], m.floor + 200 - o[2]); V3.yaw = yaw; V3.pitch = -0.4;
    }
    await demoSleep(+(DEMO.arg || 9000));
    return ['', ''];
  },
  async plain(){ await demoSleep(+(DEMO.arg || 7000)); return ['', '']; },          // (no caption: for checking things)
  async map2d(){ await demoSleep(10000); return ['The whole world on one map', 'Every cell with its place names. Zoom in to see and edit each object, or follow your character while the game runs']; },
  async npc(){
    showView('chars'); await demoSleep(800); await cOpen(DEMO.arg || 'fargoth'); await demoSleep(4000);
    return ['Characters', 'Change anyone\'s looks, stats, behaviour, services and belongings, or make someone new from a role'];
  },
  async item(){
    ieShow(DEMO.arg || 'ebon_plate_cuirass_unique'); await demoSleep(5000);
    return ['Items and enchantments', 'Edit any weapon, armor or clothing, or start a new one from it. Add effects and see the enchantment cost', {left: '975px', top: '510px', width: '480px'}];
  },
  async script(){
    showView('scripts'); await demoSleep(800); await sOpen(DEMO.arg || 'CharGenDoorGuardTalker'); await demoSleep(1000);
    SC.text = SC.text.replace(/enableplayerfighting/i, 'EnablePlayerFightng').replace(/set done to 1/i, 'set dne to 1');
    $('#s-ta').value = SC.text; sPaint(); sDirty(); sCheckSoon();
    await demoSleep(2500);
    return ['Scripts, checked as you type', 'Mistakes are explained in plain words, and every command is listed with an example', {left: '1450px', top: '780px', width: '400px'}];
  },
  async dialogue(){ await demoSleep(4000); return ['Dialogue and quests', 'Every line with its conditions in plain words: who says it, when, and what it does. Add topics, greetings and quest stages']; },
  async browse(){ await demoSleep(4000); return ['Find anything', 'Search every record in your load order by name, ID, dialogue or mesh, and open it to see and change it']; },
};
async function demoShot(scene, arg){
  DEMO.on = true; DEMO.arg = arg;
  demoSetup();
  DEMO.cursor.style.display = 'none';
  DEMO.cap.classList.add('shot');
  const cap = await DEMO_SHOTS[scene]();
  demoCaption(cap[0], cap[1]);
  if (cap[2]) Object.assign(DEMO.cap.style, {bottom: 'auto', transform: 'none', maxWidth: 'none', textAlign: 'left'}, cap[2]);
  await demoSleep(1200);
  document.title = 'Morrowind Workshop​';      // (the screenshot tool waits for this; the mark doesn't show)
}
