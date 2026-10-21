// ---------- 3D world view ----------
// Shows a place the way it looks in game (ground, textures, buildings, objects) and lets
// you select, move, turn and snap things together, or drop new ones in from the sidebar.
// Uses the same data and actions as the flat map (W, refAction, ...), so undo, the live
// link and the sidebar all keep working.
const V3 = {on: false, ready: null, scene: null, objs: new Map(), models: {}, asked: new Set(), lands: {},
            mats: {}, origin: [0, 0, 0], yaw: 0, pitch: -0.4, pos: null, keys: {}, mode: 'translate',
            grid: 0, angle: 15, pieces: true, tilt: false, queued: false, homeFor: null,
            rest: (() => { try { return localStorage.getItem('ws-rest') === '1'; } catch (e){ return false; } })()};

// what the 3D view shows (the View menu), remembered between sessions
V3.view = {grid: false, cells: true, wire: false, ground: true, water: true};
try { Object.assign(V3.view, JSON.parse(localStorage.getItem('ws-v3view') || '{}')); } catch (e) {}

function v3Script(){
  if (!V3.ready) V3.ready = ensureThree().then(() =>
    loadScript('/web/vendor/TransformControls.js'));
  return V3.ready;
}

// Textures load a few at a time. A freshly furnished room asks for several hundred at once, and the
// browser dropped some of that burst (the thing then stood pure white); the queue keeps every request
// alive, and the same file asked for twice is fetched once.
const TEX_Q = {active: 0, max: 8, waiting: [], pending: {}};
function v3TexNext(){
  while (TEX_Q.active < TEX_Q.max && TEX_Q.waiting.length){ const job = TEX_Q.waiting.shift(); TEX_Q.active++; job(); }
}
function v3Tex(path, cb, fail){
  const T = THREE, url = '/api/file?path=' + encodeURIComponent(path);
  if (texCache[url]){ cb(texCache[url]); return; }
  if (TEX_Q.pending[url]){ TEX_Q.pending[url].push([cb, fail]); return; }
  TEX_Q.pending[url] = [[cb, fail]];
  const settle = (ok, tex) => { const list = TEX_Q.pending[url] || []; delete TEX_Q.pending[url]; TEX_Q.active--; v3TexNext();
                                for (const [c, f] of list){ if (ok) c(tex); else if (f) f(); } };
  const loader = path.endsWith('.dds') ? new T.DDSLoader() : path.endsWith('.tga') ? new T.TGALoader() : new T.TextureLoader();
  const attempt = (again) => loader.load(url, tex => {
    if (!path.endsWith('.dds')) tex.flipY = false;
    else {
      // Morrowind's DDS files often stop their mip chain early; WebGL then draws them black
      const full = Math.floor(Math.log2(Math.max(tex.image.width || 1, tex.image.height || 1))) + 1;
      if (!tex.mipmaps || tex.mipmaps.length < full){ tex.minFilter = T.LinearFilter; tex.generateMipmaps = false; if (tex.mipmaps) tex.mipmaps = tex.mipmaps.slice(0, 1); }
    }
    tex.wrapS = tex.wrapT = T.RepeatWrapping;
    texCache[url] = tex; settle(true, tex);
  }, undefined, () => {
    // (a request lost all the same: once more, a moment later)
    if (again) setTimeout(() => attempt(false), 1500); else settle(false);
  });
  TEX_Q.waiting.push(() => attempt(true));
  v3TexNext();
}

function v3Material(tex, alpha, double){
  const k = (tex || '') + '|' + (alpha ? 1 : 0) + (double ? 'd' : '');
  if (!V3.mats[k]){
    // one-sided like in the Construction Set and the game: you can look into a room through its walls
    // and ceiling. Models marked to draw both sides (and see-through ones) keep both.
    // (plain stone colour until its texture is here: a thing waiting for its texture, or whose texture
    // never came, used to glow pure white in a freshly furnished room)
    const m = new THREE.MeshLambertMaterial({color: 0xcfc6b5, side: alpha || double ? THREE.DoubleSide : THREE.FrontSide, alphaTest: alpha ? 0.5 : 0,
                                             wireframe: !!V3.view.wire});
    if (tex){
      m.userData.loading = true;
      v3Tex(tex, t => { m.map = t; m.color.setHex(0xffffff); m.needsUpdate = true; m.userData.loading = false; }, () => { m.userData.loading = false; });
    }
    V3.mats[k] = m;
  }
  return V3.mats[k];
}

// ----- setting up -----
async function v3Enable(on){
  V3.on = on;
  $('#v3wrap').style.display = on ? 'block' : 'none';
  $('#map').style.display = on ? 'none' : 'block';
  document.querySelectorAll('#mapnav, .mapzoom').forEach(e => e.style.display = on ? 'none' : '');
  $('#v3tools').style.display = on ? 'flex' : 'none';
  if (typeof tbApply === 'function') tbApply();          // (where you put the buttons, now they can be measured)
  document.querySelectorAll('[data-view3d]').forEach(b => b.classList.toggle('on', (b.dataset.view3d === '1') === on));
  try { localStorage.setItem('ws-3d', on ? '1' : '0'); } catch (e) {}
  if (!on){ v3GhostSet(null); if (W.mode === 'place') setMode('place', {id: W.placeId, name: W.placeName}); drawMap(); if (W.ext && W.key) recentre(); return; }
  setBanner('<span class="spin"></span>Loading the 3D view…');
  try { await v3Script(); }
  catch (e){ setBanner(''); toast('The 3D view could not load its files (web/vendor). Reinstalling the Workshop should fix it.', true); v3Enable(false); return; }
  setBanner('');
  if (!V3.scene) v3Init();
  v3Resize();
  if (W.key && V3.homeFor !== W.key) v3Reset();
  if (W.ext && W.key) recentre();            // (the cells the 3D camera needs, whatever the 2D zoom was)
  v3Refresh();
  v3Loop();
  if (W.mode === 'place') setMode('place', {id: W.placeId, name: W.placeName, type: W.placeType});
}

function v3Init(){
  const T = THREE, box = $('#v3wrap');
  const r = new T.WebGLRenderer({antialias: true});
  r.setPixelRatio(window.devicePixelRatio || 1);
  box.appendChild(r.domElement);
  r.domElement.tabIndex = 0;
  V3.renderer = r;
  V3.scene = new T.Scene();
  try { V3.fov = +localStorage.getItem('ws-fov') || V3.fov; } catch (e) {}
  V3.camera = new T.PerspectiveCamera(V3.fov || 60, 1, 4, 40000);
  V3.camera.up.set(0, 0, 1);
  V3.root = new T.Group(); V3.scene.add(V3.root);
  V3.ground = new T.Group(); V3.scene.add(V3.ground);
  V3.hemi = new T.HemisphereLight(0xfff4e0, 0x50453a, 0.8); V3.hemi.position.set(0, 0, 1); V3.scene.add(V3.hemi);
  V3.sun = new T.DirectionalLight(0xfff0d8, 0.75); V3.sun.position.set(0.6, -0.8, 1.5); V3.scene.add(V3.sun);
  V3.amb = new T.AmbientLight(0xffffff, 0.2); V3.scene.add(V3.amb);
  V3.water = new T.Mesh(new T.PlaneGeometry(60000, 60000),
    new T.MeshLambertMaterial({color: 0x2c5262, transparent: true, opacity: 0.62, depthWrite: false}));
  V3.scene.add(V3.water);
  V3.marker = new T.Mesh(new T.ConeGeometry(30, 90, 12), new T.MeshLambertMaterial({color: 0xff6b4a, emissive: 0x401008}));
  V3.marker.geometry.rotateX(-Math.PI / 2); V3.marker.visible = false; V3.scene.add(V3.marker);
  V3.ray = new T.Raycaster();
  // move / turn handles
  const tc = new T.TransformControls(V3.camera, r.domElement);
  tc.setSpace('world'); tc.size = 0.9;
  tc.addEventListener('dragging-changed', e => e.value ? v3DragStart() : v3DragEnd());
  tc.addEventListener('objectChange', v3Snap);
  V3.scene.add(tc); V3.tc = tc;
  V3.selBox = new T.BoxHelper(undefined, 0xf0cd87); V3.selBox.visible = false; V3.scene.add(V3.selBox);
  v3Bind(r.domElement);
  v3Tools();
}

function v3Resize(){
  if (!V3.renderer) return;
  const b = $('#v3wrap').getBoundingClientRect();
  V3.renderer.setSize(Math.max(1, b.width), Math.max(1, b.height));
  V3.camera.aspect = Math.max(1, b.width) / Math.max(1, b.height); V3.camera.updateProjectionMatrix();
}
window.addEventListener('resize', () => { if (V3.on) v3Resize(); });

// A fresh place: start the camera over it and forget the old objects
function v3Reset(){
  const T = THREE, i = W.info;
  if (!i) return;
  V3.homeFor = W.key;
  V3.grassFor = null; v3GrassDrop();               // (positions are kept from a new origin)
  for (const o of V3.objs.values()) V3.root.remove(o.g);
  V3.objs.clear();
  for (const k of Object.keys(V3.lands)){ if (V3.lands[k].mesh) V3.ground.remove(V3.lands[k].mesh); }
  V3.lands = {};
  if (W.ext){
    V3.origin = [(i.gx + 0.5) * CELL, (i.gy + 0.5) * CELL, 0];
    V3.scene.background = new T.Color(0x9fb5c6);
    V3.scene.fog = new T.Fog(0x9fb5c6, 6000, 26000);
    V3.hemi.intensity = 0.8; V3.sun.intensity = 0.75; V3.amb.intensity = 0.15;
  } else {
    V3.origin = [W.cam.x, W.cam.y, 0];
    V3.scene.background = new T.Color(0x0d0c0a);
    V3.scene.fog = null;
    V3.hemi.intensity = 0.75; V3.sun.intensity = 0.35; V3.amb.intensity = 0.45;
  }
  V3.water.visible = W.ext && V3.view.water !== false;
  v3Home();
  v3Tools(); v3LandPanel(); v3ApplyView();
}

function v3Home(){
  const refs = visibleRefs().map(x => x[1]);
  let x = V3.origin[0], y = V3.origin[1], z;
  if (W.ext){
    x = W.cam.x; y = W.cam.y;
    z = (terrainAt(x, y) || 0) + 1400; y -= 2600; V3.pitch = -0.45;
  } else {
    // stand in the busiest part of the room at about head height, looking slightly down
    const near = refs.filter(r => !r.arch && Math.hypot(r.p[0] - W.cam.x, r.p[1] - W.cam.y) < 1500);
    const zs = (near.length ? near : refs).map(r => r.p[2]).sort((a, b) => a - b);
    const mid = zs.length ? zs[Math.floor(zs.length / 3)] : 0;
    x = W.cam.x; y = W.cam.y - 350; z = mid + 130; V3.pitch = -0.2;
  }
  V3.yaw = 0;
  V3.pos = new THREE.Vector3(x - V3.origin[0], y - V3.origin[1], z - V3.origin[2]);
}

// ----- keeping the scene in step with the Workshop's data -----
function v3Refresh(){
  if (!V3.on || !V3.scene || V3.queued) return;
  V3.queued = true;
  requestAnimationFrame(() => { V3.queued = false; v3Sync(); });
}

function v3Sync(){
  if (!W.key) return;
  // a new place was opened (flying into the next cell outdoors keeps the view)
  if (!V3.homeFor || (!W.ext && V3.homeFor !== W.key) || W.ext !== V3.homeFor.startsWith('#')) v3Reset();
  V3.homeFor = W.key;
  const want = new Map();
  for (const [ck, r] of visibleRefs()) want.set(ck + '|' + r.k, [ck, r]);
  for (const [key, o] of V3.objs) if (!want.has(key)){ V3.root.remove(o.g); V3.objs.delete(key); }
  const need = [];
  for (const [key, [ck, r]] of want){
    const id = r.id.toLowerCase();
    if (!(id in V3.models) && !V3.asked.has(id) && r.type !== 'LEVC') need.push(r.id);      // (people too: their bodies)
    const look = id + '|' + (id in V3.models ? 1 : 0);
    let o = V3.objs.get(key);
    if (!o || o.look !== look){
      if (o) V3.root.remove(o.g);
      o = {g: v3Build(r), look, ck, k: r.k};
      o.g.userData.ref = key;
      V3.root.add(o.g); V3.objs.set(key, o);
    }
    o.ck = ck; o.r = r;
    if (!(V3.drag && V3.drag.key === key)) v3Place(o.g, r);
  }
  if (need.length) v3Fetch(need);
  if (W.ext) v3Terrain();
  v3Paths();
  v3ApplyLighting();
  // the selected object gets the handles; several selected: one set of handles in their middle
  for (const bh of V3.multiBoxes || []) V3.scene.remove(bh);
  V3.multiBoxes = [];
  const members = W.multi && W.multi.size > 1 ? [...W.multi.values()].map(m => V3.objs.get(m.cell + '|' + m.k)).filter(Boolean) : [];
  if (members.length > 1){
    if (!V3.pivot){ V3.pivot = new THREE.Object3D(); V3.scene.add(V3.pivot); }
    if (!(V3.drag && V3.drag.group)){
      const box = new THREE.Box3();
      members.forEach(o => box.expandByObject(o.g));
      const c = box.getCenter(new THREE.Vector3());
      V3.pivot.position.set(c.x, c.y, box.min.z); V3.pivot.rotation.set(0, 0, 0); V3.pivot.updateMatrixWorld();
    }
    if (V3.tc.object !== V3.pivot) V3.tc.attach(V3.pivot);
    for (const o of members){ const bh = new THREE.BoxHelper(o.g, 0xf0cd87); V3.scene.add(bh); V3.multiBoxes.push(bh); }
    V3.selBox.visible = false;
  } else {
    const sk = W.sel ? W.sel.cell + '|' + W.sel.k : null, so = sk && V3.objs.get(sk);
    if (so && !(V3.landOpen && W.ext)){ if (V3.tc.object !== so.g) V3.tc.attach(so.g); V3.selBox.setFromObject(so.g); V3.selBox.visible = true; }
    else { V3.tc.detach(); V3.selBox.visible = false; }
  }
  v3ApplyMode();
}

