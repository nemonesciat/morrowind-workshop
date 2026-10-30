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
function v3Tex(path, cb, fail, fresh){
  // (fresh: fetched again past every cache, after the file was changed in a picture editor)
  const T = THREE, url = '/api/file?path=' + encodeURIComponent(path), get = fresh ? url + '&v=' + Date.now() : url;
  if (fresh){ delete texCache[url]; delete TEX_Q.pending[url]; }
  if (texCache[url]){ cb(texCache[url]); return; }
  if (TEX_Q.pending[url]){ TEX_Q.pending[url].push([cb, fail]); return; }
  TEX_Q.pending[url] = [[cb, fail]];
  const settle = (ok, tex) => { const list = TEX_Q.pending[url] || []; delete TEX_Q.pending[url]; TEX_Q.active--; v3TexNext();
                                for (const [c, f] of list){ if (ok) c(tex); else if (f) f(); } };
  const loader = path.endsWith('.dds') ? new T.DDSLoader() : path.endsWith('.tga') ? new T.TGALoader() : new T.TextureLoader();
  const attempt = (again) => loader.load(get, tex => {
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
// models drawn again after their file changed (a model back from Blender: assets.js)
function v3ModelReload(ids){
  for (const id of ids || []){ const k = String(id).toLowerCase(); delete V3.models[k]; V3.asked.delete(k); }
  if (typeof v3Refresh === 'function') v3Refresh();
}
// a texture drawn again, everywhere it shows, after it was changed (the asset window: assets.js)
function v3TexReload(path){
  if (typeof THREE === 'undefined' || !path) return;
  const mats = Object.entries(V3.mats).filter(([k]) => k.startsWith(path + '|')).map(([, m]) => m);
  if (!mats.length) return;
  v3Tex(path, t => { for (const m of mats){ m.map = t; m.color.setHex(0xffffff); m.needsUpdate = true; } }, null, true);
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
  tc.setSpace('world'); tc.size = 0.9;          // (V3_HANDLE: v3HandleSize keeps it from growing past the thing)
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
    V3.scene.background = new T.Color(typeof thView3d === 'function' ? thView3d() : 0x0d0c0a);
    V3.scene.fog = null;
    V3.hemi.intensity = 0.75; V3.sun.intensity = 0.35; V3.amb.intensity = 0.45;
  }
  V3.water.visible = v3WaterLevel() != null && V3.view.water !== false;
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
  // (not before the place's own info is here: v3Reset needs it for the camera, and marking the place as set up
  // without one left the 3D view with no camera, "reading 'x'")
  if (!W.key || !W.info) return;
  // a new place was opened (flying into the next cell outdoors keeps the view)
  if (!V3.homeFor || (!W.ext && V3.homeFor !== W.key) || W.ext !== V3.homeFor.startsWith('#')) v3Reset();
  V3.homeFor = W.key;
  if (!V3.pos) return;
  const want = new Map();
  for (const [ck, r] of visibleRefs()) want.set(ck + '|' + r.k, [ck, r]);
  for (const [key, o] of V3.objs) if (!want.has(key)){ V3.root.remove(o.g); V3.objs.delete(key); }
  const need = [];
  // (what's being dragged now, one thing or a whole group, stays where the mouse has it: a redraw mid-drag,
  // such as the reload after the last drop coming back late, put a group's members back where they were
  // saved, and a drop just then saved them there: the "snap back"; and it isn't rebuilt until the drop)
  const dragging = new Set();
  if (V3.drag){ if (V3.drag.group) for (const m of V3.drag.members) dragging.add(m.o.g.userData.ref); else dragging.add(V3.drag.key); }
  for (const [key, [ck, r]] of want){
    const id = r.id.toLowerCase();
    if (!(id in V3.models) && !V3.asked.has(id) && r.type !== 'LEVC') need.push(r.id);      // (people too: their bodies)
    const look = id + '|' + (id in V3.models ? 1 : 0);
    let o = V3.objs.get(key);
    if (!o || (o.look !== look && !dragging.has(key))){
      if (o) V3.root.remove(o.g);
      o = {g: v3Build(r), look, ck, k: r.k};
      o.g.userData.ref = key;
      V3.root.add(o.g); V3.objs.set(key, o);
    }
    o.ck = ck; o.r = r;
    // (physics on: where the physics has it, not where it was saved; physics.js)
    if (!dragging.has(key) && !(typeof PH !== 'undefined' && PH.on && PH.bodies.has(key))) v3Place(o.g, r);
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
      const c = box.getCenter(new THREE.Vector3()), sz = box.getSize(new THREE.Vector3());
      V3.pivot.position.set(c.x, c.y, box.min.z); V3.pivot.rotation.set(0, 0, 0); V3.pivot.updateMatrixWorld();
      V3.pivotR = Math.max(sz.x, sz.y, sz.z) / 2 || 32;      // (the group's size, for v3HandleSize: the pivot holds nothing)
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
    if (!W.ext){ V3.scene.background = new T.Color(typeof thView3d === 'function' ? thView3d() : 0x0d0c0a); V3.scene.fog = null; V3.hemi.intensity = 0.75; V3.sun.intensity = 0.35; V3.amb.intensity = 0.45;
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
// ----- the time of day: the game's own colours for each weather at sunrise, by day, at sunset and by
// night (openmw.cfg's fallback=Weather_... lines, from Morrowind.ini), blended through the hours as the
// game does: night until sunrise, to the sunrise colours half way through it, to day at its end; the same
// through sunset back to night. V3.hour: null for the plain preview, else 0-24.
const V3_KINDS = ['Clear', 'Cloudy', 'Foggy', 'Overcast', 'Rain', 'Thunderstorm', 'Ashstorm', 'Blight', 'Snow', 'Blizzard'];
async function v3Daylight(){
  if (V3.day || V3.dayAsked) return V3.day;
  V3.dayAsked = true;
  try { V3.day = await api('/api/daylight'); } catch (e){ V3.dayAsked = false; }
  return V3.day;
}
function v3DayAt(kind, h){
  const D = V3.day, K = D.kinds[kind] || D.kinds.Clear;
  // (keys: hour, which of sunrise/day/sunset/night, how much daylight)
  const keys = [[D.sunrise, 3, 0], [D.sunrise + D.sunrise_len / 2, 0, 0.55], [D.sunrise + D.sunrise_len, 1, 1],
                [D.sunset, 1, 1], [D.sunset + D.sunset_len / 2, 2, 0.55], [D.sunset + D.sunset_len, 3, 0]];
  let a = keys[0], b = keys[0], t = 0;
  if (h >= keys[0][0] && h < keys[5][0]){
    for (let i = 0; i < 5; i++) if (h >= keys[i][0] && h < keys[i + 1][0]){ a = keys[i]; b = keys[i + 1]; t = (h - a[0]) / Math.max(0.001, b[0] - a[0]); break; }
  }
  const mix = part => { const p = K[part][a[1]], q = K[part][b[1]]; return new THREE.Color((p[0] + (q[0] - p[0]) * t) / 255, (p[1] + (q[1] - p[1]) * t) / 255, (p[2] + (q[2] - p[2]) * t) / 255); };
  return {sky: mix('Sky'), fog: mix('Fog'), amb: mix('Ambient'), sun: mix('Sun'), light: a[2] + (b[2] - a[2]) * t};
}
function v3HourLabel(h){
  if (h == null) return 'Plain daylight';
  const hh = Math.floor(h) % 24, mm = Math.round((h - Math.floor(h)) * 60);
  const D = V3.day || {sunrise: 6, sunrise_len: 2, sunset: 18, sunset_len: 2};
  const part = h < D.sunrise || h >= D.sunset + D.sunset_len ? 'night' : h < D.sunrise + D.sunrise_len ? 'sunrise' : h < D.sunset ? 'day' : 'sunset';
  return `${String(hh).padStart(2, '0')}:${String(mm).padStart(2, '0')} · ${part}`;
}
const V3_RAIN_LEN = 70;          // (a raindrop's streak, in game units)
function v3ApplyWeather(){
  if (!V3.scene || !W.ext) return;
  const T = THREE, w = V3_WEATHER[V3.weather == null ? 0 : V3.weather];
  // (the fog moves out with the View distance, so the far cells fade in rather than stop at an edge;
  // on Near it is as it always was)
  const k = v3Dist() === 1 ? 1 : (v3Dist() + 0.6) / 1.6;
  const far = Math.max(40000, w.fog[1] * k * 1.1);
  if (V3.camera.far !== far){ V3.camera.far = far; V3.camera.updateProjectionMatrix(); }
  if (V3.hour != null && V3.day){
    const d = v3DayAt(V3_KINDS[V3.weather == null ? 0 : V3.weather], V3.hour);
    V3.scene.background = d.sky;
    V3.scene.fog = new T.Fog(d.fog, w.fog[0] * k, w.fog[1] * k);
    V3.amb.color.copy(d.amb); V3.amb.intensity = 1.0;
    V3.hemi.color.copy(d.sky); V3.hemi.groundColor.copy(d.amb); V3.hemi.intensity = 0.15 + 0.2 * d.light;
    // (the sun from the east at sunrise, overhead at noon, to the west at sunset; by night the moon,
    // dim, from the other side)
    const D = V3.day, span = (D.sunset + D.sunset_len / 2) - (D.sunrise + D.sunrise_len / 2);
    let a = Math.PI * (V3.hour - (D.sunrise + D.sunrise_len / 2)) / Math.max(1, span);
    V3.skyArc = a;                                       // (the sky's sun and moons: v3SkyApply)
    const night = a < 0 || a > Math.PI;
    if (night) a = ((a % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI) - Math.PI;
    V3.sun.position.set(Math.cos(a), -0.35, Math.max(0.15, Math.sin(a)) * 1.5);
    V3.sun.color.copy(d.sun); V3.sun.intensity = night ? 0.35 : (0.35 + 0.65 * d.light) * (w.sun / 0.75 * 0.6 + 0.4);
    // (lamps, candles and torches count for more as the light goes)
    if (V3.pool && v3LightMode() === 'game'){ V3.poolStrength = 0.6 + 0.8 * (1 - d.light); v3PointLightsPick(); }
  } else {
    V3.scene.background = new T.Color(w.sky);
    V3.scene.fog = new T.Fog(w.sky, w.fog[0] * k, w.fog[1] * k);
    V3.amb.color.set(0xffffff); V3.amb.intensity = 0.2;
    V3.hemi.groundColor.set(0x50453a);
    V3.sun.position.set(0.6, -0.8, 1.5);
    V3.sun.intensity = w.sun; V3.hemi.intensity = w.hemi;
    V3.sun.color.set(w.tint || 0xfff0d8); V3.hemi.color.set(w.tint || 0xfff4e0);
  }
  V3.hemiBase = V3.hemi.intensity;
  v3SkyApply();
  // falling things: one set of points that follows the camera
  if (V3.fall){ V3.scene.remove(V3.fall); V3.fall.geometry.dispose(); V3.fall.material.dispose(); V3.fall = null; }
  if (!w.fall) return;
  const kind = w.fall, n = kind === 'blizzard' ? 9000 : kind === 'rain' ? 6000 : 4000, B = 2400;
  const col = {rain: 0x9ab0c8, snow: 0xffffff, blizzard: 0xffffff, ash: 0x6a5040, blight: 0x9a4a40}[kind];
  if (kind === 'rain'){
    // (rain as thin streaks, each drop a short line along its fall: drawn as dots it read as sleet)
    const pos = new Float32Array(n * 6);
    for (let i = 0; i < n; i++){
      const x = (Math.random() - 0.5) * B * 2, y = (Math.random() - 0.5) * B * 2, z = (Math.random() - 0.3) * B;
      pos.set([x, y, z, x - 2, y - 1, z - V3_RAIN_LEN], i * 6);
    }
    const geo = new T.BufferGeometry(); geo.setAttribute('position', new T.BufferAttribute(pos, 3));
    const mat = new T.LineBasicMaterial({color: col, transparent: true, opacity: 0.45, depthWrite: false, fog: true});
    V3.fall = new T.LineSegments(geo, mat); V3.fall.frustumCulled = false; V3.fall.userData = {kind, B, lines: true};
    V3.scene.add(V3.fall);
    return;
  }
  const pos = new Float32Array(n * 3);
  for (let i = 0; i < n; i++){ pos[i * 3] = (Math.random() - 0.5) * B * 2; pos[i * 3 + 1] = (Math.random() - 0.5) * B * 2; pos[i * 3 + 2] = (Math.random() - 0.3) * B; }
  const geo = new T.BufferGeometry(); geo.setAttribute('position', new T.BufferAttribute(pos, 3));
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
  if (F.userData.lines){
    // (each streak's two ends move together, wrapped round the camera as one)
    for (let i = 0; i < p.length; i += 6){
      const dx = side * (0.6 + 0.4 * sway), dy = side * 0.3;
      p[i + 2] -= down; p[i + 5] -= down; p[i] += dx; p[i + 3] += dx; p[i + 1] += dy; p[i + 4] += dy;
      if (p[i + 2] < -B * 0.3){ p[i + 2] += B; p[i + 5] += B; }
      if (p[i] > B){ p[i] -= B * 2; p[i + 3] -= B * 2; }
      if (p[i + 1] > B){ p[i + 1] -= B * 2; p[i + 4] -= B * 2; }
    }
  } else
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
    V3.hemi.intensity = (V3.hemiBase != null ? V3.hemiBase : w.hemi) + f * 1.2;
  }
}
// ----- the sky outdoors, from the game's own: the cloud dome (meshes\sky_clouds_01.nif) with each weather's
// cloud picture (fallback=Weather_..._Cloud_Texture) drifting at its cloud speed, the stars of sky_night_01.nif,
// the sun and the two moons, over air that goes from the sky's colour overhead to the fog's at the horizon (what
// sky_atmosphere.nif's vertex colours do). Its own little scene, drawn first round a camera that only turns, so
// it is always behind everything and costs a few hundred triangles. Without the game's sky: the plain colour.
function v3SkyLoad(){
  if (V3.skyAsked) return;
  V3.skyAsked = true;
  Promise.all([api('/api/sky'), v3Daylight()]).then(([d]) => {
    if (!d || d.error || !d.dome) return;
    V3.skyData = d; v3SkyBuild(); v3SkyApply();
  }).catch(() => {});
}
function v3SkyShapes(shapes, mat){
  const T = THREE, g = new T.Group();
  for (const s of shapes || []){
    const geo = new T.BufferGeometry();
    geo.setAttribute('position', new T.Float32BufferAttribute(s.p, 3));
    if (s.uv && s.uv.length) geo.setAttribute('uv', new T.Float32BufferAttribute(s.uv, 2));
    geo.setIndex(s.i);
    const m = mat(s); g.add(new T.Mesh(geo, m));
  }
  return g;
}
function v3SkyBuild(){
  const T = THREE, D = V3.skyData;
  const S = V3.sky = {scene: new T.Scene(), cam: new T.PerspectiveCamera(60, 1, 10, 20000), off: 0, kind: null,
                      top: new T.Color(), horizon: new T.Color(), tint: new T.Color(1, 1, 1), speed: 1};
  S.cam.up.set(0, 0, 1);
  const flat = {depthWrite: false, depthTest: false, fog: false};
  S.atm = new T.Mesh(new T.SphereGeometry(4000, 32, 16), new T.ShaderMaterial(Object.assign({side: T.BackSide,
    uniforms: {top: {value: S.top}, horizon: {value: S.horizon}},
    vertexShader: 'varying vec3 vP; void main(){ vP = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
    fragmentShader: 'uniform vec3 top, horizon; varying vec3 vP; void main(){ gl_FragColor = vec4(mix(horizon, top, smoothstep(0.0, 0.45, normalize(vP).z)), 1.0); }'}, flat)));
  S.atm.renderOrder = 0; S.scene.add(S.atm);
  // (the stars, each picture added on: they are white on black)
  S.starMats = [];
  S.night = v3SkyShapes(D.night, s => {
    const m = new T.MeshBasicMaterial(Object.assign({color: 0x000000, transparent: true, blending: T.AdditiveBlending, side: T.DoubleSide}, flat));
    if (s.tex) v3Tex(s.tex, t => { m.map = t; m.needsUpdate = true; });
    S.starMats.push(m); return m;
  });
  S.night.renderOrder = 1; S.night.traverse(o => { o.renderOrder = 1; }); S.night.visible = false; S.scene.add(S.night);
  // the sun with its glow, and Masser and Secunda (sized as Moons_..._Size has them, against each other)
  const sprite = (path, size, add, order) => {
    const m = new T.SpriteMaterial(Object.assign({color: 0xffffff, transparent: true, opacity: 0, blending: add ? T.AdditiveBlending : T.NormalBlending}, flat));
    const sp = new T.Sprite(m); sp.scale.set(size, size, 1); sp.renderOrder = order; sp.visible = false;
    if (path) v3Tex(path, t => { m.map = t; m.needsUpdate = true; sp.userData.ok = true; });
    S.scene.add(sp); return sp;
  };
  S.masser = sprite(D.masser, 3600 * 0.3 * (D.masser_size || 94) / 94, false, 2);
  S.secunda = sprite(D.secunda, 3600 * 0.3 * (D.secunda_size || 40) / 94, false, 2);
  S.sun = sprite(D.sun, 3600 * 0.2, true, 3);
  // the clouds: the picture's own see-through parts, fading out towards the dome's rim, tinted with the
  // fog's colour as the game does
  S.cloudU = {map: {value: null}, tint: {value: S.tint}, off: {value: 0}, fade: {value: 1}, lo: {value: 0}, hi: {value: 1}};
  S.clouds = v3SkyShapes(D.dome, () => new T.ShaderMaterial(Object.assign({transparent: true, side: T.DoubleSide, uniforms: S.cloudU,
    vertexShader: 'varying vec2 vUv; varying float vZ; void main(){ vUv = uv; vZ = position.z; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
    fragmentShader: 'uniform sampler2D map; uniform vec3 tint; uniform float off, fade, lo, hi; varying vec2 vUv; varying float vZ;\n' +
      'void main(){ vec4 c = texture2D(map, vUv + vec2(0.0, off)); gl_FragColor = vec4(c.rgb * tint, c.a * fade * smoothstep(lo, hi, vZ)); }'}, flat)));
  // (the rim: the lowest third of the dome, which the game fades out with its vertex alpha)
  let zl = 1e9, zh = -1e9;
  for (const s of D.dome) for (let i = 2; i < s.p.length; i += 3){ zl = Math.min(zl, s.p[i]); zh = Math.max(zh, s.p[i]); }
  S.cloudU.lo.value = zl; S.cloudU.hi.value = zl + (zh - zl) * 0.35;
  S.clouds.traverse(o => { o.renderOrder = 4; }); S.clouds.scale.set(3, 3, 3); S.clouds.visible = false; S.scene.add(S.clouds);
  S.night.scale.set(1.8, 1.8, 1.8);
}
// the sky's colours, clouds and sun for the weather and hour now (from v3ApplyWeather)
function v3SkyApply(){
  if (!W.ext) return;
  if (!V3.skyData){ v3SkyLoad(); return; }
  const S = V3.sky; if (!S) return;
  const T = THREE, D = V3.skyData, wi = V3.weather == null ? 0 : V3.weather, kind = V3_KINDS[wi], K = D.kinds[kind] || {};
  const rgb = a => new T.Color(a[0] / 255, a[1] / 255, a[2] / 255);
  S.horizon.copy(V3.scene.fog ? V3.scene.fog.color : V3.scene.background);
  const timed = V3.hour != null && V3.day, G = V3.day && (V3.day.kinds[kind] || V3.day.kinds.Clear);
  let light = 1, sun;
  if (timed){
    const d = v3DayAt(kind, V3.hour);
    S.top.copy(d.sky); S.tint.copy(d.fog); light = d.light;
    const a = V3.skyArc != null ? V3.skyArc : Math.PI / 2;
    sun = new T.Vector3(Math.cos(a), -0.35, Math.sin(a)).normalize();
  } else {
    // (the plain preview: the game's day colours, the sun where the plain light comes from)
    S.top.copy(G ? rgb(G.Sky[1]) : new T.Color(V3_WEATHER[wi].sky).multiplyScalar(0.85));
    S.tint.copy(G ? rgb(G.Fog[1]) : new T.Color(1, 1, 1));
    sun = new T.Vector3(0.6, -0.8, 1.5).normalize();
  }
  // clouds: this weather's picture
  S.speed = K.speed || 1;
  if (K.clouds !== S.kind){
    S.kind = K.clouds; S.clouds.visible = false;
    if (K.clouds) v3Tex(K.clouds, t => { if (S.kind !== K.clouds) return; S.cloudU.map.value = t; S.clouds.visible = true; });
  }
  // the sun: through clear skies (Glare_View), redder towards sunset (Sun_Disc_Sunset_Color)
  const glare = K.glare != null ? K.glare : 1, low = Math.min(1, Math.max(0, (1 - light) * 1.6));
  S.sun.position.copy(sun).multiplyScalar(3600);
  S.sun.material.color.setRGB(1, 1, 1).lerp(rgb(K.disc || [255, 255, 255]), low);
  S.sun.material.opacity = glare * Math.min(1, Math.max(0, (sun.z + 0.03) / 0.1));
  // the night: stars and moons as the light goes
  const night = timed ? Math.min(1, Math.max(0, (0.55 - light) / 0.55)) : 0;
  S.night.visible = night > 0.01;
  for (const m of S.starMats) m.color.setScalar(night);
  const n = V3.skyArc != null ? ((V3.skyArc - Math.PI) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI) : 0;
  const moon = (sp, a, tilt) => {
    const v = new T.Vector3(Math.cos(a), tilt, Math.sin(a)).normalize();
    sp.position.copy(v).multiplyScalar(3600);
    sp.material.opacity = night * Math.min(1, Math.max(0, v.z / 0.1));
  };
  moon(S.masser, n * 0.85 + 0.2, 0.7);
  moon(S.secunda, n * 0.8 + 0.45, 1.2);
}
// each frame: the sky turns with the camera and the clouds drift (OpenMW: speed × 0.003 of the picture a second)
function v3SkyTick(dt){
  const S = V3.sky; if (!S) return false;
  S.off = (S.off + dt * S.speed * 0.003) % 1;
  S.cloudU.off.value = S.off;
  // (a sun or moon shows once its picture is here: a sprite without one is a white square)
  for (const sp of [S.sun, S.masser, S.secunda]) sp.visible = !!sp.userData.ok && sp.material.opacity > 0.01;
  S.cam.quaternion.copy(V3.camera.quaternion);
  if (S.cam.fov !== V3.camera.fov || S.cam.aspect !== V3.camera.aspect){ S.cam.fov = V3.camera.fov; S.cam.aspect = V3.camera.aspect; S.cam.updateProjectionMatrix(); }
  return true;
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
  // (bright where nothing is in front of them, faint behind rock and walls: drawn all bright through
  // everything, the paths in the tunnel behind seemed to cross the rock, the user's "through walls")
  V3.pathObj = new THREE.Group();
  const seen = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({color: 0x7fd0ff, transparent: true, opacity: 0.95}));
  const behind = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({color: 0x7fd0ff, depthTest: false, transparent: true, opacity: 0.16}));
  seen.renderOrder = 11; behind.renderOrder = 10;
  V3.pathObj.add(behind, seen);
  V3.pathObj.geometry = geo;
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

// a see-through preview of pieces at fixed spots in the world (Fix here: what the game would stand at a
// joint, shown while the mouse is over the menu entry), apart from the placing ghost
function v3GhostAt(items){
  v3GhostClear();
  if (!V3.scene || !items || !items.length) return;
  const T = THREE, g = new T.Group();
  V3.fixGhost = g; V3.scene.add(g);
  v3EnsureModels([...new Set(items.map(it => it.id))]).then(() => {
    if (V3.fixGhost !== g) return;
    for (const it of items){
      const m = V3.models[it.id.toLowerCase()], part = new T.Group();
      const src = m && m.parts.length ? m.parts.map(p => new T.Mesh(p.geo, p.mat)) : v3Build({id: it.id, type: 'STAT', b: null}).children;
      for (const mesh of src){
        const mat = mesh.material.clone(); mat.transparent = true; mat.opacity = 0.6; mat.depthWrite = false;
        if (mesh.material.map) mat.map = mesh.material.map;
        mat.emissive = new T.Color(0x332200);
        part.add(new T.Mesh(mesh.geometry, mat));
      }
      const p = it.p || [0, 0, 0, 0, 0, 0];
      part.position.set(p[0] - V3.origin[0], p[1] - V3.origin[1], p[2] - V3.origin[2]);
      part.rotation.set(-(p[3] || 0), -(p[4] || 0), -(p[5] || 0), 'XYZ');
      part.scale.setScalar(it.s || 1);
      g.add(part);
    }
    v3Refresh();
  });
}
function v3GhostClear(){
  if (V3.fixGhost){ if (V3.scene) V3.scene.remove(V3.fixGhost); V3.fixGhost = null; if (V3.on) v3Refresh(); }
}

function v3GhostMove(e){
  const G = V3.ghost; if (!G) return null;
  const h = v3Pick(e, true);
  if (!h || !h.world || !G.ready){ G.g.visible = false; G.hit = null; return null; }
  G.hit = h.world;
  G.g.position.set(h.point.x, h.point.y, h.point.z - G.minZ);
  G.g.rotation.set(0, 0, -G.yaw);
  // (a building from the prefab workbench or Plan a prefab: shown as it will stand, on the lowest ground under its
  // ground floor, so the preview on the land is what the click puts down; prefabplan.js pfGroundZ)
  const P = W.groupPlace;
  if (P && (P.bench || P.prefab || P.outside) && W.ext && typeof pfGroundZ === 'function'){
    const z = pfGroundZ(P.items, h.world[0], h.world[1], G.yaw, h.world[2]);
    G.hit = [h.world[0], h.world[1], z];
    G.g.position.z = z - V3.origin[2];
  }
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
    // (each load numbered: one asked before an Undo dropped the ground came back after the new ask, laid the old
    // heights down, and the new mesh then went on beside it, so the undone ground stayed drawn)
    const n = V3.landN = (V3.landN || 0) + 1;
    V3.lands[k] = {loading: true, n};
    api(`/api/land?gx=${gx}&gy=${gy}&tex=1`).then(L => {
      if (!V3.lands[k] || V3.lands[k].n !== n) return;
      V3.lands[k] = {loading: false, gx, gy, n};
      if (L.exists){
        // the ground textures by name, so painting can add new ones: slot list + one slot number per patch
        L.paths = L.tex.slice(); L.ids = L.t.map(i => L.paths[i]); L.origId = L.tid || L.t.map(() => '');
        V3.lands[k].L = L; V3.lands[k].mesh = v3LandMesh(gx, gy, L); V3.ground.add(V3.lands[k].mesh);
        v3LandNeighbours(gx, gy);                    // their edges now blend into this one
      }
    }).catch(() => { if (V3.lands[k] && V3.lands[k].n === n) delete V3.lands[k]; });
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
// (a stroke only starts once the mouse has been dragged a few pixels or held a moment: a plain click on the
// ground, to select something or pick a spot, changed nothing then, but did; and it only goes on while the
// mouse is over the view and the camera stays put. 2026-10-27: Caldera's square came out a hill in the
// Workshop, nothing like the game, after clicks and a held stroke while flying)
const V3_ARM_PX = 5, V3_ARM_MS = 350;
function v3StrokeArm(e){
  const S_ = V3.stroke; if (!S_ || S_.armed) return !!S_;
  if (Math.hypot(e.clientX - S_.x0, e.clientY - S_.y0) < V3_ARM_PX && performance.now() - S_.t0 < V3_ARM_MS) return false;
  S_.armed = true;
  const first = S_.first; S_.first = null;
  if (S_.scatter) v3ScatterDab(first.at, first.ctrl); else v3StrokeAt(first.at, first.e);
  return true;
}
function v3StrokeStart(e){
  const at = v3Brush(e); if (!at) return false;
  const arm = {armed: false, x0: e.clientX, y0: e.clientY, t0: performance.now(), cam: V3.pos.clone(), first: {at, e, ctrl: e.ctrlKey}};
  if (V3.land.tool === 'scatter'){
    // what already stands around counts as taken
    const near = [];
    for (const c of Object.values(W.cells)) for (const r of c.refs || []) if (Math.hypot(r.p[0] - at[0], r.p[1] - at[1]) < 6000 && !r.arch) near.push([r.p[0], r.p[1]]);
    const grass = V3.land.scatSet === 'grass' && V3.land.scatGrass !== false;
    if (grass) for (const lst of Object.values(V3.grassData || {})) for (const g of lst) if (Math.hypot(g[1] - at[0], g[2] - at[1]) < 6000) near.push([g[1], g[2]]);
    V3.stroke = Object.assign({cells: new Map(), scatter: true, grass, circles: [], add: [], gone: new Map(), near, last: 0, lastAt: at, erase: e.ctrlKey}, arm);
    return true;
  }
  V3.stroke = Object.assign({cells: new Map(), level: v3GroundAt(at[0], at[1]), last: 0}, arm);
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
    if (tool === 'tint'){
      // the land's own colour at each point, mixed towards the brush's colour (Ctrl: back towards plain)
      const cb = v3LandCols(L), col = c.mesh.geometry.attributes.color;
      const want = e.ctrlKey ? [255, 255, 255] : v3Hex(B.tint || '#b4a078');
      let any = false;
      for (let y = 0; y <= 64; y++) for (let x = 0; x <= 64; x++){
        const d = Math.hypot(ox + x * 128 - at[0], oy + y * 128 - at[1]); if (d >= R) continue;
        const w = Math.min(1, fall(d) * k * 0.3), v = y * 65 + x;
        for (let i = 0; i < 3; i++) cb[v * 3 + i] = Math.round(cb[v * 3 + i] + (want[i] - cb[v * 3 + i]) * w);
        col.setXYZ(v, cb[v * 3] / 255, cb[v * 3 + 1] / 255, cb[v * 3 + 2] / 255);
        any = true;
      }
      if (any){ col.needsUpdate = true; v3StrokeMark(ck, 'c'); }
      continue;
    }
    if (tool === 'paint' && B.texAuto){
      // Auto: each patch the texture the region's land has at its slope, height and shore (roads kept), worked
      // out for the cell by the server once (landshapes.texture_only); a cell still coming paints on the next dab
      const A = v3AutoTex(c.gx, c.gy);
      if (!A) continue;
      let any = false;
      for (let py = 0; py < 16; py++) for (let px = 0; px < 16; px++){
        const i = py * 16 + px, d = Math.hypot(ox + (px + 0.5) * 512 - at[0], oy + (py + 0.5) * 512 - at[1]);
        if (d <= Math.max(R, 260) && A.paths[i] && L.ids[i] !== A.paths[i]){ L.ids[i] = A.paths[i]; (L.texIds = L.texIds || {})[A.paths[i]] = A.ids[i]; any = true; }
      }
      if (any){ v3StrokeMark(ck, 't'); v3LandMaterial(c.mesh, L); v3LandNeighbours(c.gx, c.gy); }
      continue;
    }
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
    const brushed = [];
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
      brushed.push(v);
      any = true;
    }
    // (no step between neighbouring points over what the land record holds, 127 steps of 8 units: the save eased
    // a steeper one on its own, so the game had other ground than the Workshop showed, and each cell eased apart
    // from the next. Raised again and again on one spot, a small brush made them; only brushed points move)
    if (tool === 'raise' || tool === 'lower'){
      const MAXSTEP = 1000;
      for (let pass = 0; pass < 3; pass++) for (const v of brushed){
        const x = v % 65, y = (v - x) / 65;
        for (const [i, j] of [[1, 0], [-1, 0], [0, 1], [0, -1]]){
          if (x + i < 0 || x + i > 64 || y + j < 0 || y + j > 64) continue;
          const nv = H[(y + j) * 65 + x + i];
          if (H[v] > nv + MAXSTEP) H[v] = nv + MAXSTEP; else if (H[v] < nv - MAXSTEP) H[v] = nv - MAXSTEP;
        }
      }
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
    // (and the corner point it shares with the cell across the diagonal, which the sides above don't reach: after
    // Smooth, where four cells met, the fourth could keep its own corner and leave a crack)
    for (const [dx, dy] of [[1, 1], [-1, 1], [1, -1], [-1, -1]]){
      const nb = V3.lands[(c.gx + dx) + ',' + (c.gy + dy)]; if (!nb || !nb.L) continue;
      const mine = (dy === 1 ? 64 : 0) * 65 + (dx === 1 ? 64 : 0), theirs = (dy === 1 ? 0 : 64) * 65 + (dx === 1 ? 0 : 64);
      if (nb.L.h[theirs] !== L.h[mine]){ nb.L.h[theirs] = L.h[mine]; v3StrokeMark((c.gx + dx) + ',' + (c.gy + dy), 'h'); }
    }
  }
  for (const ck of S_.cells.keys()){
    const c = V3.lands[ck]; if (!c || !c.mesh || !S_.cells.get(ck).h) continue;
    v3LandHeights(c.mesh, c.L); v3LandNormals(c.mesh, c.L);
  }
}
// a cell's vertex colours as bytes to paint into (plain white where the game gave it none)
function v3LandCols(L){
  if (!L.cb){
    L.cb = new Uint8Array(65 * 65 * 3).fill(255);
    if (L.c){ const s = atob(L.c); for (let i = 0; i < L.cb.length && i < s.length; i++) L.cb[i] = s.charCodeAt(i); }
  }
  return L.cb;
}
function v3Hex(h){ const n = parseInt((h || '#ffffff').slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
function v3B64(bytes){ let s = ''; for (let i = 0; i < bytes.length; i += 8192) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 8192)); return btoa(s); }
// Shift+click with the tint brush: the colour the ground has there
function v3TintEyedrop(at){
  const gx = Math.floor(at[0] / CELL), gy = Math.floor(at[1] / CELL), c = V3.lands[gx + ',' + gy]; if (!c || !c.L) return;
  const x = Math.round((at[0] - gx * CELL) / 128), y = Math.round((at[1] - gy * CELL) / 128), cb = v3LandCols(c.L), v = (y * 65 + x) * 3;
  V3.land.tint = '#' + [cb[v], cb[v + 1], cb[v + 2]].map(n => n.toString(16).padStart(2, '0')).join('');
  v3LandSave(); v3LandPanel();
}
function v3StrokeMark(ck, what){ const m = V3.stroke.cells.get(ck) || {}; m[what] = true; V3.stroke.cells.set(ck, m); }
// a cell's automatic textures for the Auto paint, asked for once (null while on its way)
function v3AutoTex(gx, gy){
  const k = gx + ',' + gy, M = V3.autoTex = V3.autoTex || {};
  if (M[k] === undefined){
    M[k] = null;
    api('/api/land/autotex?' + new URLSearchParams({gx, gy})).then(r => { M[k] = r && r.paths && r.paths.length === 256 ? r : false; })
      .catch(() => { delete M[k]; });
  }
  return M[k] || null;
}
async function v3StrokeEnd(){
  const S_ = V3.stroke; V3.stroke = null;
  if (S_ && S_.scatter) return v3ScatterEnd(S_);
  if (!S_ || !S_.cells.size) return;
  if (!await needProject()){ v3LandsReload(); return; }
  const cells = [];
  for (const [ck, what] of S_.cells){
    const c = V3.lands[ck]; if (!c || !c.L) continue;
    const L = c.L, cell = {gx: c.gx, gy: c.gy};
    if (what.h){ cell.h = L.h.map(v => Math.round(v)); if (V3.autoTex) delete V3.autoTex[ck]; }    // (new slopes: Auto asks again)
    if (what.c) cell.c = v3B64(v3LandCols(L));
    if (what.t){
      // the server wants texture names: ones painted now, or the ones the cell already had
      // (painted with the default ground: its name is '', kept as such, not taken for "unchanged")
      cell.t = L.ids.map((p, i) => L.texIds && Object.prototype.hasOwnProperty.call(L.texIds, p) ? L.texIds[p] : (L.origId[i] || ''));
    }
    cells.push(cell);
  }
  try {
    const r = await post('/api/land/edit', {cells, keep_objects: V3.land.follow !== false});
    const n = cells.length;
    toast((cells.some(c => c.h) ? 'Reshaped the ground' : cells.some(c => c.t) ? 'Painted the ground' : 'Tinted the ground') +
          (n > 1 ? ` in ${n} cells` : '') + (r.moved ? ` (${r.moved} objects followed it)` : '') + '. Ground changes show in game after a restart.');
    W.lands = {};
    if (r.moved) for (const k of Object.keys(W.cells)) if (W.cells[k] && W.cells[k].exists) await worldReloadCell(k);
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
  ['tint', '🎨 Tint', 'Paint the ground\'s own colour, the shading the game multiplies into its textures (Ctrl: back to plain; Shift+click: pick the colour under the mouse). Or shade it automatically, the way the game does.'],
  ['scatter', '🌿 Scatter', 'Scatter grass, plants, rocks or trees of this region (Ctrl: clear them away)']];
// how far apart things of each kind usually grow (at thickness 5)
const V3_SCATTER_GAP = {grass: 110, plants: 200, rocks: 380, trees: 650, logs: 700};
// the most one stroke makes: objects in the mod, and groundcover tufts in its grass file
const V3_SCATTER_MAX = {things: 1500, grass: 15000};
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
// The Ground brush's size bar: logarithmic, each tenth of the bar the same proportion bigger (it was even steps of 64
// from 128 to 4096, the small sizes crowded into its first pixels: the user, 2026-10-30)
const V3_BRUSH = [64, 4096];        // (64: just the land point under the brush, they are 128 apart)
function v3BrushClamp(v){ return Math.max(V3_BRUSH[0], Math.min(V3_BRUSH[1], Math.round(v / 16) * 16)); }
function v3PosSize(t){ return v3BrushClamp(V3_BRUSH[0] * Math.pow(V3_BRUSH[1] / V3_BRUSH[0], t / 1000)); }
function v3SizePos(v){ return Math.round(1000 * Math.log(v3BrushClamp(v) / V3_BRUSH[0]) / Math.log(V3_BRUSH[1] / V3_BRUSH[0])); }
async function v3LandPanel(){
  let p = $('#v3land');
  if (!V3.landOpen || !W.ext){ if (p) p.remove(); return; }
  if (!p){ p = document.createElement('div'); p.id = 'v3land'; $('#v3wrap').appendChild(p); if (typeof cfMovable === 'function') cfMovable(p, '.v3lhead', 'ground'); }
  const B = V3.land;
  p.innerHTML = `<div class="v3lhead"><b>Ground${typeof guideLink === 'function' ? guideLink('shaping-the-land.md', 'The Ground brush', 'How the Ground brush works') : ''}</b><button class="btn sm" data-lt="close" title="Close the ground tools">✕</button></div>
    <div class="v3lrow">${V3_LANDTOOLS.map(([k, l, t]) => `<button class="btn sm ${B.tool === k ? 'primary' : ''}" data-lt="${k}" title="${t}">${l}</button>`).join('')}</div>
    <label class="v3lrow" title="How far the brush reaches, in game units: the land has a point every 128, so 64 moves just the one under it. [ and ] change it">Size <input type="range" id="v3lsize" min="0" max="1000" value="${v3SizePos(B.size)}"><input class="inp v3lnum" id="v3lsizen" type="number" min="${V3_BRUSH[0]}" max="${V3_BRUSH[1]}" step="16" value="${B.size}"></label>
    <label class="v3lrow" style="display:${B.tool === 'scatter' ? 'none' : ''}">Strength <input type="range" id="v3lstr" min="1" max="10" value="${B.strength}"><span>${B.strength}</span></label>
    <label class="v3lrow" title="Things standing on the ground move up and down with it"><input type="checkbox" id="v3lfollow" ${B.follow !== false ? 'checked' : ''}> Objects follow the ground</label>
    <div id="v3ltex" style="display:${B.tool === 'paint' ? 'block' : 'none'}">
      <div class="v3lrow"><button class="btn sm ${B.texAuto ? 'primary' : ''}" id="v3lauto" title="Paint each patch with the texture the region's land has at its slope, height and shore. Roads and paving stay">✨ Auto</button>
        ${B.texAuto ? '<span class="faint">The region\'s texture for each slope</span>' : `<button class="btn sm ${V3.landPick === 'paint' ? 'primary' : ''}" data-lpick="paint" title="Eyedropper: click the ground to paint with its texture (or Shift+click it any time)">💧 Pick</button>`}</div>
      ${B.texAuto ? '' : `<div class="v3lcur">${B.tex ? `<img data-swatch="${esc(B.tex.path)}"> <span>${esc(B.tex.id || 'Default ground')}</span>` : '<span class="faint">Pick a texture below, or from the ground</span>'}</div>
      <input id="v3lq" placeholder="Search textures…" value="${esc(V3.landQ || '')}">
      <div id="v3lgrid"></div>`}
    </div>
    <div id="v3lscat" style="display:${B.tool === 'scatter' ? 'block' : 'none'}"></div>
    <div id="v3ltint" style="display:${B.tool === 'tint' ? 'block' : 'none'}">
      <label class="v3lrow">Colour <input type="color" id="v3lcol" value="${esc(B.tint || '#b4a078')}">
        <button class="btn sm ${V3.landPick === 'tint' ? 'primary' : ''}" data-lpick="tint" title="Eyedropper: click the ground to take its colour (or Shift+click it any time)">💧 Pick</button></label>
      <div class="faint" style="margin:8px 0 4px"><b>Shade automatically</b>, the way the game shades the ground near here:</div>
      <div class="v3lrow"><button class="btn sm" data-shade="seams" title="Darken or tint where two textures meet, by as much as the game does at that pair, so the join doesn't show as a hard edge">Where textures meet</button>
        <button class="btn sm" data-shade="texture" title="Give each texture the tint the game gives it near here (grass, roads, rock...), blended as the textures blend">By texture</button>
        <button class="btn sm" data-shade="hollows" title="Darker in the hollows and gullies, lighter on the crests, by as much as the game's own land is in this region (6 to 14% darker)">Hollows</button></div>
      <div class="v3lrow"><label title="Only the cell under the camera, or it and the eight around it"><input type="checkbox" id="v3lshade9" ${B.shade9 ? 'checked' : ''}> and the cells around</label></div>
      <label class="v3lrow">Amount <input type="range" id="v3lshadek" min="10" max="100" step="5" value="${B.shadeK || 100}"><span>${B.shadeK || 100}%</span></label>
      <div class="faint" id="v3lshadeinfo"></div>
    </div>
    <div class="v3lnote">Drag on the ground to use the brush. Right-drag still looks around. Each stroke can be undone. ${B.tool === 'scatter' ? 'Scattered things show in game after a restart, like other new objects.' : 'Ground changes show in game after a restart.'}</div>`;
  p.querySelectorAll('[data-lt]').forEach(b => b.onclick = () => {
    const a = b.dataset.lt;
    V3.landPick = null;
    if (a === 'close') return v3LandToggle(false);
    B.tool = a; v3LandSave(); v3LandPanel();
  });
  // the eyedropper: the next click on the ground picks (click it again to put it down)
  p.querySelectorAll('[data-lpick]').forEach(b => b.onclick = e => {
    e.preventDefault();
    V3.landPick = V3.landPick === b.dataset.lpick ? null : b.dataset.lpick; v3LandPanel();
  });
  $('#v3lsize').oninput = e => { B.size = v3PosSize(+e.target.value); $('#v3lsizen').value = B.size; v3LandSave(); };
  $('#v3lsizen').onchange = e => { B.size = v3BrushClamp(+e.target.value || B.size); e.target.value = B.size; $('#v3lsize').value = v3SizePos(B.size); v3LandSave(); };
  $('#v3lstr').oninput = e => { B.strength = +e.target.value; e.target.nextElementSibling.textContent = B.strength; v3LandSave(); };
  $('#v3lfollow').onchange = e => { B.follow = e.target.checked; v3LandSave(); };
  if (B.tool === 'paint'){
    $('#v3lauto').onclick = () => { B.texAuto = !B.texAuto; v3LandSave(); v3LandPanel(); };
    if (!B.texAuto){
      if (!V3.landTex) V3.landTex = await api('/api/land/textures');
      const q = $('#v3lq'); q.oninput = () => { V3.landQ = q.value; v3LandGrid(); };
      v3LandGrid();
    }
  }
  if (B.tool === 'scatter') v3ScatterPanel();
  if (B.tool === 'tint') v3TintPanel();
  v3SwatchScan(p);
}
// ----- the tint brush and the automatic shading (landshade.py)
async function v3TintPanel(){
  const B = V3.land;
  $('#v3lcol').oninput = e => { B.tint = e.target.value; v3LandSave(); };
  $('#v3lshade9').onchange = e => { B.shade9 = e.target.checked; v3LandSave(); };
  $('#v3lshadek').oninput = e => { B.shadeK = +e.target.value; e.target.nextElementSibling.textContent = B.shadeK + '%'; v3LandSave(); };
  document.querySelectorAll('[data-shade]').forEach(b => b.onclick = async () => {
    if (!await needProject()) return;
    const [cx, cy] = v3CamCell(), cells = [];
    for (let dx = B.shade9 ? -1 : 0; dx <= (B.shade9 ? 1 : 0); dx++) for (let dy = B.shade9 ? -1 : 0; dy <= (B.shade9 ? 1 : 0); dy++) cells.push([cx + dx, cy + dy]);
    b.disabled = true; toast('Learning how the game shades the ground near here…');
    try {
      const r = await post('/api/land/shade', {cells, mode: b.dataset.shade, strength: (B.shadeK || 100) / 100});
      toast(`Shaded ${r.cells} cell${r.cells === 1 ? '' : 's'} ${b.dataset.shade === 'texture' ? 'by texture' : b.dataset.shade === 'hollows' ? 'darker in the hollows, as the region\'s land is' : 'where textures meet'}${b.dataset.shade === 'hollows' ? '' : `, learnt from ${r.learnt_from} cells of the game nearby`}. Undo takes it back. Ground changes show in game after a restart.`);
      afterChange(); W.lands = {}; v3LandsReload();
    } catch (e){ toast(e.message, true); }
    b.disabled = false;
  });
  // what the game does near here, in a line or two
  const [cx, cy] = v3CamCell(), box = $('#v3lshadeinfo'); if (!box) return;
  const key = cx + ',' + cy;
  if (!V3.shadeInfo || V3.shadeInfo.key !== key){
    box.innerHTML = '<span class="spin"></span>Reading the shading nearby…';
    try { V3.shadeInfo = await api(`/api/land/shadeinfo?gx=${cx}&gy=${cy}`); V3.shadeInfo.key = key; } catch (e){ box.textContent = ''; return; }
  }
  const I = V3.shadeInfo; if (!I.exists || !$('#v3lshadeinfo')) return;
  const sw = rgb => `<span style="display:inline-block;width:12px;height:12px;border:1px solid #0006;vertical-align:-2px;background:rgb(${rgb.join(',')})"></span>`;
  const short = t => esc((t || 'default').replace(/^.*[\\/]/, '').replace(/\.(dds|tga|bmp)$/i, ''));
  const dark = I.seams.filter(s => s.learnt).map(s => Math.round((1 - (s.k[0] + s.k[1] + s.k[2]) / 3) * 100));
  $('#v3lshadeinfo').innerHTML = `Learnt from ${I.cells} cells nearby. ${I.tints.length ? 'Here: ' + I.tints.slice(0, 6).map(t => `${sw(t.rgb)} ${short(t.tex)}`).join(' · ') : ''}
    ${I.seams.length ? `<br>${I.seams.length} kind${I.seams.length === 1 ? '' : 's'} of seam in this cell${dark.length ? `; the game darkens such joins by about ${Math.round(dark.reduce((a, b) => a + b, 0) / dark.length)}%` : ''}.` : '<br>No seams between textures in this cell.'}`;
}
// ----- scattering what grows in the region
async function v3ScatterPanel(){
  const box = $('#v3lscat'); if (!box) return;
  const ck = cellKeyAt(...v3CamWorld().slice(0, 2));
  if (!V3.scatSets || V3.scatSets.cell !== ck){
    box.innerHTML = '<div class="faint"><span class="spin"></span>Finding what grows here…</div>';
    try { V3.scatSets = await api('/api/scatter/sets?cell=' + encodeURIComponent(ck)); V3.scatSets.cell = ck; }
    catch (e){ box.innerHTML = `<div class="faint">${esc(e.message)}</div>`; return; }
    // (the Ground panel was drawn again while the sets came: that newer panel fills its own box; this one is gone
    // from the page, and the brush editor in it found none of its fields, "setting 'onchange'" of null)
    if (!box.isConnected){ v3ScatterPanel(); return; }
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
    <label class="v3lrow" title="How thickly things grow: 5 as the game has this kind, 10 about three times as thick, 1 under half">Thickness <input type="range" id="v3lthick" min="1" max="10" value="${B.scatThick}"><span>${B.scatThick}</span></label>` +
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
  // (a gentle step each way: 10 about three times the game's density, 1 under half. It was (11 - t) / 6 of the
  // gap, so 10 was 36 times as dense, "way too dense", the user 2026-10-28)
  const gap = (V3_SCATTER_GAP[B.scatSet] || (cur && cur.gap) || 200) * Math.pow(0.9, B.scatThick - 5);
  // (never more than V3_SCATTER_MAX a stroke nor 400 spots a dab, and the spacing checked on a grid: at the old
  // Thickness 10 a big brush tried 160,000 spots a dab, each against every one before, and the whole Workshop
  // stopped, PIN2 on Discord 2026-10-28)
  const cap = S_.grass ? V3_SCATTER_MAX.grass : V3_SCATTER_MAX.things;
  if (S_.add.length >= cap){
    if (!S_.capped){ S_.capped = true; toast(`That's as many as one stroke makes (${fmtN(cap)}). Let go and paint again for more.`); }
    return;
  }
  const tries = Math.min(400, Math.max(1, Math.round(Math.PI * R * R / (gap * gap))));
  const cs = Math.max(32, gap * 0.4);
  if (!S_.grid || S_.gridCs !== cs){
    S_.grid = new Map(); S_.gridCs = cs;
    for (const p of S_.near){ const k = Math.floor(p[0] / cs) + ',' + Math.floor(p[1] / cs); (S_.grid.get(k) || S_.grid.set(k, []).get(k)).push(p); }
  }
  const taken = (x, y) => {
    const gx = Math.floor(x / cs), gy = Math.floor(y / cs);
    for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++){
      const l = S_.grid.get((gx + dx) + ',' + (gy + dy));
      if (l && l.some(p => Math.hypot(p[0] - x, p[1] - y) < cs)) return true;
    }
    return false;
  };
  const total = items.reduce((a, i) => a + i.n, 0);
  // in clusters, with the odd one on its own (Project Tamriel's exterior tutorial: "stagger things, don't
  // space them evenly: a cluster of trees there, one by itself there"); not on top of one another
  const disc = () => { const a = Math.random() * Math.PI * 2, d = Math.sqrt(Math.random()) * R; return [at[0] + Math.cos(a) * d, at[1] + Math.sin(a) * d]; };
  const centres = Array.from({length: Math.max(1, Math.round(tries / 4))}, disc);
  for (let t = 0; t < tries; t++){
    let x, y;
    if (Math.random() < 0.2){ [x, y] = disc(); }
    else {
      const c = centres[Math.floor(Math.random() * centres.length)], a = Math.random() * Math.PI * 2;
      const d = Math.abs((Math.random() + Math.random() + Math.random() - 1.5) * gap * 0.9);
      x = c[0] + Math.cos(a) * d; y = c[1] + Math.sin(a) * d;
      if (Math.hypot(x - at[0], y - at[1]) > R) continue;
    }
    const g = v3GroundAt(x, y); if (g == null) continue;
    if (taken(x, y)) continue;
    if (S_.add.length >= cap) break;
    // the game's own mix: things used more often come up more often
    let pick = Math.random() * total, it = items[0];
    for (const i of items){ pick -= i.n; if (pick <= 0){ it = i; break; } }
    const s = it.smin + Math.random() * Math.max(0, it.smax - it.smin);
    // leaning as the game leans this model, as often as it does (scatter.py's tilt and tilt_share)
    const lean = it.tilt && Math.random() < (it.tilt_share || 0) ? it.tilt * Math.PI / 180 : 0;
    const rx = lean ? (Math.random() * 2 - 1) * lean : 0, ry = lean ? (Math.random() * 2 - 1) * lean : 0;
    S_.add.push({id: it.id, lib: it.lib, x, y, z: g - it.sink * s - it.zmin * s, rx, ry, rz: Math.random() * Math.PI * 2, s: Math.round(s * 100) / 100});
    S_.near.push([x, y]);
    const gk = Math.floor(x / cs) + ',' + Math.floor(y / cs); (S_.grid.get(gk) || S_.grid.set(gk, []).get(gk)).push([x, y]);
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
        items: S_.add.map(p => ({id: p.id, lib: p.lib, type: p.lib ? 'STAT' : undefined, dx: p.x - cx, dy: p.y - cy, dz: p.z, rx: p.rx || 0, ry: p.ry || 0, rz: p.rz, s: p.s}))});
      msg = `Scattered ${S_.add.length} ${set ? set.label.toLowerCase() : 'things'}`;
    }
    toast(msg + '. Undo takes the whole stroke back.');
    for (const k of Object.keys(W.cells)) if (W.cells[k] && W.cells[k].exists) await worldReloadCell(k);
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
  // (the game's plain default ground, _land_default, is a texture of its own, the sandy dirt a sea floor mod's land
  // has: it has no name, so it's painted as "none", which the game draws as it. "Pick" refused it, the user 2026-10-29)
  if (path && !id && /_land_default/i.test(path)){ V3.land.tex = {id: '', path}; v3LandSave(); v3LandPanel(); return toast('Painting with the default ground'); }
  if (!path || !id) return toast('Nothing to pick there; pick a texture from the list.', true);
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
      // (Shift+click, or a click with the panel's 💧 Pick on: once, then back to the brush)
      const pick = e.shiftKey || V3.landPick === V3.land.tool;
      if (pick && V3.land.tool === 'paint'){ V3.landPick = null; const at = v3Brush(e); if (at) v3LandEyedrop(at); else v3LandPanel(); return; }
      if (pick && V3.land.tool === 'tint'){ V3.landPick = null; const at = v3Brush(e); if (at) v3TintEyedrop(at); else v3LandPanel(); return; }
      if (V3.land.tool === 'paint' && !V3.land.tex && !V3.land.texAuto){ toast('Pick a ground texture first, or ✨ Auto.'); return; }
      if (V3.land.tool === 'scatter' && !v3ScatterItems().length){ toast('Pick something to scatter first.'); return; }
      if (v3StrokeStart(e)){ drag = {b: 0, x: e.clientX, y: e.clientY, moved: true, stroke: true}; V3.strokeEv = e; V3.over = true; }
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
      if (!v3StrokeArm(e)) return;
      const now = performance.now();
      if (now - V3.stroke.last > 33){ V3.stroke.last = now; V3.stroke.cam = V3.pos.clone(); const at = v3Brush(e); v3StrokeAt(at, e); v3BrushRing(at); }
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
      // (a locked wall or building piece under the mouse: no selection, but the spot and the piece still go
      // to the menu, for "Fix this edge" and "Fix here" on it)
      const h2 = h && h.locked ? v3Pick(e, true) : h;
      V3.lastPick = h2 && h2.point ? h2 : v3Pick(e, true);
      cfMenuAt(e, h && h.obj ? [h.obj.ck, h.obj.r] : null, h2 && h2.world, h && h.locked && h2 && h2.obj ? [h2.obj.ck, h2.obj.r] : null);
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
  // double-click an object: its window (objwin.js); on nothing: look at what's selected
  el.addEventListener('dblclick', e => {
    const h = W.mode ? null : v3Pick(e, false);
    if (h && h.obj && typeof owOpen === 'function'){ owOpen(h.obj.ck, h.obj.k); return; }
    if (W.sel){ const o = V3.objs.get(W.sel.cell + '|' + W.sel.k); if (o) v3FocusObj(o.g); }
  });
  el.addEventListener('mousemove', e => { V3.over = true; v3Hover(e); });
  // (a ground stroke ends where the mouse leaves the view or the window loses focus, and what it did is saved:
  // a release out there was never seen, and the brush went on working by itself)
  const strokeOff = () => { if (drag && drag.stroke){ drag = null; V3.strokeEv = null; v3StrokeEnd(); } };
  el.addEventListener('mouseleave', () => { V3.over = false; $('#maptip').style.display = 'none'; strokeOff(); });
  window.addEventListener('blur', () => { V3.over = false; strokeOff(); });
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
    if (typeof BN !== 'undefined' && BN.open) return;     // (the prefab workbench over the view flies its own camera)
    const k = (e.key || '').toLowerCase(), mv = v3MoveKey(e);
    if (!e.repeat) V3.lastKey = mv || k;           // (the key Windows now repeats: only the last one pressed)
    if (mv && !e.ctrlKey && !e.altKey && !e.metaKey){
      // (a move key tapped twice, the second press within a third of a second of letting go: sprint until it's
      // let go, in any direction: W, A, S, D, Q or E)
      if (!e.repeat && !V3.keys[mv] && performance.now() - ((V3.upAt || {})[mv] || 0) < 320) V3.sprint = mv;
      V3.keys[mv] = true; (V3.keyAt = V3.keyAt || {})[mv] = performance.now(); e.preventDefault();
    }
    if (e.key === 'Shift') V3.keys.shift = true;
    if (e.key === 'Escape') V3.keys = {};
    // (Move/Turn, look at it and set it down are shortcuts you can change: see comfort.js)
    if (e.key === 'Escape' && V3.landOpen) v3LandToggle(false);
    if (V3.landOpen && W.ext && (e.key === '[' || e.key === ']')){
      V3.land.size = v3BrushClamp(V3.land.size * (e.key === ']' ? 1.25 : 0.8)); v3LandSave(); v3LandPanel();
    }
  });
  // letting go of a key always stops it (heard first, before anything else can swallow it)
  window.addEventListener('keyup', e => {
    const mv = v3MoveKey(e); if (mv) V3.keys[mv] = false;
    if (mv){ if (V3.sprint === mv) V3.sprint = false; (V3.upAt = V3.upAt || {})[mv] = performance.now(); }
    const k = (e.key || '').toLowerCase(); if (k.length === 1 && V3.keys[k]) V3.keys[k] = false;     // (a key event with no name: a controller's)
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
    // (the face's way out, for the grid's "Put the grid here": a floor or a wall)
    const normal = h.face ? h.face.normal.clone().transformDirection(h.object.matrixWorld) : null;
    // (a locked building in front of the ground is what's under the mouse, not the ground behind it: outdoors the
    // right-click lost the building there, and with it "Check this building", 2026-10-27)
    if (o.userData.ground) return lockedHit ? {locked: true} : {key: null, point: h.point, world, normal};
    if (o.userData.ref === skipKey) continue;
    const ob = V3.objs.get(o.userData.ref);
    if (!any && ob && ob.r.arch && W.lockArch){ lockedHit = true; continue; }
    return {key: o.userData.ref, obj: ob, point: h.point, world, normal};
  }
  return lockedHit ? {locked: true} : null;
}

function v3Click(e){
  // (Extend mode: a click on an open edge's strip picks it; fixhere/extend.js)
  if (typeof extendPick3D === 'function' && extendPick3D(e, true)) return;
  if (W.mode === 'arrive'){
    const h = v3Pick(e, true);
    if (h && h.obj && h.obj.r && h.obj.r.type === 'DOOR' && typeof arriveDoor === 'function') return arriveDoor(h.obj.ck, h.obj.r.k);
    if (!h || !h.world) return toast('Click on the floor or ground where the player should arrive.');
    // facing the way the camera looks, in whole 15° steps
    const yaw = Math.round(((V3.yaw % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI) / (Math.PI / 12)) * (Math.PI / 12);
    arriveAt(h.world[0], h.world[1], h.world[2] + 10, yaw);
    return;
  }
  if (W.mode === 'place' || W.mode === 'play'){
    const G = W.mode === 'place' && V3.ghost;
    const h = G && G.hit ? {world: G.hit} : v3Pick(e, true);
    if (!h || !h.world) return toast('Click on the ground, a floor or an object.');
    if (W.mode === 'place') v3PlaceAt(W.placeId, W.placeName, h.world, G ? G.yaw : undefined);
    else { setMode(null); playHere({cell: cellKeyAt(h.world[0], h.world[1]), x: h.world[0], y: h.world[1], z: h.world[2] + 60, rz: 0}); }
    return;
  }
  if (W.mode === 'group'){
    const G = V3.ghost;
    // (a prefab planned in its window is pinned by the click, and set down by the window's Place here; prefabplan.js)
    if (W.groupPlace && W.groupPlace.prefab && typeof pfPin === 'function'){ pfPin(); return; }
    // (the prefab workbench's building: put down where the ghost stands on the land; bench.js)
    if (W.groupPlace && W.groupPlace.bench && typeof benchPlaceClick === 'function'){ benchPlaceClick(); return; }
    // (an interior's outside: put down where the ghost stands, its door linked with the interior's; frombuilding.js)
    if (W.groupPlace && W.groupPlace.outside && typeof goPlaceClick === 'function'){ goPlaceClick(); return; }
    const h = G && G.hit ? {world: G.hit} : v3Pick(e, true);
    if (!h || !h.world) return toast('Click on the ground or a floor.');
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
  if (W.mode === 'place' || W.mode === 'group'){ if (!(V3.ghost && V3.ghost.pinned)) v3GhostMove(e); $('#maptip').style.display = 'none'; return; }
  if (v3LandOn() && V3.landOpen){
    if (V3.stroke) return;
    const now = performance.now(); if (now - (V3.hoverT || 0) < 30) return; V3.hoverT = now;
    v3BrushRing(v3Brush(e)); $('#maptip').style.display = 'none'; return;
  }
  const now = performance.now(); if (now - (V3.hoverT || 0) < 60) return; V3.hoverT = now;
  if (typeof extendPick3D === 'function' && extendPick3D(e, false)) return;
  const h = v3Pick(e, true), tip = $('#maptip');
  if (h && h.obj){
    const r = h.obj.r, b = $('#v3wrap').getBoundingClientRect();
    tip.style.display = 'block'; tip.style.left = (e.clientX - b.left + 14) + 'px'; tip.style.top = (e.clientY - b.top + 10) + 'px';
    tip.innerHTML = `<b>${esc(r.name || r.id)}</b> <span style="color:var(--faint)">${esc(S.typeLabels[r.type] || r.type || 'unknown')}</span>${r.to ? ' → ' + esc(r.to.cell || r.to.label || 'outdoors') : ''}`;
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

// the water plane where the place's water is (each frame, and at once when the Sky panel's water changes)
function v3WaterSync(){
  if (!V3.water) return;
  const wl = v3WaterLevel();
  V3.water.visible = wl != null && V3.view.water !== false;
  if (wl != null) V3.water.position.set(V3.pos.x, V3.pos.y, wl - V3.origin[2]);
}
// the water's height in the place open now: outdoors 0; an interior's own (as being edited, else as saved), or null
function v3WaterLevel(){
  if (W.ext) return 0;
  const L = (W.placeEdit && W.info && W.placeEdit.key === W.info.key) ? W.placeEdit : (W.info && W.info.lighting);
  return L && L.water ? (+L.water_height || 0) : null;
}

// ----- moving and turning with the handles -----
function v3ApplyMode(){
  const tc = V3.tc; if (!tc) return;
  tc.setMode(V3.mode);
  // (World axes: east, north and up, whichever way the thing faces; Own axes: its own front, side and up, so a
  // turned bench slides along its length; freeman141 on Nexus: the arrows didn't show the way it would go)
  tc.setSpace(V3.mode === 'scale' ? 'local' : v3Space());
  tc.showX = tc.showY = V3.mode === 'translate' || V3.mode === 'scale' || V3.tilt;
  tc.showZ = true;
  tc.setTranslationSnap(V3.grid || null);
  tc.setRotationSnap(V3.angle ? V3.angle * Math.PI / 180 : null);
}

function v3Space(){
  if (!V3.space){ let s = null; try { s = localStorage.getItem('ws-space'); } catch (e) {} V3.space = s === 'local' ? 'local' : 'world'; }
  return V3.space;
}

function v3DragStart(){
  if (typeof phDragStart === 'function') setTimeout(phDragStart, 0);     // (physics on: what's dragged pushes; physics.js)
  if (V3.tc.object === V3.pivot && W.multi.size > 1){
    // a whole group: remember where every member started, relative to the handles
    const members = [...W.multi.values()].map(m => V3.objs.get(m.cell + '|' + m.k)).filter(Boolean);
    const D = V3.drag = {group: true, members: members.map(o => ({o, pos: o.g.position.clone(), q: o.g.quaternion.clone()})),
                         start: V3.pivot.position.clone(), startRot: V3.pivot.rotation.z};
    if (V3.pieces && V3.mode === 'translate') v3GroupSnapStart(D);
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
  const nearObjs = [];
  for (const [key, x] of V3.objs){
    if (key === sk || !x.r || ['NPC_', 'CREA', 'LEVC'].includes(x.r.type)) continue;
    if (x.g.position.distanceTo(o.g.position) < 3000) nearObjs.push(x);
  }
  V3.drag = {key: sk, o, rel: own.clone().translate(o.g.position.clone().negate()), near, nearObjs,
             start: o.g.position.clone(), startRot: o.g.rotation.clone(), startQ: o.g.quaternion.clone(), startS: o.g.scale.x};
  if (W.ext && V3.pieces && V3.mode === 'translate') v3SnapsFetch(V3.drag);
}

// the spots where the game joins this model to the pieces near it (housemodules.snaps), asked once per drag and again
// after it has been carried 800 units on
async function v3SnapsFetch(D){
  const g = D.o.g, at = g.position.clone();
  D.snapsAt = at;
  try {
    const r = await api('/api/build/snaps?' + new URLSearchParams({id: D.o.r.id, skip: D.o.r.k, x: at.x + V3.origin[0], y: at.y + V3.origin[1], z: at.z + V3.origin[2]}));
    if (V3.drag === D) D.snaps = r.snaps || [];
  } catch (e) {}
}

// A group moved as one snaps as one (the user 2026-10-30: only one piece at a time snapped). Each member is tried
// against the pieces round the group that aren't in it: outdoors the game's joins where the member already stands
// turned the game's way, else flush faces; indoors the group's box on the world's axes. The nearest fix moves them all.
function v3GroupSnapStart(D){
  const T = THREE, keys = new Set(D.members.map(m => m.o.ck + '|' + m.o.r.k));
  const mid = new T.Vector3(); D.members.forEach(m => mid.add(m.pos)); mid.divideScalar(D.members.length || 1);
  D.near = []; D.nearObjs = [];
  for (const [key, x] of V3.objs){
    if (keys.has(key) || !x.r || x.g.position.distanceTo(mid) > 4000) continue;
    const b = new T.Box3().setFromObject(x.g);
    if (!b.isEmpty()) D.near.push(b);
    if (!['NPC_', 'CREA', 'LEVC'].includes(x.r.type)) D.nearObjs.push(x);
  }
  if (!W.ext) return;
  const skip = D.members.map(m => m.o.r.k).join('\n');
  for (const m of D.members.slice(0, 12)){
    const at = m.pos;
    api('/api/build/snaps?' + new URLSearchParams({id: m.o.r.id, skip, x: at.x + V3.origin[0], y: at.y + V3.origin[1], z: at.z + V3.origin[2]}))
      .then(r => { if (V3.drag === D) m.snaps = r.snaps || []; }).catch(() => {});
  }
}
function v3GroupSnap(D){
  const T = THREE;
  if (!W.ext){
    const box = new T.Box3(); D.members.forEach(m => box.union(new T.Box3().setFromObject(m.o.g)));
    const thr = 18, best = {x: null, y: null, z: null};
    for (const nb of D.near) for (const a of ['x', 'y', 'z']){
      const others = ['x', 'y', 'z'].filter(v => v !== a);
      if (!others.every(v => box.min[v] < nb.max[v] + thr && box.max[v] > nb.min[v] - thr)) continue;
      for (const d of [nb.min[a] - box.max[a], nb.max[a] - box.min[a], nb.min[a] - box.min[a], nb.max[a] - box.max[a]])
        if (Math.abs(d) < thr && (best[a] === null || Math.abs(d) < Math.abs(best[a]))) best[a] = d;
    }
    const v = new T.Vector3(best.x || 0, best.y || 0, best.z || 0);
    return v.lengthSq() > 1e-4 ? {v, note: ''} : null;
  }
  // (the game's joins: as v3SnapGame, but only where the member is turned as the join has it, since the group isn't turned)
  let best = null;
  for (const m of D.members){
    const g = m.o.g;
    for (const s of m.snaps || []){
      const dx = s.p[0] - V3.origin[0] - g.position.x, dy = s.p[1] - V3.origin[1] - g.position.y, dz = s.p[2] - V3.origin[2] - g.position.z;
      if (Math.hypot(dx, dy) >= 80 || Math.abs(dz) >= 80) continue;
      const q = new T.Quaternion().setFromEuler(new T.Euler(-s.p[3], -s.p[4], -s.p[5], 'XYZ'));
      if (q.angleTo(g.quaternion) > 0.035) continue;
      const d = Math.hypot(dx, dy) + Math.abs(dz) * 0.5 - 30 * ((s.k || 1) - 1) - 6 * Math.log2(1 + s.n);
      if (!best || d < best.d) best = {d, v: new T.Vector3(dx, dy, dz), note: `${m.o.r.id} joined to ${s.to} the way the game does it (${s.n}×)`};
    }
  }
  if (best) return best;
  // (else flush faces: the member lined up on the most sides, then the smallest nudge)
  for (const m of D.members){
    const g = m.o.g, proxy = {position: g.position.clone(), quaternion: g.quaternion.clone()};
    const n = v3SnapFlush({o: m.o, nearObjs: D.nearObjs}, proxy);
    if (!n) continue;
    const v = proxy.position.sub(g.position), sides = ['x', 'y', 'z'].filter(a => Math.abs(v[a]) > 0.01).length;
    if (!best || sides > best.sides || (sides === best.sides && v.length() < best.v.length())) best = {v, sides, note: `${m.o.r.id} flush with ${n.r.id}`};
  }
  return best;
}

// a made thing's own box (in its own frame, scaled), for the snapping
function v3LocalBox(o){
  if (!o._lbox){
    const b = new THREE.Box3();
    o.g.children.forEach(c => { if (c.geometry){ if (!c.geometry.boundingBox) c.geometry.computeBoundingBox(); b.union(c.geometry.boundingBox); } });
    o._lbox = b;
  }
  const s = o.g.scale;
  return new THREE.Box3(o._lbox.min.clone().multiply(s), o._lbox.max.clone().multiply(s));
}

// 1) the game's own joins: within 80 units of one, the piece stands exactly where (and turned as) the game joins it
function v3SnapGame(D, g){
  if (!D.snaps || !D.snaps.length) return null;
  let best = null;
  for (const s of D.snaps){
    const dx = s.p[0] - V3.origin[0] - g.position.x, dy = s.p[1] - V3.origin[1] - g.position.y, dz = s.p[2] - V3.origin[2] - g.position.z;
    // (nearer is better, and so is a spot the game's way to more neighbours at once (k), or a join it uses often)
    const d = Math.hypot(dx, dy) + Math.abs(dz) * 0.5 - 30 * ((s.k || 1) - 1) - 6 * Math.log2(1 + s.n);
    if (Math.hypot(dx, dy) < 80 && Math.abs(dz) < 80 && (!best || d < best.d)) best = {s, d};
  }
  if (!best) return null;
  const s = best.s;
  g.position.set(s.p[0] - V3.origin[0], s.p[1] - V3.origin[1], s.p[2] - V3.origin[2]);
  g.rotation.set(-s.p[3], -s.p[4], -s.p[5], 'XYZ');
  return s;
}

// 2) flush faces in the neighbour's own frame: beside a piece turned the same way (to a quarter turn), faces meet,
// edges line up and heights match within 18 units, and a turn within 6 degrees of the neighbour's quarter turns is
// made exact. (The old snapping lined boxes up on the world's axes only: nothing beside a building turned 30 degrees.)
function v3SnapFlush(D, g){
  const T = THREE, thr = 18, Ld = v3LocalBox(D.o);
  let best = null;
  for (const n of D.nearObjs){
    const qn = n.g.quaternion, qi = qn.clone().invert();
    const rel = qi.clone().multiply(g.quaternion);
    const e = new T.Euler().setFromQuaternion(rel, 'ZYX');
    if (Math.abs(e.x) > 0.02 || Math.abs(e.y) > 0.02) continue;          // (tilted against it: no faces to meet)
    const quarter = Math.round(e.z / (Math.PI / 2)), off = e.z - quarter * Math.PI / 2;
    if (Math.abs(off) > 6 * Math.PI / 180) continue;
    const qq = new T.Quaternion().setFromAxisAngle(new T.Vector3(0, 0, 1), quarter * Math.PI / 2);
    // (the dragged box in the neighbour's frame, at the exact quarter turn)
    const pn = g.position.clone().sub(n.g.position).applyQuaternion(qi);
    const pts = [];
    for (const x of [Ld.min.x, Ld.max.x]) for (const y of [Ld.min.y, Ld.max.y]) for (const z of [Ld.min.z, Ld.max.z]) pts.push(new T.Vector3(x, y, z).applyQuaternion(qq).add(pn));
    const B = new T.Box3().setFromPoints(pts), N = v3LocalBox(n);
    const dv = new T.Vector3(); let snapped = 0, cost = 0;
    for (const a of ['x', 'y', 'z']){
      const others = ['x', 'y', 'z'].filter(v => v !== a);
      if (!others.every(v => B.min[v] < N.max[v] + thr && B.max[v] > N.min[v] - thr)) continue;
      let pick = null;
      for (const d of [N.min[a] - B.max[a], N.max[a] - B.min[a], N.min[a] - B.min[a], N.max[a] - B.max[a]]) if (Math.abs(d) < thr && (pick === null || Math.abs(d) < Math.abs(pick))) pick = d;
      if (pick !== null){ dv[a] = pick; snapped++; cost += Math.abs(pick); }
    }
    if (!snapped) continue;
    if (!best || snapped > best.snapped || (snapped === best.snapped && cost + Math.abs(off) * 100 < best.cost)) best = {n, dv, qq, qn, snapped, cost: cost + Math.abs(off) * 100};
  }
  if (!best) return null;
  g.quaternion.copy(best.qn.clone().multiply(best.qq));
  g.position.add(best.dv.clone().applyQuaternion(best.qn));
  return best.n;
}

function v3SnapNote(text){
  const t = Date.now();
  if (text === V3.snapNoteText && t - (V3.snapNoteT || 0) < 4000) return;
  V3.snapNoteText = text; V3.snapNoteT = t;
  const el = $('#v3snapnote') || (() => { const d = document.createElement('div'); d.id = 'v3snapnote';
    d.style.cssText = 'position:absolute;left:50%;bottom:44px;transform:translateX(-50%);background:#000b;color:#f0e2bf;padding:4px 10px;border-radius:6px;font-size:12px;pointer-events:none;z-index:5';
    $('#v3wrap').appendChild(d); return d; })();
  el.textContent = text; el.style.display = text ? 'block' : 'none';
}

// "Snap pieces together": while moving, line the edges up with nearby pieces
function v3Snap(){
  const D = V3.drag; if (!D) return;
  if (V3.mode === 'scale' && !D.group && D.o){
    // (the game sizes a thing evenly, ×0.5 to ×2: whichever handle is dragged sizes all three ways, as bench.js)
    const g = D.o.g, s0 = D.startS || 1, v = [g.scale.x, g.scale.y, g.scale.z].reduce((a, b) => Math.abs(b - s0) > Math.abs(a - s0) ? b : a, s0);
    g.scale.setScalar(Math.max(0.5, Math.min(2, +v.toFixed(2))));
    g.updateMatrixWorld(true); if (V3.selBox) V3.selBox.setFromObject(g);
    if (typeof v3SnapNote === 'function') v3SnapNote('×' + g.scale.x.toFixed(2));
    return;
  }
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
    if (D.nearObjs && V3.pieces && V3.mode === 'translate'){
      const fix = v3GroupSnap(D);
      if (fix) for (const m of D.members){ m.o.g.position.add(fix.v); m.o.g.updateMatrixWorld(true); }
      v3SnapNote(fix ? fix.note : '');
    }
    for (const bh of V3.multiBoxes || []) bh.update();
    return;
  }
  V3.selBox.setFromObject(D.o.g);
  if (!V3.pieces || V3.mode !== 'translate') return;
  const g = D.o.g;
  if (W.ext){
    // outdoors: the game's own joins first, then flush faces in the neighbour's frame (the old world-axis lining up
    // below stays for interiors, where the kits stand on the world's axes)
    if (D.snapsAt && g.position.distanceTo(D.snapsAt) > 800) v3SnapsFetch(D);
    const s = v3SnapGame(D, g);
    D.snapped = s;
    if (s){ v3SnapNote(`Joined to ${s.to} the way the game does it (${s.n}×)`); V3.selBox.setFromObject(g); return; }
    if (D.startQ) g.quaternion.copy(D.startQ);         // (off the game's spots: its own turn back)
    const n = v3SnapFlush(D, g);
    v3SnapNote(n ? `Flush with ${n.r.id}` : '');
    V3.selBox.setFromObject(g);
    return;
  }
  const box = D.rel.clone().translate(g.position), thr = 18;
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
  if (typeof v3SnapNote === 'function') v3SnapNote('');
  if (!D) return;
  // (physics on: let go, it falls and rests; nothing is saved until Keep; physics.js)
  if (typeof phDragEnd === 'function' && phDragEnd(D)) return;
  v3Refresh();                      // (anything a redraw left as it was while dragged catches up now)
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
  if (V3.mode === 'scale'){
    if (Math.abs(g.scale.x - (D.startS || 1)) < 0.005) return;
    if (!await needProject()){ v3Refresh(); return; }
    const r = D.o.r, s = +g.scale.x.toFixed(2);
    r.s = s;
    await refAction('/api/ref/move', {cell: D.o.ck, ref: r.k, p: r.p.slice(), s}, D.o.ck, r.k, `Scaled ${r.name || r.id} to ×${s}`);
    return;
  }
  if (g.position.distanceTo(D.start) < 0.05 && Math.abs(g.rotation.z - D.startRot.z) < 1e-4 &&
      Math.abs(g.rotation.x - D.startRot.x) < 1e-4 && Math.abs(g.rotation.y - D.startRot.y) < 1e-4) return;
  // "Land on surfaces": moved over a table, a shelf or the floor, it comes to rest on top of it
  // (a piece snapped to one of the game's joins stands at that join's height: not dropped onto what is below)
  if (V3.rest && V3.mode === 'translate' && !D.snapped){ const dz = v3RestDz(D.o, D.key, true); if (dz != null) g.position.z += dz; }
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
  if (!o) return toast('Select something first.');
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
    <button class="btn sm ${V3.mode === 'rotate' ? 'primary' : ''}" data-v3="rotate" title="Turn (R)">⟳ Turn</button>
    <button class="btn sm ${V3.tilt ? 'primary' : ''}" data-v3="tilt" title="Lean what's selected forwards or sideways">⤡ Tilt</button>
    <button class="btn sm ${V3.mode === 'scale' ? 'primary' : ''}" data-v3="scale" title="Scale handles (3): drag any handle and it grows or shrinks evenly, ×0.5 to ×2, as the game sizes things. Several selected: the Scale dialog">⤢ Scale</button>
    <button class="btn sm" data-v3="space" title="${v3Space() === 'local' ? 'Handles on its own axes: front, side and up as it is turned. Click for the world\'s axes.' : 'Handles on the world\'s axes: east, north and up. Click for its own axes, as it is turned.'}">${V3.space === 'local' ? '⟀ Own axes' : '✛ World axes'}</button></div>
    <div class="v3grp" data-grp="snap">${grip}<span class="v3viewwrap"><button class="btn sm ${V3.snapOpen ? 'primary' : ''}" data-v3="snapmenu" title="Steps for moving and turning, and snapping">⊞ Snap <span class="v3snapnow">${V3.grid || 'off'} · ${V3.angle ? V3.angle + '°' : 'off'}</span> ▾</button>
      <div class="v3viewmenu v3snapmenu" style="display:${V3.snapOpen ? 'block' : 'none'}">
        <label title="Move in steps">Move in steps of <select id="v3grid">${opt([0, 8, 16, 32, 64, 128, 256], V3.grid, v => v ? v : 'off')}</select></label>
        <label title="Turn in steps">Turn in steps of <select id="v3angle">${opt([0, 5, 15, 45, 90], V3.angle, v => v ? v + '°' : 'off')}</select></label>
        <label title="Line up with nearby walls, floors and pieces"><input type="checkbox" id="v3pieces" ${V3.pieces ? 'checked' : ''}> Snap to pieces</label>
        <label title="After a move, rest it on what's below"><input type="checkbox" id="v3rest" ${V3.rest ? 'checked' : ''}> Land on surfaces</label></div></span>
    <button class="btn sm" data-v3="floor" title="Set it down on what's below (End)">⤓ Drop down</button>
    <button class="btn sm ${typeof PH !== 'undefined' && PH.on ? 'primary' : ''}" data-v3="physics" title="Let loose things fall and be pushed; keep the result or put them back">🧲 Physics</button></div>
    <div class="v3grp" data-grp="look">${grip}<button class="btn sm" data-v3="create" title="Make something new: a place, a person, an item, a spell…">✚ Create</button><button class="btn sm" data-v3="style" title="Building pieces, furniture and decor by style">🎨 Style</button>${W.ext ? `<button class="btn sm ${V3.landOpen ? 'primary' : ''}" data-v3="land" title="Shape and paint the ground">⛰ Ground</button>` : ''}
    ${!W.ext ? `<button class="btn sm ${typeof EXM !== 'undefined' && EXM.on ? 'primary' : ''}" data-v3="extend" title="Build out piece by piece from open edges">⬚ Extend</button>` : ''}
    <button class="btn sm ${v3LightMode() === 'game' ? 'primary' : ''}" data-v3="light" title="${v3LightMode() === 'game' ? 'Game lighting. Click for bright, even light.' : 'Bright, even light. Click for game lighting.'}">${v3LightMode() === 'game' ? '💡 Game light' : '☀ Bright'}</button>
    <span class="v3viewwrap"><button class="btn sm ${V3.viewOpen ? 'primary' : ''}" data-v3="view" title="Grid, wireframe, field of view and more">👁 View ▾</button>
      <div class="v3viewmenu" style="display:${V3.viewOpen ? 'block' : 'none'}">
        <label title="Lines at the move step (128 when off)"><input type="checkbox" data-v3v="grid" ${V3.view.grid ? 'checked' : ''}> Grid <span class="msg">(${V3.grid || 128}, bright every ${(V3.grid || 128) * 4})</span></label>
        <div class="v3gridrow" style="display:${V3.view.grid ? 'flex' : 'none'};gap:4px;flex-wrap:wrap;margin:2px 0 4px 20px">
          <button class="btn sm" data-v3="gridsel" title="Grid at the selection's base">📍 At the selection</button>
          <button class="btn sm" data-v3="gridturn" title="Grid at the selection, turned to match it">⟲ Turned to it</button>
          <label style="display:block;width:100%" title="Show the grid through walls and floors"><input type="checkbox" data-v3v="gridThrough" ${V3.view.gridThrough ? 'checked' : ''}> through walls</label>
          <span class="msg" style="width:100%">Or right-click a floor or wall: Put the grid here.</span></div>
        ${W.ext ? `<label title="Where one cell ends and the next begins"><input type="checkbox" data-v3v="cells" ${V3.view.cells ? 'checked' : ''}> Cell borders</label>` : ''}
        <label title="Show the triangles"><input type="checkbox" data-v3v="wire" ${V3.view.wire ? 'checked' : ''}> Wireframe</label>
        <label title="How wide the view is (the game uses about 75°)" style="display:block;margin-top:6px">Field of view <b id="v3fovv">${V3.fov || 60}°</b>
          <input type="range" id="v3fov" min="20" max="150" step="5" value="${V3.fov || 60}" style="width:100%"></label>
        ${W.ext ? `<label><input type="checkbox" data-v3v="ground" ${V3.view.ground ? 'checked' : ''}> Ground</label>
        <label><input type="checkbox" data-v3v="water" ${V3.view.water ? 'checked' : ''}> Water</label>
        <label title="The game's clouds, sun, stars and moons"><input type="checkbox" data-v3v="sky" ${V3.view.sky !== false ? 'checked' : ''}> Sky</label>
        <label title="How many cells load round you; further is slower"
          style="display:block;margin-top:6px">View distance <b id="v3distv">${V3_DISTS[v3Dist()]}</b>
          <input type="range" id="v3dist" min="1" max="4" step="1" value="${v3Dist()}" style="width:100%"></label>` : ''}
      </div></span>
    <button class="btn sm" data-v3="home" title="Back to the start view">◎</button>
    <button class="btn sm" data-v3="help" title="Controls">?</button></div>`;
  if (typeof tbApply === 'function') tbApply();
  t.querySelectorAll('[data-v3]').forEach(b => b.onclick = () => {
    const a = b.dataset.v3;
    if (a === 'translate' || a === 'rotate'){ V3.mode = a; v3ApplyMode(); v3Tools(); }
    // (sizing with the handles, the user 2026-10-29: "Scale" beside Move, Turn and Tilt. A group sizes through
    // the dialog, which scales the spacing too)
    else if (a === 'scale'){ if (W.multi.size > 1 && typeof qolScale === 'function'){ qolScale(); return; } V3.mode = 'scale'; V3.tilt = false; v3ApplyMode(); v3Tools(); }
    else if (a === 'floor') v3DropToFloor();
    else if (a === 'physics' && typeof phToggle === 'function') phToggle(!PH.on);
    else if (a === 'land') v3LandToggle(!V3.landOpen);
    else if (a === 'extend' && typeof extendMode === 'function') extendMode(!EXM.on, W.key);
    else if (a === 'light'){ V3.lightMode = v3LightMode() === 'game' ? 'bright' : 'game'; try { localStorage.setItem('ws-light', V3.lightMode); } catch (e) {} v3ApplyLighting(); v3Tools(); }
    else if (a === 'home') v3Home();
    else if (a === 'help') $('#v3help').style.display = $('#v3help').style.display === 'none' ? 'block' : 'none';
    // (tilting turns: on, the turning handles with their two tilt rings)
    else if (a === 'tilt'){ V3.tilt = !V3.tilt; V3.mode = 'rotate'; v3ApplyMode(); v3Tools(); }
    else if (a === 'space'){ V3.space = V3.space === 'local' ? 'world' : 'local'; try { localStorage.setItem('ws-space', V3.space); } catch (e) {} v3ApplyMode(); v3Tools(); }
    else if (a === 'view'){ V3.viewOpen = !V3.viewOpen; V3.snapOpen = false; v3Tools(); }
    else if (a === 'snapmenu'){ V3.snapOpen = !V3.snapOpen; V3.viewOpen = false; v3Tools(); }
    else if (a === 'gridsel') v3GridToSel(false);
    else if (a === 'gridturn') v3GridToSel(true);
  });
  t.querySelectorAll('[data-v3v]').forEach(c => c.onchange = () => {
    V3.view[c.dataset.v3v] = c.checked;
    try { localStorage.setItem('ws-v3view', JSON.stringify(V3.view)); } catch (e) {}
    if (c.dataset.v3v === 'grid' || c.dataset.v3v === 'gridThrough'){ V3.gridFor = null; const row = t.querySelector('.v3gridrow'); if (row) row.style.display = V3.view.grid ? 'flex' : 'none'; }
    v3ApplyView();
  });
  const vd = $('#v3dist');
  if (vd){ vd.oninput = () => { $('#v3distv').textContent = V3_DISTS[+vd.value]; }; vd.onchange = () => v3SetDist(+vd.value); }
  const vf = $('#v3fov');
  if (vf) vf.oninput = () => { V3.fov = +vf.value; $('#v3fovv').textContent = V3.fov + '°'; if (V3.camera){ V3.camera.fov = V3.fov; V3.camera.updateProjectionMatrix(); } try { localStorage.setItem('ws-fov', String(V3.fov)); } catch (e) {} };
  $('#v3grid').onchange = e => { V3.grid = +e.target.value; v3ApplyMode(); v3Tools(); V3.gridFor = null; };
  $('#v3angle').onchange = e => { V3.angle = +e.target.value; v3ApplyMode(); v3Tools(); };
  $('#v3pieces').onchange = e => { V3.pieces = e.target.checked; };
  $('#v3rest').onchange = e => { V3.rest = e.target.checked; try { localStorage.setItem('ws-rest', V3.rest ? '1' : '0'); } catch (x) {} };
}

// ----- the View menu: grid, cell borders, wireframe, ground, water and sky (the sky is the render loop's: off, the plain colour)
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
  if (V3.water) V3.water.visible = v3WaterLevel() != null && V3.view.water !== false;
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
// The grid is a plane you put somewhere, and it stays there (the user: a grid that hopped to whatever the
// view looked at "hardly seems like it could be useful"). V3.gridAt = {p: a point on it (scene coordinates),
// wall: upright or level, yaw: which way its lines run}. A level grid's lines fall on the game's own
// multiples of the step (the 256 of the building pieces, say) unless turned to an object; it is put where
// the selection stands, or where you right-click ("Put the grid here": a floor gives a level grid, a wall
// an upright one along it). As you move, it only reaches further along its own lines, so it never moves.
function v3GridPlace(p, wall, yaw){
  V3.gridAt = {p: p.clone ? p.clone() : new THREE.Vector3(p[0], p[1], p[2]), wall: !!wall, yaw: yaw || 0, key: W.key};
  V3.gridFor = null;
  if (!V3.view.grid){ V3.view.grid = true; try { localStorage.setItem('ws-v3view', JSON.stringify(V3.view)); } catch (e) {} v3Tools(); }
  V3.gridT = 0;
}
function v3GridHere(pick){
  if (!pick || !pick.point) return toast('Right-click on a floor, the ground or a wall to put the grid there.', true);
  const n = pick.normal || {x: 0, y: 0, z: 1};
  if (Math.abs(n.z) > 0.7) v3GridPlace(pick.point, false, V3.gridAt && !V3.gridAt.wall ? V3.gridAt.yaw : 0);
  else v3GridPlace(pick.point, true, Math.atan2(n.y, n.x));
  toast(V3.gridAt.wall ? 'The grid stands on that wall, its lines along it and upright.' : 'The grid lies level at that height. It stays there until you put it somewhere else.');
}
function v3GridToSel(turn){
  const sel = V3.tc && V3.tc.object;
  if (!sel) return toast('Select something first.');
  const b = new THREE.Box3().setFromObject(sel);
  const r = W.sel && findRef(W.sel.cell, W.sel.k);
  v3GridPlace(new THREE.Vector3((b.min.x + b.max.x) / 2, (b.min.y + b.max.y) / 2, b.min.z), false, turn && r ? -r.p[5] : 0);
}
function v3GridTick(t){
  if (!V3.view.grid && !(V3.view.cells && W.ext)){ if (V3.gridGroup) V3.gridGroup.visible = false; return; }
  if (t - (V3.gridT || 0) < 120) return;
  V3.gridT = t;
  const T = THREE, step = V3.grid || 128;
  if (!V3.gridGroup){ V3.gridGroup = new T.Group(); V3.scene.add(V3.gridGroup); }
  // (first shown: where the selection stands, else where the view looks; once, never again by itself)
  if (!V3.gridAt || V3.gridAt.key !== W.key){
    let at;
    const sel = V3.tc && V3.tc.object;
    if (sel){ const b = new T.Box3().setFromObject(sel); at = new T.Vector3((b.min.x + b.max.x) / 2, (b.min.y + b.max.y) / 2, b.min.z); }
    else {
      V3.ray.setFromCamera(new T.Vector2(0, 0), V3.camera);
      const h = V3.ray.intersectObjects(W.ext ? [V3.ground] : [V3.root], true)[0];
      at = h ? h.point : V3.pos.clone().add(v3Dir().multiplyScalar(800));
    }
    V3.gridAt = {p: at, wall: false, yaw: 0, key: W.key};
    V3.gridFor = null;
  }
  const G = V3.gridAt;
  G.key = W.key;
  const through = !!V3.view.gridThrough;
  // (the bright lines and the cell borders reach as far as the view does; once, they stopped a cell from the camera
  // and the user saw the edge on Very far, 2026-10-27. The faint lines stay near: there are four of them a bright one)
  const big0 = step * 4, reachN = Math.min(400, 2 * Math.ceil((V3.camera.far || 40000) / big0));
  const cellsN = Math.min(40, 2 * Math.ceil((V3.camera.far || 40000) / CELL));
  const sig = step + '|' + G.wall + '|' + G.yaw + '|' + through + '|' + reachN;
  if (V3.gridFor !== sig){
    V3.gridFor = sig;
    for (const c of [...V3.gridGroup.children]){ V3.gridGroup.remove(c); c.traverse(o => o.geometry && o.geometry.dispose()); }
    const mk = (size, div, color, op) => {
      const g = new T.GridHelper(size, div, color, color);
      for (const m of Array.isArray(g.material) ? g.material : [g.material]){ m.depthTest = !through; m.transparent = true; m.opacity = op; }
      g.renderOrder = 5;
      return g;
    };
    // (the step's lines faint, every fourth brighter: distances read at a glance)
    V3.plane = new T.Group();
    const fine = mk(step * 64, 64, 0xf0cd87, 0.16), major = mk(big0 * Math.max(16, reachN), Math.max(16, reachN), 0xf0cd87, 0.42);
    // (GridHelper lies in its own x-z plane: turned up into x-y for a level grid; left upright for a wall)
    for (const g of [fine, major]){ if (!G.wall) g.rotation.x = Math.PI / 2; V3.plane.add(g); }
    V3.plane.rotation.z = G.wall ? G.yaw - Math.PI / 2 : G.yaw;
    V3.fine = V3.plane;
    V3.gridGroup.add(V3.plane);
    V3.borders = v3GridLines(CELL * Math.max(6, cellsN), Math.max(6, cellsN), 0xffb347, 0.85); V3.gridGroup.add(V3.borders);
  }
  // reach out along its own lines to under the camera, a whole number of the bright lines at a time
  const big = step * 4, c = Math.cos(G.yaw), s = Math.sin(G.yaw);
  const cam = V3.camera.position;
  let px = G.p.x, py = G.p.y, pz = G.p.z;
  if (!G.wall){
    // (a level grid that isn't turned: on the game's own multiples of the step)
    if (!G.yaw){ px = Math.round((px + V3.origin[0]) / step) * step - V3.origin[0]; py = Math.round((py + V3.origin[1]) / step) * step - V3.origin[1]; }
    const du = (cam.x - px) * c + (cam.y - py) * s, dv = -(cam.x - px) * s + (cam.y - py) * c;
    const ou = Math.round(du / big) * big, ov = Math.round(dv / big) * big;
    V3.plane.position.set(px + ou * c - ov * s, py + ou * s + ov * c, pz + 1);
  } else {
    const tx = -s, ty = c;                                        // (along the wall)
    const dt = (cam.x - px) * tx + (cam.y - py) * ty, dz = cam.z - pz;
    const ot = Math.round(dt / big) * big, oz = Math.round(dz / big) * big;
    V3.plane.position.set(px + c * 1 + ot * tx, py + s * 1 + ot * ty, pz + oz);
  }
  V3.gridGroup.visible = true;
  V3.plane.visible = !!V3.view.grid;
  const snap = (v, o, s_) => Math.round((v + o) / s_) * s_ - o;
  V3.borders.visible = !!(V3.view.cells && W.ext);
  V3.borders.position.set(snap(cam.x, V3.origin[0], CELL), snap(cam.y, V3.origin[1], CELL), (G.wall ? pz : pz) + 2);
}

// ----- drawing -----
let v3Last = 0, v3CellCheck = 0;
// The move and turn handles keep one size on the screen (TransformControls), so from far off, or with a wide
// field of view, they grew far past the thing they hold: the user's tilt rings round a small thing filled the
// room. Kept on screen as before up close, but never more than a few times the thing's own size in the world.
const V3_HANDLE = 0.9;
function v3HandleSize(){
  const tc = V3.tc, o = tc && tc.object;
  if (!o) return;
  if (o === V3.pivot){
    // (several things selected: the handles sit on an empty pivot, which measured as nothing, so they shrank to
    // 80 units among the group; PIN2's "the axis display shrinks". The group's own size instead)
    V3.handleFor = null;
    V3.handleR = V3.pivotR || 32;
  } else if (V3.handleFor !== o){
    V3.handleFor = o;
    const sz = new THREE.Box3().setFromObject(o).getSize(new THREE.Vector3());
    V3.handleR = Math.max(sz.x, sz.y, sz.z) / 2 || 32;
  }
  const cam = V3.camera, p = o.getWorldPosition(new THREE.Vector3());
  const factor = p.distanceTo(cam.position) * Math.min(1.9 * Math.tan(Math.PI * cam.fov / 360) / cam.zoom, 7);
  // (the handles' world size is factor * size / 7; at most 2.5 times the thing's half size, and never under 40)
  const most = Math.max(40, V3.handleR * 2.5) * 7 / Math.max(1e-6, factor);
  const size = Math.round(Math.min(V3_HANDLE, most) * 100) / 100;
  if (tc.size !== size) tc.size = size;
}

function v3Loop(){
  if (V3.looping) return;
  V3.looping = true;
  const step = t => {
    if (!V3.on || !$('#world').classList.contains('on')){ V3.looping = false; return; }
    const dt = Math.min(0.1, (t - (v3Last || t)) / 1000); v3Last = t;
    // (3D left on from last time and no place open yet: no camera until one opens. Without this the first
    // frame threw, the loop stopped for good, and the place opened next never showed)
    if (!V3.pos){
      if (W.key && W.info && V3.homeFor !== W.key) v3Reset();
      if (!V3.pos){ requestAnimationFrame(step); return; }
    }
    // fly with WASD (Q/E down/up, Shift faster)
    // (a key held down repeats its keydown many times a second; one that hasn't for 0.7 s was let go where
    // the page didn't hear it, a menu or a dialog of the window's own: the camera "that wouldn't stop",
    // the user, still now and then after the blur and Windows-key fixes)
    const now_ = performance.now();
    // (only the key pressed last repeats: W held, then Shift pressed, W's repeats stop and it is still held,
    // the user's "Shift works for a second and then it abruptly stops")
    for (const k of 'wasdqe') if (V3.keys[k] && V3.keyAt && V3.lastKey === k && now_ - (V3.keyAt[k] || 0) > 700) V3.keys[k] = false;
    if (V3.sprint && !V3.keys[V3.sprint]) V3.sprint = false;
    // (a double-tapped move key: three times as fast, every direction alike, until that key is let go)
    const sp = (V3.keys.shift ? 2600 : 700) * (V3.sprint ? 3 : 1) * dt, d = v3Dir(), flat = new THREE.Vector3(d.x, d.y, 0).normalize(),
          right = new THREE.Vector3(flat.y, -flat.x, 0);
    if (V3.keys.w) V3.pos.addScaledVector(d, sp);
    if (V3.keys.s) V3.pos.addScaledVector(d, -sp);
    if (V3.keys.d) V3.pos.addScaledVector(right, sp);
    if (V3.keys.a) V3.pos.addScaledVector(right, -sp);
    if (V3.keys.e) V3.pos.z += sp;
    if (V3.keys.q) V3.pos.z -= sp;
    V3.camera.position.copy(V3.pos);
    V3.camera.lookAt(V3.pos.clone().add(d));
    if (typeof phTick === 'function') phTick(dt);          // (physics on: a step of the world; physics.js)
    // (outdoors the sea at 0; an interior with water at its own height, the one being edited in the Sky panel as
    // you type: interiors drew no water at all, and a flooded cave's level was set blind, the user 2026-10-30)
    v3WaterSync();
    if (V3.selBox.visible && V3.tc.object) V3.selBox.setFromObject(V3.tc.object);
    v3GridTick(t);
    // things built since wireframe was switched on follow it
    if (V3.view.wire && V3.wireFor !== true + '|' + V3.objs.size && t - (V3.wireT || 0) > 1000){ V3.wireT = t; v3ApplyView(); }
    v3LightsTick(t);
    v3WeatherTick(dt, t);
    if (typeof pe3DTick === 'function'){ pe3DTick(); v3Paths(); }
    if (t - (V3.lightPickT || 0) > 500){ V3.lightPickT = t; v3PointLightsPick(); }
    // holding the brush still keeps raising / lowering / smoothing
    // (only over the view, and only while the camera stays where the stroke last was: a brush held while flying
    // with the keys reshaped everything the mouse's spot passed over)
    if (V3.stroke && V3.stroke.first && V3.strokeEv && performance.now() - V3.stroke.t0 >= V3_ARM_MS && V3.over) v3StrokeArm(V3.strokeEv);
    if (V3.stroke && V3.stroke.armed && V3.strokeEv && V3.over && V3.land.tool !== 'paint' && V3.land.tool !== 'scatter' && t - V3.stroke.last > 50
        && V3.stroke.cam && V3.pos.distanceTo(V3.stroke.cam) < 1){
      V3.stroke.last = t; const at = v3Brush(V3.strokeEv); v3StrokeAt(at, V3.strokeEv); v3BrushRing(at);
    }
    // your character, when the game is linked
    const pl = LINK.player, here = pl && LINK.connected && (W.ext ? pl.kind === 'ext' : pl.cell === W.key);
    V3.marker.visible = !!here;
    if (here){ V3.marker.position.set(pl.x - V3.origin[0], pl.y - V3.origin[1], pl.z - V3.origin[2] + 150); V3.marker.rotation.set(0, 0, -pl.yaw); }
    // outdoors: load what's around as you fly
    // (only once the view is set up for this place: just opened from an interior, the camera is still where it was
    // inside, 815, -2759 read as outdoors, and following it took you to cell 0, -1 first; the user, 2026-10-27)
    if (W.ext && V3.homeFor && V3.homeFor.startsWith('#') && t - v3CellCheck > 600){
      v3CellCheck = t;
      const [x, y] = v3CamWorld();
      if (cellKeyAt(x, y) !== W.key || Math.hypot(x - W.cam.x, y - W.cam.y) > CELL){ W.cam.x = x; W.cam.y = y; recentre(); }
      v3Terrain();
    }
    // (outdoors with the game's sky: the sky first, then the place over it; a colour background would
    // clear the sky away again, so the place is drawn without it)
    v3HandleSize();
    const R = V3.renderer;
    if (W.ext && V3.view.sky !== false && v3SkyTick(dt)){
      const bg = V3.scene.background;
      R.autoClear = false; R.clear(); R.render(V3.sky.scene, V3.sky.cam); R.clearDepth();
      V3.scene.background = null; R.render(V3.scene, V3.camera); V3.scene.background = bg; R.autoClear = true;
    } else R.render(V3.scene, V3.camera);
    requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