// ----- lighting: the place's own ambient/sunlight/fog, and real lights from lamps, candles and torches
// V3.lightMode: 'game' (as in game) or 'bright' (even light for editing). V3.lightPreview: unsaved settings being tried.
const V3_LIGHT_POOL = 12;
function v3LightMode(){ if (!V3.lightMode){ try { V3.lightMode = localStorage.getItem('ws-light') || 'game'; } catch (e){ V3.lightMode = 'game'; } } return V3.lightMode; }
function v3ApplyLighting(){
  if (!V3.scene) return;
  const T = THREE, L = V3.lightPreview || (W.info && W.info.lighting);
  const game = v3LightMode() === 'game';
  if (!W.ext && V3.fall){ V3.scene.remove(V3.fall); V3.fall = null; }      // no rain indoors
  if (W.ext || !L || !game){
    // outdoors, or bright editing light: what the view always used
    if (!W.ext){ V3.scene.background = new T.Color(0x0d0c0a); V3.scene.fog = null; V3.hemi.intensity = 0.75; V3.sun.intensity = 0.35; V3.amb.intensity = 0.45;
      V3.amb.color.set(0xffffff); V3.sun.color.set(0xfff0d8); V3.hemi.color.set(0xfff4e0); }
    v3PointLights(W.ext && game ? 0.6 : 0);
    if (W.ext) v3ApplyWeather();
    return;
  }
  const c = a => new T.Color(a[0] / 255, a[1] / 255, a[2] / 255);
  V3.amb.color.copy(c(L.ambient)); V3.amb.intensity = 1.15;
  V3.sun.color.copy(c(L.sun)); V3.sun.intensity = 0.55;
  V3.hemi.color.copy(c(L.sun)); V3.hemi.groundColor.copy(c(L.ambient)); V3.hemi.intensity = 0.12;
  const far = 700 + (1 - Math.min(1, Math.max(0, L.density))) * 9000;
  V3.scene.fog = new T.Fog(c(L.fog), far * 0.15, far);
  V3.scene.background = c(L.fog);
  v3PointLights(1);
}
// ----- a preview of the weather outdoors: sky and fog colour, light, and rain, snow or ash falling
// (index into Clear, Cloudy, Foggy, Overcast, Rain, Thunderstorm, Ash storm, Blight, Snow, Blizzard)
const V3_WEATHER = [
  {sky: 0x9fb5c6, fog: [6000, 26000], sun: 0.75, hemi: 0.8},
  {sky: 0x93a2ae, fog: [5000, 22000], sun: 0.5, hemi: 0.75},
  {sky: 0xa8aca8, fog: [300, 3200], sun: 0.3, hemi: 0.7},
  {sky: 0x7d858c, fog: [3500, 16000], sun: 0.3, hemi: 0.65},
  {sky: 0x5f6870, fog: [2000, 11000], sun: 0.2, hemi: 0.55, fall: 'rain'},
  {sky: 0x3c434c, fog: [1500, 9000], sun: 0.12, hemi: 0.45, fall: 'rain', flash: true},
  {sky: 0x8a5a3c, fog: [400, 4500], sun: 0.25, hemi: 0.6, fall: 'ash', tint: 0xffc8a0},
  {sky: 0x8a4a48, fog: [400, 4000], sun: 0.2, hemi: 0.55, fall: 'blight', tint: 0xffa8a0},
  {sky: 0xc8d2dc, fog: [1500, 9000], sun: 0.45, hemi: 0.85, fall: 'snow'},
  {sky: 0xd8e0e8, fog: [250, 2200], sun: 0.3, hemi: 0.9, fall: 'blizzard'},
];
function v3ApplyWeather(){
  if (!V3.scene || !W.ext) return;
  const T = THREE, w = V3_WEATHER[V3.weather == null ? 0 : V3.weather];
  V3.scene.background = new T.Color(w.sky);
  // (the fog moves out with the View distance, so the far cells fade in rather than stop at an edge;
  // on Near it is as it always was)
  const k = v3Dist() === 1 ? 1 : (v3Dist() + 0.6) / 1.6;
  V3.scene.fog = new T.Fog(w.sky, w.fog[0] * k, w.fog[1] * k);
  const far = Math.max(40000, w.fog[1] * k * 1.1);
  if (V3.camera.far !== far){ V3.camera.far = far; V3.camera.updateProjectionMatrix(); }
  V3.sun.intensity = w.sun; V3.hemi.intensity = w.hemi;
  V3.sun.color.set(w.tint || 0xfff0d8); V3.hemi.color.set(w.tint || 0xfff4e0);
  // falling things: one set of points that follows the camera
  if (V3.fall){ V3.scene.remove(V3.fall); V3.fall.geometry.dispose(); V3.fall.material.dispose(); V3.fall = null; }
  if (!w.fall) return;
  const kind = w.fall, n = kind === 'blizzard' ? 9000 : kind === 'rain' ? 6000 : 4000, B = 2400;
  const pos = new Float32Array(n * 3);
  for (let i = 0; i < n; i++){ pos[i * 3] = (Math.random() - 0.5) * B * 2; pos[i * 3 + 1] = (Math.random() - 0.5) * B * 2; pos[i * 3 + 2] = (Math.random() - 0.3) * B; }
  const geo = new T.BufferGeometry(); geo.setAttribute('position', new T.BufferAttribute(pos, 3));
  const col = {rain: 0x9ab0c8, snow: 0xffffff, blizzard: 0xffffff, ash: 0x6a5040, blight: 0x9a4a40}[kind];
  if (!V3.dotTex){
    // a soft round dot, so flakes and ash aren't little squares
    const c = document.createElement('canvas'); c.width = c.height = 32;
    const x = c.getContext('2d'), gr = x.createRadialGradient(16, 16, 0, 16, 16, 16);
    gr.addColorStop(0, 'rgba(255,255,255,1)'); gr.addColorStop(0.5, 'rgba(255,255,255,0.7)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
    x.fillStyle = gr; x.fillRect(0, 0, 32, 32);
    V3.dotTex = new T.CanvasTexture(c);
  }
  const mat = new T.PointsMaterial({color: col, size: kind === 'rain' ? 5 : kind === 'ash' || kind === 'blight' ? 9 : 10, transparent: true,
    map: V3.dotTex, opacity: kind === 'rain' ? 0.6 : 0.9, depthWrite: false, fog: true});
  V3.fall = new T.Points(geo, mat); V3.fall.frustumCulled = false; V3.fall.userData = {kind, B};
  V3.scene.add(V3.fall);
}
function v3WeatherTick(dt, t){
  const F = V3.fall; if (!F || !V3.pos) return;
  const {kind, B} = F.userData, p = F.geometry.attributes.position.array;
  const down = {rain: 2200, snow: 160, blizzard: 420, ash: 260, blight: 230}[kind] * dt;
  const side = {rain: 60, snow: 40, blizzard: 900, ash: 700, blight: 500}[kind] * dt;
  const sway = Math.sin(t / 900);
  for (let i = 0; i < p.length; i += 3){
    p[i + 2] -= down; p[i] += side * (0.6 + 0.4 * sway); p[i + 1] += side * 0.3;
    if (p[i + 2] < -B * 0.3) p[i + 2] += B;
    if (p[i] > B) p[i] -= B * 2; if (p[i] < -B) p[i] += B * 2;
    if (p[i + 1] > B) p[i + 1] -= B * 2;
  }
  F.geometry.attributes.position.needsUpdate = true;
  F.position.copy(V3.pos);
  // thunder: now and then the sky lights up
  const w = V3_WEATHER[V3.weather];
  if (w && w.flash){
    if (!V3.flashT || t > V3.flashT){ V3.flashT = t + 4000 + Math.random() * 9000; V3.flashOn = t; }
    const f = V3.flashOn && t - V3.flashOn < 180 ? 1 : 0;
    V3.hemi.intensity = w.hemi + f * 1.2;
  }
}
// up to 12 nearby lights as real point lights (a fixed set, so materials never need rebuilding)
function v3PointLights(strength){
  const T = THREE;
  if (!V3.pool){
    V3.pool = [];
    for (let n = 0; n < V3_LIGHT_POOL; n++){ const l = new T.PointLight(0xffffff, 0, 300, 1.2); V3.scene.add(l); V3.pool.push(l); }
  }
  V3.poolStrength = strength;
  v3PointLightsPick();
}
function v3PointLightsPick(){
  if (!V3.pool) return;
  const cam = V3.pos, list = [];
  if (V3.poolStrength > 0){
    for (const o of V3.objs.values()){
      const L = o.r && o.r.light; if (!L) continue;
      if (L[4] & 0x4 || L[4] & 0x20) continue;           // "negative" lights and lights that start off
      const d = o.g.position.distanceTo(cam); if (d > 6000) continue;
      list.push([d, o, L]);
    }
    list.sort((a, b) => a[0] - b[0]);
  }
  V3.pool.forEach((l, n) => {
    const it = list[n];
    if (!it){ l.intensity = 0; l.userData.src = null; return; }
    const [, o, L] = it;
    l.color.setRGB(L[0] / 255, L[1] / 255, L[2] / 255);
    l.distance = Math.max(64, L[3]) * 1.6;
    l.position.copy(o.g.position); l.position.z += 8;
    l.userData = {src: o, flags: L[4], base: 1.6 * V3.poolStrength, seed: n * 7.3};
    l.intensity = l.userData.base;
  });
}
// flicker and pulse, like in game (called every frame)
function v3LightsTick(t){
  if (!V3.pool || !V3.poolStrength) return;
  for (const l of V3.pool){
    const u = l.userData; if (!u || !u.src) continue;
    const s = t / 1000 + u.seed;
    let k = 1;
    if (u.flags & 0x8) k = 0.82 + 0.18 * (Math.sin(s * 13) * 0.5 + Math.sin(s * 7.7) * 0.5);
    else if (u.flags & 0x40) k = 0.88 + 0.12 * Math.sin(s * 4.1);
    else if (u.flags & 0x80) k = 0.6 + 0.4 * Math.sin(s * 3);
    else if (u.flags & 0x100) k = 0.7 + 0.3 * Math.sin(s * 1.2);
    l.intensity = u.base * k;
  }
}

// walking paths as glowing lines just above the floor (View tab: "Show them on the map")
function v3Paths(){
  const P = !(typeof PE !== 'undefined' && PE) && W.showPaths && !W.ext && W.info && W.info.paths;   // (while editing: pathedit.js draws them)
  // (redrawn whenever they're new data, not only when the count changes: moved points too)
  const sig = P ? W.key + '|' + V3.origin.join(',') : '';
  if (sig === V3.pathSig && P === V3.pathSrc) return;
  V3.pathSig = sig; V3.pathSrc = P;
  if (V3.pathObj){ V3.scene.remove(V3.pathObj); V3.pathObj.geometry.dispose(); V3.pathObj = null; }
  if (!P) return;
  const o = V3.origin, pos = [];
  for (const [a, b] of P.edges){
    const A = P.pts[a], B = P.pts[b];
    pos.push(A[0] - o[0], A[1] - o[1], A[2] - o[2] + 8, B[0] - o[0], B[1] - o[1], B[2] - o[2] + 8);
  }
  const geo = new THREE.BufferGeometry(); geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  V3.pathObj = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({color: 0x7fd0ff, depthTest: false, transparent: true, opacity: 0.9}));
  V3.pathObj.renderOrder = 10;
  V3.scene.add(V3.pathObj);
}

function v3Place(g, r){
  const p = r.p, o = V3.origin;
  g.position.set(p[0] - o[0], p[1] - o[1], p[2] - o[2]);
  // the game turns things clockwise, about Z first, then Y, then X (OpenMW's makeOsgQuat): Three's 'XYZ'
  g.rotation.set(-p[3], -p[4], -p[5], 'XYZ');
  g.scale.setScalar(r.s || 1);
  g.updateMatrixWorld(true);
}

const V3_COLORS = {NPC_: 0x7fb0e0, CREA: 0xd08a5a, LEVC: 0xd08a5a, LIGH: 0xffd27a, DOOR: 0xb08bd6};
function v3Build(r){
  const T = THREE, g = new T.Group(), m = V3.models[r.id.toLowerCase()];
  if (m && m.parts.length){
    for (const pt of m.parts) g.add(new T.Mesh(pt.geo, pt.mat));
    return g;
  }
  const col = V3_COLORS[r.type] || 0xb0a090;
  if (r.type === 'NPC_' || r.type === 'CREA' || r.type === 'LEVC'){
    // people have no single model: a stand-in figure of the right size
    if (!V3.figure){ V3.figure = new T.CylinderGeometry(26, 26, 128, 14); V3.figure.rotateX(Math.PI / 2); V3.figure.translate(0, 0, 64); }
    g.add(new T.Mesh(V3.figure, new T.MeshLambertMaterial({color: col})));
    const nose = new T.Mesh(new T.BoxGeometry(10, 22, 10), new T.MeshLambertMaterial({color: 0x222222}));
    nose.position.set(0, 30, 110); g.add(nose);
  } else if (r.b && m !== undefined){
    const b = r.b, geo = new T.BoxGeometry(Math.max(4, b[3] - b[0]), Math.max(4, b[4] - b[1]), Math.max(4, b[5] - b[2]));
    geo.translate((b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2);
    g.add(new T.Mesh(geo, new T.MeshLambertMaterial({color: col, transparent: true, opacity: 0.45})));
  } else if (m !== undefined){
    // (a sound source from the Library: a teal ball, so it's told apart from a light)
    const snd = r.type === 'LIGH' && /^sound_/i.test(r.id);
    g.add(new T.Mesh(new T.SphereGeometry(snd ? 14 : 10, 10, 8), new T.MeshLambertMaterial({color: snd ? 0x4fd1c5 : col,
      emissive: snd ? 0x0f4a44 : r.type === 'LIGH' ? 0x664411 : 0})));
  }
  return g;
}

V3.inflight = {};
function v3Fetch(ids){
  ids = [...new Set(ids)];
  ids.forEach(i => V3.asked.add(i.toLowerCase()));
  const jobs = [];
  for (let n = 0; n < ids.length; n += 60){
    const part = ids.slice(n, n + 60);
    const job = (async () => {
      let res;
      try { res = await post('/api/models', {ids: part}); } catch (e){ part.forEach(i => V3.asked.delete(i.toLowerCase())); return; }
      const T = THREE;
      for (const id of part){
        const shapes = res[id], parts = [];
        for (const s of shapes || []){
          const geo = new T.BufferGeometry();
          geo.setAttribute('position', new T.Float32BufferAttribute(s.p, 3));
          if (s.uv && s.uv.length) geo.setAttribute('uv', new T.Float32BufferAttribute(s.uv, 2));
          geo.setIndex(s.i); geo.computeVertexNormals(); geo.computeBoundingBox(); geo.computeBoundingSphere();
          parts.push({geo, mat: v3Material(s.tex, s.alpha, s.double)});
        }
        V3.models[id.toLowerCase()] = {parts};
      }
      v3Refresh();
    })();
    part.forEach(i => V3.inflight[i.toLowerCase()] = job);
    jobs.push(job);
  }
  return Promise.all(jobs);
}

// Models for these ids, fetched if needed
async function v3EnsureModels(ids){
  await v3Script();
  const missing = ids.filter(i => !(i.toLowerCase() in V3.models) && !V3.asked.has(i.toLowerCase()));
  if (missing.length) await v3Fetch(missing);
  await Promise.all(ids.map(i => V3.inflight[i.toLowerCase()]).filter(Boolean));
}

// ----- small pictures of objects (sidebar tiles, search results, hover preview) -----
// Drawn from the real 3D models on one hidden canvas, then kept as images.
const THUMB = {cache: {}, waiting: {}, queue: [], busy: false};
function v3ThumbScan(root){
  (root || document).querySelectorAll('img[data-tid]:not([data-done])').forEach(img => {
    const id = img.dataset.tid, size = +(img.dataset.ts || 96), k = id.toLowerCase() + '|' + size + (img.dataset.tview ? '|' + img.dataset.tview : '');
    img.dataset.done = '1';
    if (THUMB.cache[k]){ img.src = THUMB.cache[k]; return; }
    if (THUMB.cache[k] === null){ img.replaceWith(v3ThumbFallback(img)); return; }
    (THUMB.waiting[k] = THUMB.waiting[k] || []).push(img);
    if (!THUMB.queue.includes(k)) THUMB.queue.push(k);
  });
  v3ThumbWork();
}
function v3ThumbFallback(img){
  const s = document.createElement('span');
  s.className = img.className + ' nothumb';
  s.textContent = ({NPC_: '👤', CREA: '🐾', LEVC: '🐾', LEVI: '🎲'})[img.dataset.tt] || '◇';
  return s;
}
async function v3ThumbWork(){
  if (THUMB.busy || !THUMB.queue.length) return;
  THUMB.busy = true;
  try {
    await v3Script();
    while (THUMB.queue.length){
      // fetch models for the next few at once
      const batch = THUMB.queue.splice(0, 12);
      await v3EnsureModels([...new Set(batch.map(k => k.split('|')[0]))]);
      for (const k of batch){
        const [id, size, view] = k.split('|');
        const url = await v3ThumbRender(id, +size, view);
        THUMB.cache[k] = url;
        for (const img of THUMB.waiting[k] || []){
          if (url) img.src = url; else if (img.isConnected) img.replaceWith(v3ThumbFallback(img));
        }
        delete THUMB.waiting[k];
      }
    }
  } finally { THUMB.busy = false; }
}
async function v3ThumbRender(id, size, view){
  const T = THREE, m = V3.models[id];
  if (!m || !m.parts.length) return null;
  v3ThumbSetup();
  // wait (briefly) for its textures
  for (let n = 0; n < 40 && m.parts.some(p => p.mat.userData.loading); n++) await new Promise(r => setTimeout(r, 50));
  const g = new T.Group();
  for (const p of m.parts) g.add(new T.Mesh(p.geo, p.mat));
  THUMB.scene.add(g);
  const box = new T.Box3().setFromObject(g), c = box.getCenter(new T.Vector3()), s = box.getSize(new T.Vector3());
  const rad = Math.max(s.x, s.y, s.z, 1) * 0.62;
  const dist = rad / Math.sin(15 * Math.PI / 180) * 1.05;
  // heads and hair: look at their face, a little from the side
  if (view === 'front') THUMB.cam.position.set(c.x + dist * 0.35, c.y - dist * 0.92, c.z + dist * 0.12);
  else THUMB.cam.position.set(c.x + dist * 0.55, c.y - dist * 0.72, c.z + dist * 0.42);
  THUMB.cam.lookAt(c);
  THUMB.r.setSize(size, size, false);
  THUMB.r.render(THUMB.scene, THUMB.cam);
  const url = THUMB.r.domElement.toDataURL('image/png');
  THUMB.scene.remove(g);
  return url;
}
function v3ThumbSetup(){
  const T = THREE;
  if (!THUMB.r){
    THUMB.r = new T.WebGLRenderer({antialias: true, alpha: true, preserveDrawingBuffer: true});
    THUMB.scene = new T.Scene();
    THUMB.scene.add(new T.HemisphereLight(0xfff4e0, 0x5a4a38, 1.25));
    THUMB.scene.add(new T.AmbientLight(0xffffff, 0.35));
    const sun = new T.DirectionalLight(0xffffff, 0.75); sun.position.set(1, -1.5, 2); THUMB.scene.add(sun);
    THUMB.cam = new T.PerspectiveCamera(30, 1, 1, 100000); THUMB.cam.up.set(0, 0, 1);
  }
}

// ----- the see-through copy that shows where a new object will go -----
function v3GhostSet(id, type){
  const G = V3.ghost;
  if (G && G.id === id) return;
  if (G){ V3.scene && V3.scene.remove(G.g); V3.ghost = null; }
  if (!id || !V3.scene) return;
  const ghost = {id, type, yaw: G ? G.yaw : 0, g: new THREE.Group(), minZ: 0, ready: false};
  ghost.g.visible = false;
  V3.ghost = ghost; V3.scene.add(ghost.g);
  v3EnsureModels([id]).then(() => {
    if (V3.ghost !== ghost) return;
    const T = THREE, m = V3.models[id.toLowerCase()];
    let src;
    if (m && m.parts.length) src = m.parts.map(p => new T.Mesh(p.geo, p.mat));
    else src = v3Build({id, type: type || 'NPC_', b: null}).children;
    for (const mesh of src){
      const mat = mesh.material.clone(); mat.transparent = true; mat.opacity = 0.55; mat.depthWrite = false;
      if (mesh.material.map) mat.map = mesh.material.map;
      ghost.g.add(new T.Mesh(mesh.geometry, mat));
    }
    const b = new T.Box3().setFromObject(ghost.g);
    ghost.minZ = b.isEmpty() ? 0 : b.min.z;
    ghost.ready = true;
  });
}
// a see-through copy of a whole group (paste, prefab), turned and placed like one object
function v3GhostGroup(items){
  if (!V3.scene) return;
  if (V3.ghost){ V3.scene.remove(V3.ghost.g); V3.ghost = null; }
  const ghost = {id: '__group', yaw: (W.groupPlace && W.groupPlace.yaw) || 0, g: new THREE.Group(), minZ: 0, ready: false};
  ghost.g.visible = false;
  V3.ghost = ghost; V3.scene.add(ghost.g);
  v3EnsureModels([...new Set(items.map(it => it.id))]).then(() => {
    if (V3.ghost !== ghost) return;
    const T = THREE;
    for (const it of items){
      const m = V3.models[it.id.toLowerCase()], part = new T.Group();
      const src = m && m.parts.length ? m.parts.map(p => new T.Mesh(p.geo, p.mat)) : v3Build({id: it.id, type: it.type || 'NPC_', b: it.b}).children;
      for (const mesh of src){
        const mat = mesh.material.clone(); mat.transparent = true; mat.opacity = 0.55; mat.depthWrite = false;
        if (mesh.material.map) mat.map = mesh.material.map;
        part.add(new T.Mesh(mesh.geometry, mat));
      }
      part.position.set(it.dx, it.dy, it.dz || 0);
      part.rotation.set(-(it.rx || 0), -(it.ry || 0), -(it.rz || 0), 'XYZ');
      part.scale.setScalar(it.s || 1);
      ghost.g.add(part);
    }
    ghost.minZ = 0;                 // a group's offsets already sit on its lowest point
    ghost.ready = true;
  });
}

function v3GhostMove(e){
  const G = V3.ghost; if (!G) return null;
  const h = v3Pick(e, true);
  if (!h || !h.world || !G.ready){ G.g.visible = false; G.hit = null; return null; }
  G.hit = h.world;
  G.g.position.set(h.point.x, h.point.y, h.point.z - G.minZ);
  G.g.rotation.set(0, 0, -G.yaw);
  G.g.visible = true;
  return h;
}

// ----- ground -----
// how far the 3D view reaches outdoors: cells each way round the camera (1: the 3 x 3 around it ... 4:
// 9 x 9), from the View menu, remembered
const V3_DISTS = ['', 'Near', 'Medium', 'Far', 'Very far'];
function v3Dist(){
  if (V3.dist == null){ let d = 1; try { d = +localStorage.getItem('ws-3d-dist') || 1; } catch (e) {} V3.dist = Math.max(1, Math.min(4, d)); }
  return V3.dist;
}
function v3SetDist(d){
  V3.dist = Math.max(1, Math.min(4, d));
  try { localStorage.setItem('ws-3d-dist', String(V3.dist)); } catch (e) {}
  v3ApplyLighting();                                     // (the fog goes with it)
  if (W.ext){ v3Terrain(); loadAround(); }
}
function v3Terrain(){
  const [cx, cy] = v3CamCell(), D = v3Dist();
  // nearest first, so the ground under the camera comes in before the far hills
  const spots = [];
  for (let dx = -D; dx <= D; dx++) for (let dy = -D; dy <= D; dy++) spots.push([dx, dy]);
  spots.sort((a, b) => Math.hypot(a[0], a[1]) - Math.hypot(b[0], b[1]));
  for (const [dx, dy] of spots){
    const gx = cx + dx, gy = cy + dy, k = gx + ',' + gy;
    if (V3.lands[k]) continue;
    V3.lands[k] = {loading: true};
    api(`/api/land?gx=${gx}&gy=${gy}&tex=1`).then(L => {
      if (!V3.lands[k]) return;
      V3.lands[k] = {loading: false, gx, gy};
      if (L.exists){
        // the ground textures by name, so painting can add new ones: slot list + one slot number per patch
        L.paths = L.tex.slice(); L.ids = L.t.map(i => L.paths[i]); L.origId = L.tid || L.t.map(() => '');
        V3.lands[k].L = L; V3.lands[k].mesh = v3LandMesh(gx, gy, L); V3.ground.add(V3.lands[k].mesh);
        v3LandNeighbours(gx, gy);                    // their edges now blend into this one
      }
    }).catch(() => { delete V3.lands[k]; });
  }
  for (const k of Object.keys(V3.lands)){
    const [x, y] = k.split(',').map(Number);
    if ((Math.abs(x - cx) > D + 1 || Math.abs(y - cy) > D + 1) && !(V3.stroke && V3.stroke.cells.has(k))) v3LandDrop(k);
  }
  if (V3.grassFor !== cx + ',' + cy) v3GrassReload();      // the mod's grass around the camera
}
function v3LandDrop(k){
  const m = V3.lands[k] && V3.lands[k].mesh;
  if (m){ V3.ground.remove(m); m.geometry.dispose(); m.material.dispose(); }
  delete V3.lands[k];
}
// forget the ground so it loads again (after undo, or after the Workshop changed it)
function v3LandsReload(){ for (const k of Object.keys(V3.lands)) v3LandDrop(k); if (V3.on && W.ext) v3Terrain(); }

// One mesh per cell (65 x 65 heights). The ground textures blend smoothly into each other
// like in game: a small map says which texture each 512-unit patch has, and the shader mixes
// the four nearest patches.
const V3_MAXTEX = 12;
function v3LandMesh(gx, gy, L){
  const T = THREE, H = L.h, col = L.c ? atob(L.c) : null, o = V3.origin;
  const pos = new Float32Array(65 * 65 * 3), clr = new Float32Array(65 * 65 * 3), uv = new Float32Array(65 * 65 * 2), idx = [];
  for (let y = 0; y <= 64; y++) for (let x = 0; x <= 64; x++){
    const v = y * 65 + x;
    pos[v * 3] = gx * CELL + x * 128 - o[0]; pos[v * 3 + 1] = gy * CELL + y * 128 - o[1]; pos[v * 3 + 2] = H[v] - o[2];
    uv[v * 2] = x / 64; uv[v * 2 + 1] = y / 64;
    for (let c = 0; c < 3; c++) clr[v * 3 + c] = col ? col.charCodeAt(v * 3 + c) / 255 : 1;
  }
  for (let y = 0; y < 64; y++) for (let x = 0; x < 64; x++){
    const a = y * 65 + x, b = a + 1, c = a + 65, d = a + 66;
    idx.push(a, b, d, a, d, c);
  }
  const geo = new T.BufferGeometry();
  geo.setAttribute('position', new T.BufferAttribute(pos, 3));
  geo.setAttribute('normal', new T.BufferAttribute(new Float32Array(65 * 65 * 3), 3));
  geo.setAttribute('uv', new T.BufferAttribute(uv, 2));
  geo.setAttribute('color', new T.BufferAttribute(clr, 3));
  geo.setIndex(idx);
  const mesh = new T.Mesh(geo, null);
  mesh.userData.ground = true; mesh.userData.gx = gx; mesh.userData.gy = gy;
  v3LandNormals(mesh, L);
  v3LandMaterial(mesh, L);
  return mesh;
}

// heights across cell borders (for smooth shading and the brushes)
function v3H(gx, gy, x, y){
  if (x < 0){ gx--; x += 64; } else if (x > 64){ gx++; x -= 64; }
  if (y < 0){ gy--; y += 64; } else if (y > 64){ gy++; y -= 64; }
  const c = V3.lands[gx + ',' + gy];
  return c && c.L ? c.L.h[y * 65 + x] : null;
}
function v3LandNormals(mesh, L){
  const n = mesh.geometry.attributes.normal, H = L.h, {gx, gy} = mesh.userData;
  const at = (x, y) => { const v = v3H(gx, gy, x, y); return v === null ? H[Math.max(0, Math.min(64, y)) * 65 + Math.max(0, Math.min(64, x))] : v; };
  for (let y = 0; y <= 64; y++) for (let x = 0; x <= 64; x++){
    const nx = -(at(x + 1, y) - at(x - 1, y)) / 256, ny = -(at(x, y + 1) - at(x, y - 1)) / 256, len = Math.hypot(nx, ny, 1);
    n.setXYZ(y * 65 + x, nx / len, ny / len, 1 / len);
  }
  n.needsUpdate = true;
}
function v3LandHeights(mesh, L){
  const p = mesh.geometry.attributes.position;
  for (let v = 0; v < 65 * 65; v++) p.setZ(v, L.h[v] - V3.origin[2]);
  p.needsUpdate = true;
  mesh.geometry.computeBoundingBox(); mesh.geometry.computeBoundingSphere();
}

let V3_GREY = null;
// the texture of a 512-unit patch, looking into the next cell when it's off this one's edge
function v3PatchAt(gx, gy, px, py, own){
  let cx = gx, cy = gy;
  if (px < 0){ cx--; px += 16; } else if (px > 15){ cx++; px -= 16; }
  if (py < 0){ cy--; py += 16; } else if (py > 15){ cy++; py -= 16; }
  const c = V3.lands[cx + ',' + cy];
  if (c && c.L && c.L.ids) return c.L.ids[py * 16 + px];
  return own[Math.max(0, Math.min(15, py)) * 16 + Math.max(0, Math.min(15, px))];   // no neighbour: this cell's edge
}
// after a cell loads or is painted, the cells around it blend into it again
function v3LandNeighbours(gx, gy){
  for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++){
    if (!dx && !dy) continue;
    const c = V3.lands[(gx + dx) + ',' + (gy + dy)];
    if (c && c.mesh && c.L) v3LandMaterial(c.mesh, c.L);
  }
}
function v3LandMaterial(mesh, L){
  const T = THREE, {gx, gy} = mesh.userData;
  // the patches of this cell plus a ring of its neighbours' (18 x 18), so textures blend across
  // cell edges the way they do in game
  const grid = [];
  for (let py = -1; py <= 16; py++) for (let px = -1; px <= 16; px++) grid.push(v3PatchAt(gx, gy, px, py, L.ids));
  // the textures used, in slots (with very many, the 12 used most)
  const count = {};
  grid.forEach(p => { count[p] = (count[p] || 0) + 1; });
  let slots = Object.keys(count).sort((a, b) => count[b] - count[a]).slice(0, V3_MAXTEX);
  const slotOf = {}; slots.forEach((p, i) => { slotOf[p] = i; });
  const data = new Uint8Array(18 * 18 * 4);
  grid.forEach((p, i) => { data[i * 4] = slotOf[p] !== undefined ? slotOf[p] : 0; data[i * 4 + 3] = 255; });
  const map = new T.DataTexture(data, 18, 18, T.RGBAFormat);
  map.magFilter = map.minFilter = T.NearestFilter; map.needsUpdate = true;
  if (!V3_GREY){ V3_GREY = new T.DataTexture(new Uint8Array([138, 132, 102, 255]), 1, 1, T.RGBAFormat); V3_GREY.needsUpdate = true; }
  const uniforms = {
    patchMap: {value: map},
    skyCol: {value: new T.Color()}, groundCol: {value: new T.Color()}, sunCol: {value: new T.Color()},
    sunDir: {value: new T.Vector3()}, ambCol: {value: new T.Color()},
    fogCol: {value: new T.Color()}, fogNear: {value: 1e9}, fogFar: {value: 2e9},
  };
  const N = Math.max(1, slots.length);
  for (let i = 0; i < N; i++){
    uniforms['tex' + i] = {value: V3_GREY};
    const p = slots[i];
    if (p && p !== 'null') v3Tex(p, t => { uniforms['tex' + i].value = t; });
  }
  let decl = '', pick = '';
  for (let i = 0; i < N; i++){
    decl += `uniform sampler2D tex${i};\n`;
    pick += `  c${i} = texture2D(tex${i}, tuv).rgb;\n`;
  }
  // Each patch's texture counts fully at its middle and fades out towards its neighbours' middles
  const frag = `
uniform sampler2D patchMap; ${decl}
uniform vec3 skyCol, groundCol, sunCol, sunDir, ambCol, fogCol; uniform float fogNear, fogFar;
varying vec2 vUv; varying vec3 vN, vCol; varying float vDepth;
float slotAt(vec2 p){ p = clamp(p, -1.0, 16.0); return floor(texture2D(patchMap, (p + 1.5) / 18.0).r * 255.0 + 0.5); }
void main(){
  vec2 g = vUv * 16.0 - 0.5, b = floor(g), f = smoothstep(0.0, 1.0, g - b);
  float s00 = slotAt(b), s10 = slotAt(b + vec2(1.0, 0.0)), s01 = slotAt(b + vec2(0.0, 1.0)), s11 = slotAt(b + vec2(1.0, 1.0));
  float w00 = (1.0 - f.x) * (1.0 - f.y), w10 = f.x * (1.0 - f.y), w01 = (1.0 - f.x) * f.y, w11 = f.x * f.y;
  vec2 tuv = vUv * 16.0;
  vec3 ${Array.from({length: N}, (_, i) => 'c' + i).join(', ')};
${pick}
  vec3 col = vec3(0.0);
  ${Array.from({length: N}, (_, i) => `col += c${i} * ((s00 == ${i}.0 ? w00 : 0.0) + (s10 == ${i}.0 ? w10 : 0.0) + (s01 == ${i}.0 ? w01 : 0.0) + (s11 == ${i}.0 ? w11 : 0.0));`).join('\n  ')}
  vec3 n = normalize(vN);
  vec3 light = mix(groundCol, skyCol, 0.5 * n.z + 0.5) + sunCol * max(dot(n, sunDir), 0.0) + ambCol;
  vec3 c = col * vCol * light;
  gl_FragColor = vec4(mix(c, fogCol, smoothstep(fogNear, fogFar, vDepth)), 1.0);
}`;
  const vert = `
attribute vec3 color; varying vec2 vUv; varying vec3 vN, vCol; varying float vDepth;
void main(){ vUv = uv; vN = normal; vCol = color; vec4 mv = modelViewMatrix * vec4(position, 1.0); vDepth = -mv.z; gl_Position = projectionMatrix * mv; }`;
  const m = new T.ShaderMaterial({uniforms, vertexShader: vert, fragmentShader: frag, wireframe: !!V3.view.wire});
  m.userData.slots = slots;
  mesh.onBeforeRender = () => v3LandLights(uniforms);
  if (mesh.material) mesh.material.dispose();
  mesh.material = m;
}
// the same light and fog as the rest of the scene
function v3LandLights(u){
  u.skyCol.value.copy(V3.hemi.color).multiplyScalar(V3.hemi.intensity);
  u.groundCol.value.copy(V3.hemi.groundColor).multiplyScalar(V3.hemi.intensity);
  u.sunCol.value.copy(V3.sun.color).multiplyScalar(V3.sun.intensity);
  u.sunDir.value.copy(V3.sun.position).sub(V3.sun.target.position).normalize();
  u.ambCol.value.copy(V3.amb.color).multiplyScalar(V3.amb.intensity);
  const f = V3.scene.fog;
  if (f){ u.fogCol.value.copy(f.color); u.fogNear.value = f.near; u.fogFar.value = f.far; }
  else { u.fogNear.value = 1e9; u.fogFar.value = 2e9; }
}

// ----- shaping and painting the ground -----
// V3.land: the open ground tool {tool: raise|lower|smooth|flatten|paint, size (units), strength 1-10, tex}
function v3LandOn(){ return !!(V3.land && W.ext); }
function v3Brush(e){
  V3.ray.setFromCamera(v3Mouse(e), V3.camera);
  const meshes = Object.values(V3.lands).map(c => c.mesh).filter(Boolean);
  const h = V3.ray.intersectObjects(meshes, false)[0];
  return h ? [h.point.x + V3.origin[0], h.point.y + V3.origin[1], h.point.z + V3.origin[2]] : null;
}
function v3BrushRing(at){
  const T = THREE;
  if (!V3.ring){
    V3.ring = new T.LineLoop(new T.BufferGeometry(), new T.LineBasicMaterial({color: 0xffe08a, depthTest: false, transparent: true}));
    V3.ring.geometry.setAttribute('position', new T.BufferAttribute(new Float32Array(64 * 3), 3));
    V3.ring.renderOrder = 20; V3.scene.add(V3.ring);
  }
  V3.ring.visible = !!at && v3LandOn();
  if (!V3.ring.visible) return;
  const p = V3.ring.geometry.attributes.position, R = V3.land.size;
  for (let i = 0; i < 64; i++){
    const a = i / 64 * Math.PI * 2, x = at[0] + Math.cos(a) * R, y = at[1] + Math.sin(a) * R;
    p.setXYZ(i, x - V3.origin[0], y - V3.origin[1], (v3GroundAt(x, y) ?? at[2]) + 6 - V3.origin[2]);
  }
  p.needsUpdate = true; V3.ring.geometry.computeBoundingSphere();
}
function v3GroundAt(x, y){
  const gx = Math.floor(x / CELL), gy = Math.floor(y / CELL), c = V3.lands[gx + ',' + gy];
  if (!c || !c.L) return null;
  const fx = (x - gx * CELL) / 128, fy = (y - gy * CELL) / 128, x0 = Math.min(63, Math.floor(fx)), y0 = Math.min(63, Math.floor(fy));
  const tx = fx - x0, ty = fy - y0, H = c.L.h;
  return (H[y0 * 65 + x0] * (1 - tx) + H[y0 * 65 + x0 + 1] * tx) * (1 - ty) + (H[(y0 + 1) * 65 + x0] * (1 - tx) + H[(y0 + 1) * 65 + x0 + 1] * tx) * ty;
}
function v3StrokeStart(e){
  const at = v3Brush(e); if (!at) return false;
  if (V3.land.tool === 'scatter'){
    // what already stands around counts as taken
    const near = [];
    for (const c of Object.values(W.cells)) for (const r of c.refs || []) if (Math.hypot(r.p[0] - at[0], r.p[1] - at[1]) < 6000 && !r.arch) near.push([r.p[0], r.p[1]]);
    const grass = V3.land.scatSet === 'grass' && V3.land.scatGrass !== false;
    if (grass) for (const lst of Object.values(V3.grassData || {})) for (const g of lst) if (Math.hypot(g[1] - at[0], g[2] - at[1]) < 6000) near.push([g[1], g[2]]);
    V3.stroke = {cells: new Map(), scatter: true, grass, circles: [], add: [], gone: new Map(), near, last: 0, lastAt: at, erase: e.ctrlKey};
    v3ScatterDab(at, e.ctrlKey);
    return true;
  }
  V3.stroke = {cells: new Map(), level: v3GroundAt(at[0], at[1]), last: 0};
  v3StrokeAt(at, e);
  return true;
}
function v3StrokeAt(at, e){
  const S_ = V3.stroke, B = V3.land; if (!S_ || !at) return;
  if (S_.scatter){
    // a new dab each time the brush has moved on by half its size
    if (Math.hypot(at[0] - S_.lastAt[0], at[1] - S_.lastAt[1]) > B.size * 0.5){ S_.lastAt = at; v3ScatterDab(at, S_.erase); }
    return;
  }
  const R = B.size, k = B.strength / 10, tool = B.tool === 'raise' && e.ctrlKey ? 'lower' : B.tool === 'lower' && e.ctrlKey ? 'raise' : B.tool;
  const touched = new Set();
  const fall = d => { const t = Math.max(0, 1 - d / R); return t * t * (3 - 2 * t); };
  for (const [ck, c] of Object.entries(V3.lands)){
    if (!c.L) continue;
    const ox = c.gx * CELL, oy = c.gy * CELL;
    if (at[0] + R < ox || at[0] - R > ox + CELL || at[1] + R < oy || at[1] - R > oy + CELL) continue;
    const L = c.L;
    if (tool === 'paint'){
      if (!B.tex) continue;
      let any = false;
      for (let py = 0; py < 16; py++) for (let px = 0; px < 16; px++){
        const d = Math.hypot(ox + (px + 0.5) * 512 - at[0], oy + (py + 0.5) * 512 - at[1]);
        if (d <= Math.max(R, 260) && L.ids[py * 16 + px] !== B.tex.path){ L.ids[py * 16 + px] = B.tex.path; any = true; }
      }
      if (any){ (L.texIds = L.texIds || {})[B.tex.path] = B.tex.id; v3StrokeMark(ck, 't'); v3LandMaterial(c.mesh, L); v3LandNeighbours(c.gx, c.gy); }
      continue;
    }
    const H = L.h, old = tool === 'smooth' ? H.slice() : null;
    let any = false;
    for (let y = 0; y <= 64; y++) for (let x = 0; x <= 64; x++){
      const d = Math.hypot(ox + x * 128 - at[0], oy + y * 128 - at[1]); if (d >= R) continue;
      const w = fall(d), v = y * 65 + x;
      if (tool === 'raise') H[v] += 24 * k * w;
      else if (tool === 'lower') H[v] -= 24 * k * w;
      else if (tool === 'flatten') H[v] += (S_.level - H[v]) * Math.min(1, 0.35 * k * w);
      else if (tool === 'smooth'){
        let s = 0, n = 0;
        for (let j = -1; j <= 1; j++) for (let i = -1; i <= 1; i++){
          const hv = (x + i >= 0 && x + i <= 64 && y + j >= 0 && y + j <= 64) ? old[(y + j) * 65 + x + i] : v3H(c.gx, c.gy, x + i, y + j);
          if (hv !== null){ s += hv; n++; }
        }
        H[v] += (s / n - H[v]) * Math.min(1, 0.5 * k * w);
      }
      any = true;
    }
    if (any){ v3StrokeMark(ck, 'h'); touched.add(ck); }
  }
  // keep the shared edges of neighbouring cells exactly level, then redraw
  for (const ck of touched){
    const c = V3.lands[ck], L = c.L;
    for (const [dx, dy] of [[1, 0], [0, 1], [-1, 0], [0, -1]]){
      const nb = V3.lands[(c.gx + dx) + ',' + (c.gy + dy)]; if (!nb || !nb.L) continue;
      for (let i = 0; i <= 64; i++){
        const mine = dx === 1 ? i * 65 + 64 : dx === -1 ? i * 65 : dy === 1 ? 64 * 65 + i : i;
        const theirs = dx === 1 ? i * 65 : dx === -1 ? i * 65 + 64 : dy === 1 ? i : 64 * 65 + i;
        if (nb.L.h[theirs] !== L.h[mine]){ nb.L.h[theirs] = L.h[mine]; v3StrokeMark((c.gx + dx) + ',' + (c.gy + dy), 'h'); }
      }
    }
  }
  for (const ck of S_.cells.keys()){
    const c = V3.lands[ck]; if (!c || !c.mesh || !S_.cells.get(ck).h) continue;
    v3LandHeights(c.mesh, c.L); v3LandNormals(c.mesh, c.L);
  }
}
function v3StrokeMark(ck, what){ const m = V3.stroke.cells.get(ck) || {}; m[what] = true; V3.stroke.cells.set(ck, m); }
async function v3StrokeEnd(){
  const S_ = V3.stroke; V3.stroke = null;
  if (S_ && S_.scatter) return v3ScatterEnd(S_);
  if (!S_ || !S_.cells.size) return;
  if (!await needProject()){ v3LandsReload(); return; }
  const cells = [];
  for (const [ck, what] of S_.cells){
    const c = V3.lands[ck]; if (!c || !c.L) continue;
    const L = c.L, cell = {gx: c.gx, gy: c.gy};
    if (what.h) cell.h = L.h.map(v => Math.round(v));
    if (what.t){
      // the server wants texture names: ones painted now, or the ones the cell already had
      cell.t = L.ids.map((p, i) => (L.texIds && L.texIds[p]) || L.origId[i] || '');
    }
    cells.push(cell);
  }
  try {
    const r = await post('/api/land/edit', {cells, keep_objects: V3.land.follow !== false});
    const n = cells.length;
    toast((S_.cells.size && cells.some(c => c.t) && !cells.some(c => c.h) ? 'Painted the ground' : 'Reshaped the ground') +
          (n > 1 ? ` in ${n} cells` : '') + (r.moved ? ` (${r.moved} objects followed it)` : '') + '. Ground changes show in game after a restart.');
    W.lands = {};
    if (r.moved) for (const k of Object.keys(W.cells)) if (W.cells[k].exists) await worldReloadCell(k);
    await loadAround(Math.floor(W.cam.x / CELL), Math.floor(W.cam.y / CELL));
    // what's on screen is already right; just remember the names of the textures painted
    for (const c of cells){ const L = V3.lands[c.gx + ',' + c.gy] && V3.lands[c.gx + ',' + c.gy].L; if (L && c.t) L.origId = c.t; }
    afterChange(); drawMap(); v3Refresh();
  } catch (err){ toast(err.message, true); v3LandsReload(); }
}

// the ground tool panel (outdoors, "⛰ Ground" in the toolbar)
const V3_LANDTOOLS = [['raise', '▲ Raise', 'Raise the ground (Ctrl: lower)'], ['lower', '▼ Lower', 'Lower the ground (Ctrl: raise)'],
  ['smooth', '≈ Smooth', 'Even out bumps'], ['flatten', '▬ Flatten', 'Level the ground to the height where you start the stroke'],
  ['paint', '🖌 Paint', 'Paint a ground texture (Shift+click: pick the texture under the mouse)'],
  ['scatter', '🌿 Scatter', 'Scatter grass, plants, rocks or trees of this region (Ctrl: clear them away)']];
// how far apart things of each kind usually grow (at thickness 5)
const V3_SCATTER_GAP = {grass: 110, plants: 200, rocks: 380, trees: 650, logs: 700};
function v3LandToggle(on){
  if (on && !W.ext) return toast('The ground tools are for outdoor places.', true);
  if (on){
    V3.land = V3.land || JSON.parse((() => { try { return localStorage.getItem('ws-land'); } catch (e) { return null; } })() || 'null') ||
      {tool: 'raise', size: 512, strength: 4, tex: null, follow: true};
    V3.landOpen = true;
    if (W.mode) setMode(null);
    W.sel = null; W.multi.clear(); renderWside();
  } else { V3.landOpen = false; V3.land = V3.land ? Object.assign({}, V3.land) : null; }
  v3Tools(); v3LandPanel(); v3Refresh();
  if (V3.ring) V3.ring.visible = false;
}
function v3LandSave(){ try { localStorage.setItem('ws-land', JSON.stringify(V3.land)); } catch (e) {} }
async function v3LandPanel(){
  let p = $('#v3land');
  if (!V3.landOpen || !W.ext){ if (p) p.remove(); return; }
  if (!p){ p = document.createElement('div'); p.id = 'v3land'; $('#v3wrap').appendChild(p); }
  const B = V3.land;
  p.innerHTML = `<div class="v3lhead"><b>Ground</b><button class="btn sm" data-lt="close" title="Close the ground tools">✕</button></div>
    <div class="v3lrow">${V3_LANDTOOLS.map(([k, l, t]) => `<button class="btn sm ${B.tool === k ? 'primary' : ''}" data-lt="${k}" title="${t}">${l}</button>`).join('')}</div>
    <label class="v3lrow">Size <input type="range" id="v3lsize" min="128" max="4096" step="64" value="${B.size}"><span>${B.size}</span></label>
    <label class="v3lrow">Strength <input type="range" id="v3lstr" min="1" max="10" value="${B.strength}"><span>${B.strength}</span></label>
    <label class="v3lrow" title="Things standing on the ground move up and down with it"><input type="checkbox" id="v3lfollow" ${B.follow !== false ? 'checked' : ''}> Objects follow the ground</label>
    <div id="v3ltex" style="display:${B.tool === 'paint' ? 'block' : 'none'}">
      <div class="v3lcur">${B.tex ? `<img data-swatch="${esc(B.tex.path)}"> <span>${esc(B.tex.id)}</span>` : '<span class="faint">Pick a texture below, or Shift+click the ground</span>'}</div>
      <input id="v3lq" placeholder="Search textures…" value="${esc(V3.landQ || '')}">
      <div id="v3lgrid"></div>
    </div>
    <div id="v3lscat" style="display:${B.tool === 'scatter' ? 'block' : 'none'}"></div>
    <div class="v3lnote">Drag on the ground to use the brush. Right-drag still looks around. Each stroke can be undone. ${B.tool === 'scatter' ? 'Scattered things show in game after a restart, like other new objects.' : 'Ground changes show in game after a restart.'}</div>`;
  p.querySelectorAll('[data-lt]').forEach(b => b.onclick = () => {
    const a = b.dataset.lt;
    if (a === 'close') return v3LandToggle(false);
    B.tool = a; v3LandSave(); v3LandPanel();
  });
  $('#v3lsize').oninput = e => { B.size = +e.target.value; e.target.nextElementSibling.textContent = B.size; v3LandSave(); };
  $('#v3lstr').oninput = e => { B.strength = +e.target.value; e.target.nextElementSibling.textContent = B.strength; v3LandSave(); };
  $('#v3lfollow').onchange = e => { B.follow = e.target.checked; v3LandSave(); };
  if (B.tool === 'paint'){
    if (!V3.landTex) V3.landTex = await api('/api/land/textures');
    const q = $('#v3lq'); q.oninput = () => { V3.landQ = q.value; v3LandGrid(); };
    v3LandGrid();
  }
  if (B.tool === 'scatter') v3ScatterPanel();
  v3SwatchScan(p);
}
// ----- scattering what grows in the region
async function v3ScatterPanel(){
  const box = $('#v3lscat'); if (!box) return;
  const ck = cellKeyAt(...v3CamWorld().slice(0, 2));
  if (!V3.scatSets || V3.scatSets.cell !== ck){
    box.innerHTML = '<div class="faint"><span class="spin"></span>Finding what grows here…</div>';
    try { V3.scatSets = await api('/api/scatter/sets?cell=' + encodeURIComponent(ck)); V3.scatSets.cell = ck; }
    catch (e){ box.innerHTML = `<div class="faint">${esc(e.message)}</div>`; return; }
  }
  const S_ = V3.scatSets, B = V3.land;
  if (!S_.sets.length){ box.innerHTML = '<div class="faint">Nothing grows in the cells around here to learn from. <button class="btn sm" id="v3lnewbr">+ New brush</button> makes one of your own.</div>';
    $('#v3lnewbr').onclick = async () => { try { await brNew(); v3ScatterPanel(); } catch (e){ toast(e.message, true); } }; return; }
  if (!S_.sets.some(s => s.key === B.scatSet)) B.scatSet = S_.sets[0].key;
  const set = S_.sets.find(s => s.key === B.scatSet);
  B.scatOff = B.scatOff || {};
  B.scatThick = B.scatThick || 5;
  box.innerHTML = `<div class="v3lrow" style="flex-wrap:wrap">${S_.sets.map(s => `<button class="btn sm ${s.key === B.scatSet ? 'primary' : ''}" data-ss="${s.key}" title="${s.mine ? 'One of your own brushes' : 'What grows in this region'}">${s.mine ? '★ ' : ''}${esc(s.label)}</button>`).join('')}
      <button class="btn sm" id="v3lnewbr" title="A brush of your own: any objects, from mods too">+ New brush</button></div>
    <label class="v3lrow">Thickness <input type="range" id="v3lthick" min="1" max="10" value="${B.scatThick}"><span>${B.scatThick}</span></label>` +
    (set.mine ? '' : `<div class="faint" style="margin:4px 0">From ${esc(S_.region ? S_.region.replace(/\b\w/g, c => c.toUpperCase()) : 'the cells around here')}, used most first. Click to leave one out:</div>
    <div class="v3scat">${set.items.map(it => `<label class="${B.scatOff[it.id.toLowerCase()] ? '' : 'on'}" title="${esc(it.id)} — used ${it.n} times nearby"><input type="checkbox" data-si="${esc(it.id)}" ${B.scatOff[it.id.toLowerCase()] ? '' : 'checked'}> ${esc(it.name || it.id)}</label>`).join('')}</div>`);
  if (set.mine) brEditor(box, set);
  $('#v3lnewbr').onclick = async () => { try { await brNew(); v3ScatterPanel(); } catch (e){ toast(e.message, true); } };
  if (B.scatSet === 'grass'){
    // grass can go in as OpenMW groundcover: no collision, drawn fast, swaying, kept in its own file
    if (B.scatGrass === undefined) B.scatGrass = true;
    const st = V3.grassStatus;
    box.insertAdjacentHTML('beforeend', `<label class="v3lrow" style="display:flex;align-items:center;gap:6px;margin-top:6px" title="OpenMW draws groundcover fast and in great numbers, sways it in the wind and lets you walk through it. It goes into its own file next to your mod."><input type="checkbox" id="v3lgc" ${B.scatGrass ? 'checked' : ''}> As groundcover (its own grass file)</label>
      ${B.scatGrass ? `<div class="v3lrow"><button class="btn sm" id="v3lfill" title="Grass on grassy ground, thinner on dirt, none on roads, rocks, sand or under water">🌾 Grow it over this cell</button><button class="btn sm" id="v3lfill9" title="This cell and the eight around it">…and around</button><button class="btn sm" id="v3lclear" title="Take the groundcover out of this cell">Clear cell</button></div>
      <div class="faint" id="v3lgcst">${st ? (st.enabled ? `Groundcover is on in OpenMW. ${V3.grassTotal || 0} tufts in your grass file.` : 'Groundcover is off in your OpenMW settings, so the game won\'t show this grass. <button class="btn sm" id="v3lgcon">Turn it on</button>') : ''}</div>` : ''}`);
    const gc = $('#v3lgc'); if (gc) gc.onchange = () => { B.scatGrass = gc.checked; v3LandSave(); v3ScatterPanel(); };
    const fillCells = async around => {
      if (!await needProject()) return;
      const [cx, cy] = v3CamCell(), cells = [];
      for (let dx = around ? -1 : 0; dx <= (around ? 1 : 0); dx++) for (let dy = around ? -1 : 0; dy <= (around ? 1 : 0); dy++) cells.push('#' + (cx + dx) + ',' + (cy + dy));
      const ids = v3ScatterItems().map(i => i.id);
      toast('Growing grass…');
      try { const r = await post('/api/grass/fill', {cells, thickness: B.scatThick, ids}); toast(`Grew ${r.made} tufts of grass in ${r.cells} cell${r.cells === 1 ? '' : 's'}. Undo takes it back.`); afterChange(); v3GrassReload(); }
      catch (e){ toast(e.message, true); }
    };
    const f1 = $('#v3lfill'); if (f1) f1.onclick = () => fillCells(false);
    const f9 = $('#v3lfill9'); if (f9) f9.onclick = () => fillCells(true);
    const cl = $('#v3lclear'); if (cl) cl.onclick = async () => {
      if (!await needProject()) return;
      const [cx, cy] = v3CamCell();
      try { const r = await post('/api/grass/clear', {cells: ['#' + cx + ',' + cy]}); toast(`Took out ${r.removed} tufts.`); afterChange(); v3GrassReload(); } catch (e){ toast(e.message, true); }
    };
    const on = $('#v3lgcon'); if (on) on.onclick = async () => {
      if (!confirm('Turn on groundcover in your OpenMW settings (settings.cfg)? The Workshop makes a backup first. It takes effect the next time the game starts.')) return;
      try { V3.grassStatus = await post('/api/grass/enable', {}); toast('Groundcover is on. Start the game again to see grass.'); v3ScatterPanel(); } catch (e){ toast(e.message, true); }
    };
  }
  box.querySelectorAll('[data-ss]').forEach(b => b.onclick = () => { B.scatSet = b.dataset.ss; v3LandSave(); v3ScatterPanel(); });
  $('#v3lthick').oninput = e => { B.scatThick = +e.target.value; e.target.nextElementSibling.textContent = B.scatThick; v3LandSave(); };
  box.querySelectorAll('[data-si]').forEach(c => c.onchange = () => { const k = c.dataset.si.toLowerCase(); if (c.checked) delete B.scatOff[k]; else B.scatOff[k] = 1; v3LandSave(); c.parentElement.classList.toggle('on', c.checked); });
}
function v3ScatterItems(){
  const S_ = V3.scatSets, B = V3.land; if (!S_) return [];
  const set = S_.sets.find(s => s.key === B.scatSet); if (!set) return [];
  return set.items.filter(it => !(B.scatOff || {})[it.id.toLowerCase()]);
}
// ----- the mod's groundcover in the 3D view: thousands of tufts, drawn as instances of each model
async function v3GrassReload(){
  if (!V3.scene || !W.ext || !S.summary || !S.summary.project){ v3GrassDrop(); return; }
  const [cx, cy] = v3CamCell();
  V3.grassFor = cx + ',' + cy;
  let r;
  try { r = await api(`/api/grass?gx=${cx}&gy=${cy}&r=1`); } catch (e){ return; }
  V3.grassData = r.cells; V3.grassStatus = r.status; V3.grassTotal = r.total;
  const ids = [...new Set(Object.values(r.cells).flatMap(l => l.map(g => g[0])))];
  if (ids.length) await v3EnsureModels(ids);
  v3GrassBuild();
  const st = $('#v3lgcst');
  if (st && r.status.enabled) st.textContent = `Groundcover is on in OpenMW. ${r.total} tufts in your grass file.`;
}
function v3GrassDrop(){
  if (V3.grassGroup){ V3.scene.remove(V3.grassGroup); V3.grassGroup.children.forEach(m => m.dispose && m.dispose()); V3.grassGroup = null; }
}
function v3GrassBuild(){
  const T = THREE;
  v3GrassDrop();
  const data = V3.grassData || {};
  const byId = {};
  for (const lst of Object.values(data)) for (const g of lst) (byId[g[0].toLowerCase()] = byId[g[0].toLowerCase()] || []).push(g);
  const grp = new T.Group(), m4 = new T.Matrix4(), q = new T.Quaternion(), e = new T.Euler(), pos = new T.Vector3(), sc = new T.Vector3();
  for (const [id, list] of Object.entries(byId)){
    const model = V3.models[id];
    if (!model || !model.parts.length) continue;
    for (const part of model.parts){
      const inst = new T.InstancedMesh(part.geo, part.mat, list.length);
      list.forEach((g, i) => {
        pos.set(g[1] - V3.origin[0], g[2] - V3.origin[1], g[3] - V3.origin[2]);
        e.set(0, 0, -g[4]); q.setFromEuler(e); sc.set(g[5], g[5], g[5]);
        m4.compose(pos, q, sc); inst.setMatrixAt(i, m4);
      });
      inst.instanceMatrix.needsUpdate = true;
      inst.userData.grass = true;               // (not something to click and select)
      grp.add(inst);
    }
  }
  V3.grassGroup = grp; V3.scene.add(grp);
}
// one dab: new spots inside the brush, not too close to each other or to what is already there
function v3ScatterDab(at, erase){
  const S_ = V3.stroke, B = V3.land, R = B.size, items = v3ScatterItems();
  if (!items.length) return;
  const ids = new Set(v3ScatterItems().map(i => i.id.toLowerCase()));
  if (erase && S_.grass){
    // groundcover: everything in the brush goes (red dots show what)
    S_.circles.push([at[0], at[1], R]);
    for (const lst of Object.values(V3.grassData || {})) for (const g of lst){
      if (Math.hypot(g[1] - at[0], g[2] - at[1]) <= R){ const k = g[1] + ',' + g[2]; if (!S_.gone.has(k)) S_.gone.set(k, {x: g[1], y: g[2], z: g[3]}); }
    }
    v3ScatterShow(); return;
  }
  if (erase){
    for (const [ck, c] of Object.entries(W.cells)) for (const r of c.refs || []){
      if (!ids.has(r.id.toLowerCase()) || Math.hypot(r.p[0] - at[0], r.p[1] - at[1]) > R) continue;
      const k = ck + '|' + r.k; if (!S_.gone.has(k)){ S_.gone.set(k, {cell: ck, ref: r.k, x: r.p[0], y: r.p[1], z: r.p[2]}); }
    }
    v3ScatterShow(); return;
  }
  const cur = V3.scatSets && V3.scatSets.sets.find(s => s.key === B.scatSet);
  const gap = (V3_SCATTER_GAP[B.scatSet] || (cur && cur.gap) || 200) * (11 - B.scatThick) / 6;
  const tries = Math.max(1, Math.round(Math.PI * R * R / (gap * gap)));
  const total = items.reduce((a, i) => a + i.n, 0);
  for (let t = 0; t < tries; t++){
    const a = Math.random() * Math.PI * 2, d = Math.sqrt(Math.random()) * R, x = at[0] + Math.cos(a) * d, y = at[1] + Math.sin(a) * d;
    const g = v3GroundAt(x, y); if (g == null) continue;
    if (S_.near.some(p => Math.hypot(p[0] - x, p[1] - y) < gap * 0.7)) continue;
    // the game's own mix: things used more often come up more often
    let pick = Math.random() * total, it = items[0];
    for (const i of items){ pick -= i.n; if (pick <= 0){ it = i; break; } }
    const s = it.smin + Math.random() * Math.max(0, it.smax - it.smin);
    S_.add.push({id: it.id, lib: it.lib, x, y, z: g - it.sink * s - it.zmin * s, rz: Math.random() * Math.PI * 2, s: Math.round(s * 100) / 100});
    S_.near.push([x, y]);
  }
  v3ScatterShow();
}
// dots where things will go (green) or be cleared (red), until the stroke is let go
function v3ScatterShow(){
  const T = THREE, S_ = V3.stroke; if (!S_) return;
  const pts = S_.add.map(p => [p.x, p.y, p.z + 40, 0]).concat([...S_.gone.values()].map(p => [p.x, p.y, p.z + 60, 1]));
  if (V3.scatDots){ V3.scene.remove(V3.scatDots); V3.scatDots.geometry.dispose(); }
  const pos = new Float32Array(pts.length * 3), col = new Float32Array(pts.length * 3);
  pts.forEach((p, i) => { pos[i * 3] = p[0] - V3.origin[0]; pos[i * 3 + 1] = p[1] - V3.origin[1]; pos[i * 3 + 2] = p[2] - V3.origin[2];
    col[i * 3] = p[3] ? 1 : 0.55; col[i * 3 + 1] = p[3] ? 0.3 : 0.95; col[i * 3 + 2] = p[3] ? 0.25 : 0.4; });
  const geo = new T.BufferGeometry(); geo.setAttribute('position', new T.BufferAttribute(pos, 3)); geo.setAttribute('color', new T.BufferAttribute(col, 3));
  V3.scatDots = new T.Points(geo, new T.PointsMaterial({size: 14, vertexColors: true, depthTest: false, transparent: true, opacity: 0.9}));
  V3.scatDots.renderOrder = 21; V3.scene.add(V3.scatDots);
}
async function v3ScatterEnd(S_){
  if (V3.scatDots){ V3.scene.remove(V3.scatDots); V3.scatDots.geometry.dispose(); V3.scatDots = null; }
  if (!S_.add.length && !S_.gone.size) return;
  if (!await needProject()) return;
  if (S_.grass){
    try {
      if (S_.circles.length){ const r = await post('/api/grass/remove', {circles: S_.circles}); toast(`Cleared away ${r.removed} tufts of grass.`); }
      else { const r = await post('/api/grass/add', {items: S_.add}); toast(`Painted ${r.added} tufts of groundcover. Undo takes the whole stroke back.`); }
      afterChange(); v3GrassReload();
    } catch (e){ toast(e.message, true); }
    return;
  }
  try {
    let msg;
    if (S_.gone.size){
      await post('/api/group/delete', {refs: [...S_.gone.values()].map(g => ({cell: g.cell, ref: g.ref}))});
      msg = `Cleared away ${S_.gone.size} things`;
    } else {
      const cx = S_.add.reduce((a, p) => a + p.x, 0) / S_.add.length, cy = S_.add.reduce((a, p) => a + p.y, 0) / S_.add.length;
      const set = V3.scatSets.sets.find(s => s.key === V3.land.scatSet);
      await post('/api/group/place', {cell: cellKeyAt(cx, cy), x: cx, y: cy, z: 0, yaw: 0, label: (set ? set.label : 'plants').toLowerCase(),
        items: S_.add.map(p => ({id: p.id, lib: p.lib, type: p.lib ? 'STAT' : undefined, dx: p.x - cx, dy: p.y - cy, dz: p.z, rz: p.rz, s: p.s}))});
      msg = `Scattered ${S_.add.length} ${set ? set.label.toLowerCase() : 'things'}`;
    }
    toast(msg + '. Undo takes the whole stroke back.');
    for (const k of Object.keys(W.cells)) if (W.cells[k].exists) await worldReloadCell(k);
    afterChange(); v3Refresh();
  } catch (e){ toast(e.message, true); }
}
function v3LandGrid(){
  const g = $('#v3lgrid'); if (!g) return;
  const q = (V3.landQ || '').toLowerCase().split(/\s+/).filter(Boolean);
  // textures used nearby first, then everything else
  const near = new Set();
  for (const c of Object.values(V3.lands)) if (c.L) c.L.ids.forEach(p => near.add(p));
  const all = (V3.landTex || []).filter(t => q.every(w => (t.id + ' ' + t.file).toLowerCase().includes(w)));
  all.sort((a, b) => (near.has(b.path) - near.has(a.path)) || a.id.localeCompare(b.id));
  g.innerHTML = all.slice(0, 120).map(t => `<button class="v3lt ${V3.land.tex && V3.land.tex.path === t.path ? 'on' : ''}" data-tp="${esc(t.path)}" title="${esc(t.id)} (${esc(t.file)})"><img data-swatch="${esc(t.path)}"><span>${esc(t.id)}</span></button>`).join('') +
    (all.length > 120 ? `<div class="faint">…and ${all.length - 120} more. Type to narrow it down.</div>` : '') + (!all.length ? '<div class="faint">No textures match.</div>' : '');
  g.querySelectorAll('[data-tp]').forEach(b => b.onclick = () => {
    const t = V3.landTex.find(x => x.path === b.dataset.tp); V3.land.tex = {id: t.id, path: t.path}; v3LandSave(); v3LandPanel();
  });
  v3SwatchScan(g);
}
// small pictures of ground textures (drawn with WebGL, since the browser can't show .dds files)
const SWATCH = {};
function v3SwatchScan(root){
  root.querySelectorAll('img[data-swatch]:not([data-done])').forEach(img => {
    img.dataset.done = '1';
    const path = img.dataset.swatch;
    if (SWATCH[path]){ if (typeof SWATCH[path] === 'string') img.src = SWATCH[path]; else SWATCH[path].push(img); return; }
    SWATCH[path] = [img];
    v3Tex(path, tex => {
      const T = THREE;
      v3ThumbSetup();
      if (!SWATCH.scene){
        SWATCH.scene = new T.Scene(); SWATCH.cam = new T.OrthographicCamera(-1, 1, 1, -1, 0, 2);
        SWATCH.mesh = new T.Mesh(new T.PlaneGeometry(2, 2), new T.MeshBasicMaterial()); SWATCH.scene.add(SWATCH.mesh);
        SWATCH.cam.position.z = 1;
      }
      SWATCH.mesh.material.map = tex; SWATCH.mesh.material.needsUpdate = true;
      THUMB.r.setSize(48, 48, false); THUMB.r.render(SWATCH.scene, SWATCH.cam);
      const url = THUMB.r.domElement.toDataURL('image/png'), imgs = SWATCH[path];
      SWATCH[path] = url; imgs.forEach(i => { i.src = url; });
    }, () => { SWATCH[path] = ''; });
  });
}
// Shift+click while painting: use the texture under the mouse
function v3LandEyedrop(at){
  const gx = Math.floor(at[0] / CELL), gy = Math.floor(at[1] / CELL), c = V3.lands[gx + ',' + gy];
  if (!c || !c.L) return;
  const px = Math.min(15, Math.floor((at[0] - gx * CELL) / 512)), py = Math.min(15, Math.floor((at[1] - gy * CELL) / 512)), i = py * 16 + px;
  const path = c.L.ids[i], id = (c.L.texIds && c.L.texIds[path]) || c.L.origId[i];
  if (!path || !id) return toast('That is the plain default ground; pick a texture from the list.', true);
  V3.land.tex = {id, path}; v3LandSave(); v3LandPanel(); toast('Painting with ' + id);
}

// ----- camera and mouse -----
function v3CamWorld(){ return [V3.pos.x + V3.origin[0], V3.pos.y + V3.origin[1], V3.pos.z + V3.origin[2]]; }
function v3CamCell(){ const [x, y] = v3CamWorld(); return [Math.floor(x / CELL), Math.floor(y / CELL)]; }
function v3Dir(){ return new THREE.Vector3(Math.sin(V3.yaw) * Math.cos(V3.pitch), Math.cos(V3.yaw) * Math.cos(V3.pitch), Math.sin(V3.pitch)); }
function v3Typing(e){ const t = e.target; return t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable); }

function v3Bind(el){
  let drag = null;
  el.addEventListener('contextmenu', e => e.preventDefault());
  // (no browser autoscroll on a middle-click: it swallows the button coming up, and the view kept sliding)
  el.addEventListener('auxclick', e => { if (e.button === 1) e.preventDefault(); });
  el.addEventListener('mousedown', e => {
    el.focus();
    if (e.button === 1) e.preventDefault();
    if (e.button === 0 && (V3.tc.dragging || V3.tc.axis)) return;      // using the handles
    if (e.button === 0 && !e.altKey && v3LandOn() && V3.landOpen){
      // the ground brush
      if (e.shiftKey && V3.land.tool === 'paint'){ const at = v3Brush(e); if (at) v3LandEyedrop(at); return; }
      if (V3.land.tool === 'paint' && !V3.land.tex){ toast('Pick a ground texture first.', true); return; }
      if (V3.land.tool === 'scatter' && !v3ScatterItems().length){ toast('Pick something to scatter first.', true); return; }
      if (v3StrokeStart(e)){ drag = {b: 0, x: e.clientX, y: e.clientY, moved: true, stroke: true}; }
      return;
    }
    drag = {b: e.button, x: e.clientX, y: e.clientY, yaw: V3.yaw, pitch: V3.pitch, pos: V3.pos.clone(), moved: false, alt: e.altKey};
    // drawing a box to select: drag from an empty spot (or anywhere with Shift)
    if (e.button === 0 && !e.altKey && !W.mode){
      const h = e.shiftKey ? null : v3Pick(e, false);
      if (e.shiftKey || !(h && h.obj)) drag.box = {add: e.shiftKey};
    }
    if (e.button === 0 && e.altKey && W.sel){
      const o = V3.objs.get(W.sel.cell + '|' + W.sel.k);
      if (o){ drag.pivot = o.g.position.clone(); drag.dist = V3.pos.distanceTo(drag.pivot); }
    }
  });
  window.addEventListener('mousemove', e => {
    if (!drag || !V3.on) return;
    // the button was let go where we couldn't see it (outside the window, over a menu): stop right here
    if (!(e.buttons & ({0: 1, 1: 4, 2: 2}[drag.b] || 0))){
      const D = drag; drag = null;
      if (D.stroke){ V3.strokeEv = null; v3StrokeEnd(); }
      v3BoxHide();
      return;
    }
    if (drag.stroke){
      // a few dabs a second while the mouse moves (and while it rests, see v3Loop)
      V3.strokeEv = e;
      const now = performance.now();
      if (now - V3.stroke.last > 33){ V3.stroke.last = now; const at = v3Brush(e); v3StrokeAt(at, e); v3BrushRing(at); }
      return;
    }
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (Math.hypot(dx, dy) > 3) drag.moved = true;
    if (drag.box){ if (drag.moved) v3BoxDraw(drag, e); return; }
    if (drag.b === 2 || (drag.b === 0 && drag.alt && !drag.pivot)){
      V3.yaw = drag.yaw + dx * 0.005; V3.pitch = Math.max(-1.5, Math.min(1.5, drag.pitch - dy * 0.005));
    } else if (drag.b === 0 && drag.pivot){
      // Alt + drag: circle around the selected object
      V3.yaw = drag.yaw + dx * 0.006; V3.pitch = Math.max(-1.5, Math.min(1.5, drag.pitch - dy * 0.006));
      V3.pos.copy(drag.pivot).addScaledVector(v3Dir(), -drag.dist);
    } else if (drag.b === 1){
      const d = v3Dir(), right = new THREE.Vector3(d.y, -d.x, 0).normalize(), up = new THREE.Vector3().crossVectors(right, d);
      const k = 2.2;
      V3.pos.copy(drag.pos).addScaledVector(right, -dx * k).addScaledVector(up, dy * k);
    }
  });
  window.addEventListener('mouseup', e => {
    const D = drag; drag = null;
    if (D && D.stroke){ V3.strokeEv = null; v3StrokeEnd(); return; }
    if (D && D.box && D.moved){ v3BoxEnd(D, e); return; }
    v3BoxHide();
    // a right-click without dragging: the menu for what's under the mouse
    if (D && V3.on && D.b === 2 && !D.moved && e.target === el && typeof cfMenuAt === 'function'){
      const h = W.mode ? null : v3Pick(e, false);
      cfMenuAt(e, h && h.obj ? [h.obj.ck, h.obj.r] : null, h && h.world);
      return;
    }
    if (!D || !V3.on || D.moved || D.b !== 0 || e.target !== el) return;
    v3Click(e);
  });
  el.addEventListener('wheel', e => {
    e.preventDefault();
    if ((W.mode === 'place' || W.mode === 'group') && V3.ghost){
      // placing: the wheel turns the preview (Shift: fine steps)
      const G = V3.ghost, step = (e.shiftKey ? 1 : 15) * Math.PI / 180;
      G.yaw = ((G.yaw + (e.deltaY < 0 ? step : -step)) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI);
      G.g.rotation.set(0, 0, -G.yaw);
      if (W.mode === 'group'){ W.groupPlace.yaw = G.yaw; groupHint(); } else v3PlaceHint();
      return;
    }
    V3.pos.addScaledVector(v3Dir(), (e.deltaY < 0 ? 1 : -1) * (e.shiftKey ? 600 : 160));
  }, {passive: false});
  el.addEventListener('dblclick', () => { if (W.sel){ const o = V3.objs.get(W.sel.cell + '|' + W.sel.k); if (o) v3FocusObj(o.g); } });
  el.addEventListener('mousemove', e => v3Hover(e));
  el.addEventListener('mouseleave', () => { $('#maptip').style.display = 'none'; });
  // dropping things from the sidebar
  el.addEventListener('dragover', e => {
    if (!e.dataTransfer.types.includes('text/x-mw-id')) return;
    e.preventDefault(); e.dataTransfer.dropEffect = 'copy';
    if (window.wsDrag){ v3GhostSet(wsDrag.id, wsDrag.type); v3GhostMove(e); }
  });
  el.addEventListener('dragleave', () => { if (V3.ghost && W.mode !== 'place') v3GhostSet(null); });
  el.addEventListener('drop', e => {
    const id = e.dataTransfer.getData('text/x-mw-id'); if (!id) return;
    e.preventDefault();
    const G = V3.ghost && V3.ghost.id === id ? V3.ghost : null;
    const h = G && G.hit ? {world: G.hit} : v3Pick(e, true);
    const yaw = G ? G.yaw : undefined;
    if (W.mode !== 'place') v3GhostSet(null);
    if (!h || !h.world) return toast('Drop it onto the ground, a floor or another object.', true);
    v3PlaceAt(id, e.dataTransfer.getData('text/x-mw-name'), h.world, yaw);
  });
  window.addEventListener('keydown', e => {
    if (!V3.on || !$('#world').classList.contains('on') || v3Typing(e)) return;
    const k = e.key.toLowerCase(), mv = v3MoveKey(e);
    if (mv && !e.ctrlKey && !e.altKey && !e.metaKey){ V3.keys[mv] = true; e.preventDefault(); }
    if (e.key === 'Shift') V3.keys.shift = true;
    if (e.key === 'Escape') V3.keys = {};
    // (Move/Turn, look at it and set it down are shortcuts you can change: see comfort.js)
    if (e.key === 'Escape' && V3.landOpen) v3LandToggle(false);
    if (V3.landOpen && W.ext && (e.key === '[' || e.key === ']')){
      V3.land.size = Math.max(128, Math.min(4096, V3.land.size + (e.key === ']' ? 128 : -128))); v3LandSave(); v3LandPanel();
    }
  });
  // letting go of a key always stops it (heard first, before anything else can swallow it)
  window.addEventListener('keyup', e => {
    const mv = v3MoveKey(e); if (mv) V3.keys[mv] = false;
    const k = e.key.toLowerCase(); if (k.length === 1 && V3.keys[k]) V3.keys[k] = false;
    if (e.key === 'Shift') V3.keys.shift = false;
    if (e.key === 'Meta' || e.key === 'OS') V3.keys = {};   // (the Windows key: the Start menu eats the rest)
  }, true);
  const stop = () => { V3.keys = {}; };
  window.addEventListener('blur', stop);
  document.addEventListener('visibilitychange', () => { if (document.hidden) stop(); });
  // (the keyboard itself said a key is no longer down, e.g. Shift seen up on a mouse move)
  window.addEventListener('mousemove', e => { if (V3.keys.shift && !e.shiftKey) V3.keys.shift = false; }, true);
}

// which way a key moves the camera: by where the key sits on the keyboard (so it works in any layout,
// and switching layout while a key is down can't leave it stuck)
function v3MoveKey(e){
  const c = {KeyW: 'w', KeyA: 'a', KeyS: 's', KeyD: 'd', KeyQ: 'q', KeyE: 'e'}[e.code];
  if (c) return c;
  const k = (e.key || '').toLowerCase();
  return k.length === 1 && 'wasdqe'.includes(k) ? k : null;
}

function v3Mouse(e){
  const b = V3.renderer.domElement.getBoundingClientRect();
  return new THREE.Vector2(((e.clientX - b.left) / b.width) * 2 - 1, -((e.clientY - b.top) / b.height) * 2 + 1);
}
// What's under the mouse: {key (object) or null, point, world [x, y, z]}
function v3Pick(e, any, skipKey){
  V3.ray.setFromCamera(v3Mouse(e), V3.camera);
  const hits = V3.ray.intersectObjects([V3.root, V3.ground], true);
  let lockedHit = false;
  for (const h of hits){
    let o = h.object; while (o && !o.userData.ref && !o.userData.ground) o = o.parent;
    if (!o) continue;
    const world = [h.point.x + V3.origin[0], h.point.y + V3.origin[1], h.point.z + V3.origin[2]];
    if (o.userData.ground) return {key: null, point: h.point, world};
    if (o.userData.ref === skipKey) continue;
    const ob = V3.objs.get(o.userData.ref);
    if (!any && ob && ob.r.arch && W.lockArch){ lockedHit = true; continue; }
    return {key: o.userData.ref, obj: ob, point: h.point, world};
  }
  return lockedHit ? {locked: true} : null;
}

function v3Click(e){
  if (W.mode === 'arrive'){
    const h = v3Pick(e, true);
    if (!h || !h.world) return toast('Click on the floor or ground where the player should arrive.', true);
    // facing the way the camera looks, in whole 15° steps
    const yaw = Math.round(((V3.yaw % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI) / (Math.PI / 12)) * (Math.PI / 12);
    arriveAt(h.world[0], h.world[1], h.world[2] + 10, yaw);
    return;
  }
  if (W.mode === 'place' || W.mode === 'play'){
    const G = W.mode === 'place' && V3.ghost;
    const h = G && G.hit ? {world: G.hit} : v3Pick(e, true);
    if (!h || !h.world) return toast('Click on the ground, a floor or an object.', true);
    if (W.mode === 'place') v3PlaceAt(W.placeId, W.placeName, h.world, G ? G.yaw : undefined);
    else { setMode(null); playHere({cell: cellKeyAt(h.world[0], h.world[1]), x: h.world[0], y: h.world[1], z: h.world[2] + 60, rz: 0}); }
    return;
  }
  if (W.mode === 'group'){
    const G = V3.ghost;
    const h = G && G.hit ? {world: G.hit} : v3Pick(e, true);
    if (!h || !h.world) return toast('Click on the ground or a floor.', true);
    placeGroupAt(h.world[0], h.world[1], h.world[2]);
    return;
  }
  const h = v3Pick(e, false);
  if (h && h.obj && e.shiftKey){ toggleMulti(h.obj.ck, h.obj.k); return; }
  if (h && h.obj){ selectRef(h.obj.ck, h.obj.k); return; }
  if (h && h.locked) toast('Walls and buildings are locked. Untick "Lock walls & buildings" in the View panel to select them.');
  W.sel = null; renderWside(); v3Refresh();
}

// ----- selecting with a box: everything whose middle is inside it (Shift adds to what's selected)
function v3BoxRect(D, e){
  const b = $('#v3wrap').getBoundingClientRect();
  return {x0: Math.min(D.x, e.clientX) - b.left, x1: Math.max(D.x, e.clientX) - b.left, y0: Math.min(D.y, e.clientY) - b.top, y1: Math.max(D.y, e.clientY) - b.top, w: b.width, h: b.height};
}
function v3BoxDraw(D, e){
  let el = $('#v3box');
  if (!el){ el = document.createElement('div'); el.id = 'v3box'; el.style.cssText = 'position:absolute;border:1px dashed var(--gold);background:#d9b26a1c;pointer-events:none;z-index:4'; $('#v3wrap').appendChild(el); }
  const R = v3BoxRect(D, e);
  Object.assign(el.style, {display: 'block', left: R.x0 + 'px', top: R.y0 + 'px', width: (R.x1 - R.x0) + 'px', height: (R.y1 - R.y0) + 'px'});
}
function v3BoxHide(){ const el = $('#v3box'); if (el) el.style.display = 'none'; }
function v3BoxEnd(D, e){
  v3BoxHide();
  const R = v3BoxRect(D, e); if (R.x1 - R.x0 < 5 || R.y1 - R.y0 < 5) return;
  const T = THREE, v = new T.Vector3(), box = new T.Box3(), fwd = v3Dir();
  if (!D.box.add) W.multi.clear();
  for (const o of V3.objs.values()){
    if (!o.r || !o.g.visible) continue;
    if (o.r.arch && W.lockArch) continue;
    box.setFromObject(o.g); if (box.isEmpty()) continue;
    box.getCenter(v);
    if (v.clone().sub(V3.pos).dot(fwd) <= 0) continue;          // behind the camera
    v.project(V3.camera);
    const sx = (v.x + 1) / 2 * R.w, sy = (1 - v.y) / 2 * R.h;
    if (sx >= R.x0 && sx <= R.x1 && sy >= R.y0 && sy <= R.y1) W.multi.set(mkey(o.ck, o.k), {cell: o.ck, k: o.k});
  }
  if (W.sel && D.box.add && !W.multi.has(mkey(W.sel.cell, W.sel.k)) && findRef(W.sel.cell, W.sel.k)) W.multi.set(mkey(W.sel.cell, W.sel.k), {cell: W.sel.cell, k: W.sel.k});
  const n = W.multi.size;
  if (n === 1){ const only = [...W.multi.values()][0]; W.multi.clear(); selectRef(only.cell, only.k); }
  else if (n > 1){ const last = [...W.multi.values()].pop(); W.sel = {cell: last.cell, k: last.k}; W.tab = 'sel'; renderWside(); }
  else if (!D.box.add){ W.sel = null; renderWside(); }
  v3Refresh();
  if (!n) toast('Nothing inside the box' + (W.lockArch ? ' (walls and buildings are locked: see View).' : '.'));
}

function v3PlaceHint(){
  if (W.mode !== 'place') return;
  const deg = V3.ghost ? Math.round(V3.ghost.yaw * 180 / Math.PI) : 0;
  setBanner(`Placing <b>${esc(W.placeName)}</b>: point where it should go, <b>wheel</b> to turn it (${deg}°, Shift for fine steps), <b>click</b> to place. Esc to stop.`, 'place3d');
}
function v3Hover(e){
  if (!V3.on || V3.tc.dragging) return;
  if (W.mode === 'place' || W.mode === 'group'){ v3GhostMove(e); $('#maptip').style.display = 'none'; return; }
  if (v3LandOn() && V3.landOpen){
    if (V3.stroke) return;
    const now = performance.now(); if (now - (V3.hoverT || 0) < 30) return; V3.hoverT = now;
    v3BrushRing(v3Brush(e)); $('#maptip').style.display = 'none'; return;
  }
  const now = performance.now(); if (now - (V3.hoverT || 0) < 60) return; V3.hoverT = now;
  const h = v3Pick(e, true), tip = $('#maptip');
  if (h && h.obj){
    const r = h.obj.r, b = $('#v3wrap').getBoundingClientRect();
    tip.style.display = 'block'; tip.style.left = (e.clientX - b.left + 14) + 'px'; tip.style.top = (e.clientY - b.top + 10) + 'px';
    tip.innerHTML = `<b>${esc(r.name || r.id)}</b> <span style="color:var(--faint)">${esc(S.typeLabels[r.type] || r.type || 'unknown')}</span>`;
  } else tip.style.display = 'none';
}

function v3FocusObj(g){
  const box = new THREE.Box3().setFromObject(g), c = box.getCenter(new THREE.Vector3());
  const size = Math.max(80, box.getSize(new THREE.Vector3()).length());
  V3.pos.copy(c).addScaledVector(v3Dir(), -size * 1.6);
}
// centre the view on a ref (from the object list, or a pick in game)
function v3Focus(r){
  const o = [...V3.objs.values()].find(x => x.k === r.k);
  if (o) v3FocusObj(o.g);
  else { V3.pos.set(r.p[0] - V3.origin[0], r.p[1] - V3.origin[1], r.p[2] - V3.origin[2]).addScaledVector(v3Dir(), -500); }
}

async function v3PlaceAt(id, name, world, yaw){
  if (!await needProject()) return;
  const ck = cellKeyAt(world[0], world[1]);
  // without a preview: face the camera, turned to whole 15° steps
  if (yaw === undefined) yaw = Math.round((V3.yaw + Math.PI) / (Math.PI / 12)) * (Math.PI / 12);
  if (typeof rememberRecent === 'function') rememberRecent(id, name);
  const m = await refAction('/api/ref/place', {cell: ck, id, p: [world[0], world[1], world[2], 0, 0, yaw], surface: true}, ck, null, 'Placed ' + (name || id));
  if (m && m.placed) selectRef(ck, m.placed);
}

// ----- moving and turning with the handles -----
function v3ApplyMode(){
  const tc = V3.tc; if (!tc) return;
  tc.setMode(V3.mode);
  tc.showX = tc.showY = V3.mode === 'translate' || V3.tilt;
  tc.showZ = true;
  tc.setTranslationSnap(V3.grid || null);
  tc.setRotationSnap(V3.angle ? V3.angle * Math.PI / 180 : null);
}

function v3DragStart(){
  if (V3.tc.object === V3.pivot && W.multi.size > 1){
    // a whole group: remember where every member started, relative to the handles
    const members = [...W.multi.values()].map(m => V3.objs.get(m.cell + '|' + m.k)).filter(Boolean);
    V3.drag = {group: true, members: members.map(o => ({o, pos: o.g.position.clone(), q: o.g.quaternion.clone()})),
               start: V3.pivot.position.clone(), startRot: V3.pivot.rotation.z};
    return;
  }
  const sk = W.sel && W.sel.cell + '|' + W.sel.k, o = sk && V3.objs.get(sk);
  if (!o) return;
  const T = THREE, own = new T.Box3().setFromObject(o.g);
  const near = [];
  for (const [key, x] of V3.objs){
    if (key === sk || !x.r) continue;
    if (x.g.position.distanceTo(o.g.position) > 3000) continue;
    const b = new T.Box3().setFromObject(x.g);
    if (!b.isEmpty()) near.push(b);
  }
  V3.drag = {key: sk, o, rel: own.clone().translate(o.g.position.clone().negate()), near,
             start: o.g.position.clone(), startRot: o.g.rotation.clone()};
}

// "Snap pieces together": while moving, line the edges up with nearby pieces
function v3Snap(){
  const D = V3.drag; if (!D) return;
  if (D.group){
    // move/turn every member with the handles (turning around the group's middle)
    const d = V3.pivot.position.clone().sub(D.start), a = V3.pivot.rotation.z - D.startRot, c = Math.cos(a), s = Math.sin(a);
    for (const m of D.members){
      const ox = m.pos.x - D.start.x, oy = m.pos.y - D.start.y;
      m.o.g.position.set(D.start.x + d.x + ox * c - oy * s, D.start.y + d.y + ox * s + oy * c, m.pos.z + d.z);
      // (turned about the world's up axis on top of its own turn; a tilted thing keeps its tilt)
      m.o.g.quaternion.copy(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), a).multiply(m.q));
      m.o.g.updateMatrixWorld(true);
    }
    for (const bh of V3.multiBoxes || []) bh.update();
    return;
  }
  V3.selBox.setFromObject(D.o.g);
  if (!V3.pieces || V3.mode !== 'translate') return;
  const g = D.o.g, box = D.rel.clone().translate(g.position), thr = 18;
  const best = {x: null, y: null, z: null};
  for (const nb of D.near){
    for (const a of ['x', 'y', 'z']){
      const others = ['x', 'y', 'z'].filter(v => v !== a);
      // only pieces beside this one (overlapping, or nearly, on the other two axes)
      if (!others.every(v => box.min[v] < nb.max[v] + thr && box.max[v] > nb.min[v] - thr)) continue;
      for (const d of [nb.min[a] - box.max[a], nb.max[a] - box.min[a], nb.min[a] - box.min[a], nb.max[a] - box.max[a]]){
        if (Math.abs(d) < thr && (best[a] === null || Math.abs(d) < Math.abs(best[a]))) best[a] = d;
      }
    }
  }
  for (const a of ['x', 'y', 'z']) if (best[a] !== null && Math.abs(best[a]) > 0.01) g.position[a] += best[a];
  V3.selBox.setFromObject(g);
}

async function v3DragEnd(){
  const D = V3.drag; V3.drag = null;
  if (!D) return;
  if (D.group){
    if (V3.pivot.position.distanceTo(D.start) < 0.05 && Math.abs(V3.pivot.rotation.z - D.startRot) < 1e-4) return;
    if (!await needProject()){ v3Refresh(); return; }
    const moves = D.members.map(m => {
      const r = m.o.r, p = r.p.slice(), e = new THREE.Euler().setFromQuaternion(m.o.g.quaternion, 'XYZ');
      p[0] = m.o.g.position.x + V3.origin[0]; p[1] = m.o.g.position.y + V3.origin[1]; p[2] = m.o.g.position.z + V3.origin[2];
      p[3] = -e.x; p[4] = -e.y; p[5] = ((-e.z) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI);
      return {cell: m.o.ck, ref: r.k, p};
    });
    await groupAction('/api/group/move', {moves}, `${V3.mode === 'rotate' ? 'Turned' : 'Moved'} ${moves.length} objects`);
    return;
  }
  const g = D.o.g;
  if (g.position.distanceTo(D.start) < 0.05 && Math.abs(g.rotation.z - D.startRot.z) < 1e-4 &&
      Math.abs(g.rotation.x - D.startRot.x) < 1e-4 && Math.abs(g.rotation.y - D.startRot.y) < 1e-4) return;
  // "Land on surfaces": moved over a table, a shelf or the floor, it comes to rest on top of it
  if (V3.rest && V3.mode === 'translate'){ const dz = v3RestDz(D.o, D.key, true); if (dz != null) g.position.z += dz; }
  await v3Commit(D.o, g);
}

// how far down (or up) an object must go to sit on what's below it; from its top (after a move,
// so it lands on a table it was moved over) or from just above its bottom (End)
function v3RestDz(o, sk, fromTop){
  const T = THREE, box = new T.Box3().setFromObject(o.g), c = box.getCenter(new T.Vector3());
  V3.ray.set(new T.Vector3(c.x, c.y, (fromTop ? box.max.z : box.min.z) + 2), new T.Vector3(0, 0, -1));
  const skip = new Set([sk, ...[...W.multi.values()].map(m => m.cell + '|' + m.k)]);
  const hits = V3.ray.intersectObjects([V3.root, V3.ground], true).filter(h => {
    let x = h.object; while (x && !x.userData.ref && !x.userData.ground) x = x.parent;
    return x && !skip.has(x.userData.ref);
  });
  return hits.length ? hits[0].point.z - box.min.z : null;
}

async function v3Commit(o, g){
  if (!await needProject()){ v3Refresh(); return; }
  const r = o.r, p = r.p.slice(), e = new THREE.Euler().setFromQuaternion(g.quaternion, 'XYZ');
  p[0] = g.position.x + V3.origin[0]; p[1] = g.position.y + V3.origin[1]; p[2] = g.position.z + V3.origin[2];
  p[3] = -e.x; p[4] = -e.y; p[5] = ((-e.z) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI);
  r.p = p;
  await refAction('/api/ref/move', {cell: o.ck, ref: r.k, p}, o.ck, r.k, (V3.mode === 'rotate' ? 'Turned ' : 'Moved ') + (r.name || r.id));
}

// Set the selected object down on whatever is below it (End key)
async function v3DropToFloor(){
  const sk = W.sel && W.sel.cell + '|' + W.sel.k, o = sk && V3.objs.get(sk);
  if (!o) return toast('Select something first.', true);
  const dz = v3RestDz(o, sk, false);
  if (dz == null) return toast('There is nothing below it to set it down on.', true);
  o.g.position.z += dz;
  await v3Commit(o, o.g);
}

// ----- toolbar -----
function v3Tools(){
  const t = $('#v3tools'); if (!t) return;
  const opt = (vals, cur, fmt) => vals.map(v => `<option value="${v}" ${v === cur ? 'selected' : ''}>${fmt(v)}</option>`).join('');
  // (in groups you can drag about by their grip: see toolbar.js)
  const grip = typeof tbGrip === 'function' ? tbGrip() : '';
  t.innerHTML = `<div class="v3grp" data-grp="move">${grip}<button class="btn sm ${V3.mode === 'translate' ? 'primary' : ''}" data-v3="translate" title="Move (G)">✥ Move</button>
    <button class="btn sm ${V3.mode === 'rotate' ? 'primary' : ''}" data-v3="rotate" title="Turn (R)">⟳ Turn</button></div>
    <div class="v3grp" data-grp="steps">${grip}<label title="Move in steps">Grid <select id="v3grid">${opt([0, 8, 16, 32, 64, 128, 256], V3.grid, v => v ? v : 'off')}</select></label>
    <label title="Turn in steps">Angle <select id="v3angle">${opt([0, 5, 15, 45, 90], V3.angle, v => v ? v + '°' : 'off')}</select></label></div>
    <div class="v3grp" data-grp="snap">${grip}<label title="When moving, line up with the edges of nearby walls, floors and pieces"><input type="checkbox" id="v3pieces" ${V3.pieces ? 'checked' : ''}> Snap pieces</label>
    <label title="Also tilt forwards/sideways when turning"><input type="checkbox" id="v3tilt" ${V3.tilt ? 'checked' : ''}> Tilt</label>
    <label title="After a move, let it come to rest on what's below: the floor, a table, a shelf"><input type="checkbox" id="v3rest" ${V3.rest ? 'checked' : ''}> Land on surfaces</label>
    <button class="btn sm" data-v3="floor" title="Set the selected object down on what is below it (End)">⤓ Drop down</button></div>
    <div class="v3grp" data-grp="look">${grip}${W.ext ? `<button class="btn sm ${V3.landOpen ? 'primary' : ''}" data-v3="land" title="Shape and paint the ground">⛰ Ground</button>` : ''}
    <button class="btn sm ${v3LightMode() === 'game' ? 'primary' : ''}" data-v3="light" title="${v3LightMode() === 'game' ? 'Showing light as in game (lamps, candles, fog). Click for bright, even light for editing.' : 'Showing bright, even light for editing. Click to see it as in game.'}">${v3LightMode() === 'game' ? '💡 Game light' : '☀ Bright'}</button>
    <span class="v3viewwrap"><button class="btn sm ${V3.viewOpen ? 'primary' : ''}" data-v3="view" title="Grid, cell borders, wireframe, what to show, and how far you can see">👁 View ▾</button>
      <div class="v3viewmenu" style="display:${V3.viewOpen ? 'block' : 'none'}">
        <label title="Lines at the move grid's spacing (128 when the grid is off), at the selected object's base or where you look"><input type="checkbox" data-v3v="grid" ${V3.view.grid ? 'checked' : ''}> Grid <span class="msg">(${V3.grid || 128})</span></label>
        ${W.ext ? `<label title="Where one cell ends and the next begins"><input type="checkbox" data-v3v="cells" ${V3.view.cells ? 'checked' : ''}> Cell borders</label>` : ''}
        <label title="Show the triangles that make up models and the ground"><input type="checkbox" data-v3v="wire" ${V3.view.wire ? 'checked' : ''}> Wireframe</label>
        <label title="How wide the view is: narrow like a camera lens, or wide to take a whole room in (the game's own is about 75)" style="display:block;margin-top:6px">Field of view <b id="v3fovv">${V3.fov || 60}°</b>
          <input type="range" id="v3fov" min="40" max="110" step="5" value="${V3.fov || 60}" style="width:100%"></label>
        ${W.ext ? `<label><input type="checkbox" data-v3v="ground" ${V3.view.ground ? 'checked' : ''}> Ground</label>
        <label><input type="checkbox" data-v3v="water" ${V3.view.water ? 'checked' : ''}> Water</label>
        <label title="How far you can see outdoors: the cells loaded round the camera. Further is slower in towns."
          style="display:block;margin-top:6px">View distance <b id="v3distv">${V3_DISTS[v3Dist()]}</b>
          <input type="range" id="v3dist" min="1" max="4" step="1" value="${v3Dist()}" style="width:100%"></label>` : ''}
      </div></span>
    <button class="btn sm" data-v3="home" title="Back to the start view">◎</button>
    <button class="btn sm" data-v3="help" title="Controls">?</button></div>`;
  if (typeof tbApply === 'function') tbApply();
  t.querySelectorAll('[data-v3]').forEach(b => b.onclick = () => {
    const a = b.dataset.v3;
    if (a === 'translate' || a === 'rotate'){ V3.mode = a; v3ApplyMode(); v3Tools(); }
    else if (a === 'floor') v3DropToFloor();
    else if (a === 'land') v3LandToggle(!V3.landOpen);
    else if (a === 'light'){ V3.lightMode = v3LightMode() === 'game' ? 'bright' : 'game'; try { localStorage.setItem('ws-light', V3.lightMode); } catch (e) {} v3ApplyLighting(); v3Tools(); }
    else if (a === 'home') v3Home();
    else if (a === 'help') $('#v3help').style.display = $('#v3help').style.display === 'none' ? 'block' : 'none';
    else if (a === 'view'){ V3.viewOpen = !V3.viewOpen; v3Tools(); }
  });
  t.querySelectorAll('[data-v3v]').forEach(c => c.onchange = () => {
    V3.view[c.dataset.v3v] = c.checked;
    try { localStorage.setItem('ws-v3view', JSON.stringify(V3.view)); } catch (e) {}
    v3ApplyView();
  });
  const vd = $('#v3dist');
  if (vd){ vd.oninput = () => { $('#v3distv').textContent = V3_DISTS[+vd.value]; }; vd.onchange = () => v3SetDist(+vd.value); }
  const vf = $('#v3fov');
  if (vf) vf.oninput = () => { V3.fov = +vf.value; $('#v3fovv').textContent = V3.fov + '°'; if (V3.camera){ V3.camera.fov = V3.fov; V3.camera.updateProjectionMatrix(); } try { localStorage.setItem('ws-fov', String(V3.fov)); } catch (e) {} };
  $('#v3grid').onchange = e => { V3.grid = +e.target.value; v3ApplyMode(); v3Tools(); V3.gridFor = null; };
  $('#v3angle').onchange = e => { V3.angle = +e.target.value; v3ApplyMode(); };
  $('#v3pieces').onchange = e => { V3.pieces = e.target.checked; };
  $('#v3tilt').onchange = e => { V3.tilt = e.target.checked; v3ApplyMode(); };
  $('#v3rest').onchange = e => { V3.rest = e.target.checked; try { localStorage.setItem('ws-rest', V3.rest ? '1' : '0'); } catch (x) {} };
}

// ----- the View menu: grid, cell borders, wireframe, ground and water
function v3ApplyView(){
  if (!V3.scene) return;
  const wire = !!V3.view.wire;
  const setWire = o => {
    if (!o.isMesh || o === V3.water || o === V3.marker) return;
    for (const m of Array.isArray(o.material) ? o.material : [o.material]) if (m && m.wireframe !== wire){ m.wireframe = wire; m.needsUpdate = true; }
  };
  V3.root.traverse(setWire); V3.ground.traverse(setWire);
  if (V3.grassGroup) V3.grassGroup.traverse(setWire);
  for (const m of Object.values(V3.mats)) m.wireframe = wire;          // (things not built yet)
  V3.wireFor = wire + '|' + V3.objs.size;
  V3.ground.visible = !W.ext || V3.view.ground !== false;
  if (V3.water) V3.water.visible = W.ext && V3.view.water !== false;
  if (V3.gridGroup) V3.gridGroup.visible = false;                    // (placed again by v3GridTick)
}
// lines that ignore depth so they can be seen through the ground and floors, faintly
function v3GridLines(size, div, color, opacity){
  const g = new THREE.GridHelper(size, div, color, color);
  g.rotation.x = Math.PI / 2;                                          // (GridHelper lies in x-z; our up is z)
  for (const m of Array.isArray(g.material) ? g.material : [g.material]){ m.depthTest = false; m.transparent = true; m.opacity = opacity; }
  g.renderOrder = 5;
  return g;
}
function v3GridTick(t){
  if (!V3.view.grid && !(V3.view.cells && W.ext)){ if (V3.gridGroup) V3.gridGroup.visible = false; return; }
  if (t - (V3.gridT || 0) < 200) return;
  V3.gridT = t;
  const T = THREE, step = V3.grid || 128;
  if (!V3.gridGroup){ V3.gridGroup = new T.Group(); V3.scene.add(V3.gridGroup); }
  if (V3.gridFor !== step){
    V3.gridFor = step;
    for (const c of [...V3.gridGroup.children]){ V3.gridGroup.remove(c); c.geometry.dispose(); }
    V3.fine = v3GridLines(step * 64, 64, 0xf0cd87, 0.18); V3.gridGroup.add(V3.fine);
    V3.borders = v3GridLines(CELL * 6, 6, 0xffb347, 0.85); V3.gridGroup.add(V3.borders);
  }
  // where: the selected object's base, else what the middle of the view is looking at
  let at = null;
  const sel = V3.tc && V3.tc.object;
  if (sel){ const b = new T.Box3().setFromObject(sel); at = new T.Vector3((b.min.x + b.max.x) / 2, (b.min.y + b.max.y) / 2, b.min.z); }
  else {
    V3.ray.setFromCamera(new T.Vector2(0, 0), V3.camera);
    const h = V3.ray.intersectObjects(W.ext ? [V3.ground] : [V3.root], true)[0];
    at = h ? h.point : V3.pos.clone().add(v3Dir().multiplyScalar(800));
  }
  const snap = (v, o, s) => Math.round((v + o) / s) * s - o;            // grid lines on world multiples
  V3.gridGroup.visible = true;
  V3.fine.visible = !!V3.view.grid;
  V3.fine.position.set(snap(at.x, V3.origin[0], step), snap(at.y, V3.origin[1], step), at.z + 1);
  V3.borders.visible = !!(V3.view.cells && W.ext);
  V3.borders.position.set(snap(at.x, V3.origin[0], CELL), snap(at.y, V3.origin[1], CELL), at.z + 2);
}

// ----- drawing -----
let v3Last = 0, v3CellCheck = 0;
function v3Loop(){
  if (V3.looping) return;
  V3.looping = true;
  const step = t => {
    if (!V3.on || !$('#world').classList.contains('on')){ V3.looping = false; return; }
    const dt = Math.min(0.1, (t - (v3Last || t)) / 1000); v3Last = t;
    // fly with WASD (Q/E down/up, Shift faster)
    const sp = (V3.keys.shift ? 2600 : 700) * dt, d = v3Dir(), flat = new THREE.Vector3(d.x, d.y, 0).normalize(),
          right = new THREE.Vector3(flat.y, -flat.x, 0);
    if (V3.keys.w) V3.pos.addScaledVector(d, sp);
    if (V3.keys.s) V3.pos.addScaledVector(d, -sp);
    if (V3.keys.d) V3.pos.addScaledVector(right, sp);
    if (V3.keys.a) V3.pos.addScaledVector(right, -sp);
    if (V3.keys.e) V3.pos.z += sp;
    if (V3.keys.q) V3.pos.z -= sp;
    V3.camera.position.copy(V3.pos);
    V3.camera.lookAt(V3.pos.clone().add(d));
    V3.water.position.set(V3.pos.x, V3.pos.y, -V3.origin[2]);
    if (V3.selBox.visible && V3.tc.object) V3.selBox.setFromObject(V3.tc.object);
    v3GridTick(t);
    // things built since wireframe was switched on follow it
    if (V3.view.wire && V3.wireFor !== true + '|' + V3.objs.size && t - (V3.wireT || 0) > 1000){ V3.wireT = t; v3ApplyView(); }
    v3LightsTick(t);
    v3WeatherTick(dt, t);
    if (typeof pe3DTick === 'function'){ pe3DTick(); v3Paths(); }
    if (t - (V3.lightPickT || 0) > 500){ V3.lightPickT = t; v3PointLightsPick(); }
    // holding the brush still keeps raising / lowering / smoothing
    if (V3.stroke && V3.strokeEv && V3.land.tool !== 'paint' && V3.land.tool !== 'scatter' && t - V3.stroke.last > 50){
      V3.stroke.last = t; const at = v3Brush(V3.strokeEv); v3StrokeAt(at, V3.strokeEv); v3BrushRing(at);
    }
    // your character, when the game is linked
    const pl = LINK.player, here = pl && LINK.connected && (W.ext ? pl.kind === 'ext' : pl.cell === W.key);
    V3.marker.visible = !!here;
    if (here){ V3.marker.position.set(pl.x - V3.origin[0], pl.y - V3.origin[1], pl.z - V3.origin[2] + 150); V3.marker.rotation.set(0, 0, -pl.yaw); }
    // outdoors: load what's around as you fly
    if (W.ext && t - v3CellCheck > 600){
      v3CellCheck = t;
      const [x, y] = v3CamWorld();
      if (cellKeyAt(x, y) !== W.key || Math.hypot(x - W.cam.x, y - W.cam.y) > CELL){ W.cam.x = x; W.cam.y = y; recentre(); }
      v3Terrain();
    }
    V3.renderer.render(V3.scene, V3.camera);
    requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
