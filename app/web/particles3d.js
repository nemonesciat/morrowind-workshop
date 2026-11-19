// Particles in the 3D view: the flames, smoke and sparks of the game's models, run from their own settings
// (partnif.effects on the server, sent with the models as '$fx'). They follow what OpenMW does with the same
// numbers: a box placer of the emitter's size, a cone shooter, a rate that keeps the system full unless the
// model says otherwise, grow and fade, wind and pull at OpenMW's 1.6, colour over a particle's life.
// Drawn in the model's own coordinates, so a placed thing carries its flame.
const PFX = {live: [], max: 24000, near: 6000};

function fxRate(e){ return e.per_second || 0; }

// the controller's time for a moment of the view's clock (OpenMW: frequency, phase, then loop or hold)
function fxTime(e, t){
  const span = Math.max(0, (e.stop || 0) - (e.start || 0));
  let x = t * (e.freq || 1) + (e.phase || 0);
  if (span <= 0) return x;
  const cycle = ((e.flags || 0) >> 1) & 3;
  if (cycle === 2) return Math.min(e.stop, Math.max(e.start, x));
  if (cycle === 1){ const k = ((x - e.start) % (2 * span) + 2 * span) % (2 * span); return e.start + (k < span ? k : 2 * span - k); }
  return e.start + (((x - e.start) % span) + span) % span;
}

function fxMaterial(e){
  const T = THREE, b = e.blend || {};
  const m = new T.ShaderMaterial({
    uniforms: {map: {value: null}, hasMap: {value: 0}, scale: {value: 600}, oscale: {value: 1}, grey: {value: 0}},
    vertexShader: `attribute float psize; attribute vec4 pcolor; varying vec4 vColor; uniform float scale; uniform float oscale;
      void main(){ vColor = pcolor; vec4 mv = modelViewMatrix * vec4(position, 1.0);
        gl_PointSize = max(0.0, psize * oscale * scale / max(1.0, -mv.z)); gl_Position = projectionMatrix * mv; }`,
    fragmentShader: `uniform sampler2D map; uniform float hasMap; uniform float grey; varying vec4 vColor;
      void main(){ vec2 p = gl_PointCoord; vec4 t = hasMap > 0.5 ? texture2D(map, vec2(p.x, 1.0 - p.y))
        : vec4(1.0, 1.0, 1.0, 1.0 - smoothstep(0.25, 0.5, length(p - 0.5)));
        if (grey > 0.5) t.rgb = vec3(dot(t.rgb, vec3(0.299, 0.587, 0.114)));
        gl_FragColor = t * vColor; if (gl_FragColor.a < 0.004) discard; }`,
    transparent: true, depthWrite: false,
    // (the game's flames add their light, src alpha + one; smoke blends over, src alpha + one minus src alpha)
    blending: b.on && b.dst === 0 ? T.AdditiveBlending : T.NormalBlending,
  });
  if (e.tex) v3Tex(e.tex, t => { m.uniforms.map.value = t; m.uniforms.hasMap.value = 1; });
  return m;
}

// an object's emitters, added to its group (v3Build). own: a viewer of its own runs them (fxRun), not the 3D view.
// lit: it carries its own light (a lamp's flame), so the room's light doesn't dim it
function fxAttach(g, list, own, lit){
  const T = THREE, made = [];
  for (const e of list || []){
    const cap = own ? 1500 : Math.max(8, Math.min(1200, e.nparts || 64));     // (a preview's sliders may ask for more)
    const geo = new T.BufferGeometry();
    geo.setAttribute('position', new T.BufferAttribute(new Float32Array(cap * 3), 3).setUsage(T.DynamicDrawUsage));
    geo.setAttribute('pcolor', new T.BufferAttribute(new Float32Array(cap * 4), 4).setUsage(T.DynamicDrawUsage));
    geo.setAttribute('psize', new T.BufferAttribute(new Float32Array(cap), 1).setUsage(T.DynamicDrawUsage));
    geo.setDrawRange(0, 0);
    // (the emitter's spot only: a selection's box, and picking, stay the object's own)
    const at = new T.Vector3(...e.at);
    geo.boundingBox = new T.Box3(at.clone(), at.clone());
    geo.boundingSphere = new T.Sphere(at.clone(), 1);
    const pts = new T.Points(geo, fxMaterial(e));
    pts.frustumCulled = false;
    pts.raycast = () => {};
    pts.renderOrder = 5;
    pts.userData.fx = true;
    g.add(pts);
    const s = {e, g, pts, cap, p: [], acc: 0, t: Math.random() * 10,
               R: e.R, pR: e.pR, base: (e.color || [1, 1, 1, 1]), lit: !!lit || !!own,
               em: [0, 1, 2].map(k => (e.emissive || [0, 0, 0])[k] || 0), dif: [0, 1, 2].map(k => (e.diffuse || [1, 1, 1])[k] ?? 1),
               tint: [1, 1, 1]};
    fxLight(s, [1, 1, 1]);
    // (warmed up, so a torch is lit when it comes into view, not starting from nothing)
    for (let k = 0; k < 40; k++) fxStep(s, 0.05);
    if (own) s.own = true; else PFX.live.push(s);
    made.push(s);
  }
  return made;
}

// a small viewer's own emitters (the model preview), each frame
function fxRun(list, dt, renderer, camera){
  const scale = renderer.domElement.height / (2 * Math.tan(camera.fov * Math.PI / 360));
  for (const s of list){
    s.pts.material.uniforms.scale.value = scale;
    fxStep(s, Math.min(0.1, dt));
    fxDraw(s);
  }
}

// how far a list of emitters reaches from where it starts, for framing a view of it
function fxReach(e){
  const life = (e.life || 0) + (e.life_random || 0);
  return Math.max(10, Math.max(...(e.box || [0, 0, 0])) / 2 + Math.min(400, ((e.speed || 0) + (e.speed_random || 0) / 2) * life) + 2 * (e.size || 0));
}

// the game lights particles as it lights anything: their own glow (emissive) plus the light falling on them
// (diffuse). Seen in the game 2026-11-18: smoke and spray in a dim hall came out dim and tinted by its light,
// a lamp's flame bright from the lamp beside it
function fxLight(s, room){
  const L = s.lit ? [1, 1, 1] : room;
  s.tint = L;
}

const fxRot = (R, v) => [R[0][0] * v[0] + R[0][1] * v[1] + R[0][2] * v[2], R[1][0] * v[0] + R[1][1] * v[1] + R[1][2] * v[2],
                         R[2][0] * v[0] + R[2][1] * v[1] + R[2][2] * v[2]];
const fxRnd = () => 2 * Math.random() - 1;

function fxEmit(s){
  const e = s.e, box = e.box || [0, 0, 0];
  const off = fxRot(s.R, [box[0] / 2 * fxRnd(), box[1] / 2 * fxRnd(), box[2] / 2 * fxRnd()]).map(x => x * (e.s || 1));
  // (OpenMW's shooter: up from Z by the vertical angle, then round Z by the horizontal one)
  const h = e.h_dir + e.h_angle * fxRnd(), v = e.v_dir + e.v_angle * fxRnd();
  const sp = (e.speed - e.speed_random / 2) + e.speed_random * Math.random();
  const d = fxRot(s.R, [Math.cos(h) * Math.sin(v), Math.sin(h) * Math.sin(v), Math.cos(v)]);
  s.p.push({x: e.at[0] + off[0], y: e.at[1] + off[1], z: e.at[2] + off[2], vx: d[0] * sp, vy: d[1] * sp, vz: d[2] * sp,
            age: 0, life: Math.max(1e-4, e.life + e.life_random * Math.random())});
}

function fxColor(keys, f){
  if (!keys.length) return null;
  if (f <= keys[0][0]) return keys[0].slice(1, 5);
  for (let k = 1; k < keys.length; k++){
    const a = keys[k - 1], b = keys[k];
    if (f <= b[0]){ const u = (f - a[0]) / Math.max(1e-6, b[0] - a[0]); return [1, 2, 3, 4].map(i => a[i] + (b[i] - a[i]) * u); }
  }
  return keys[keys.length - 1].slice(1, 5);
}

function fxStep(s, dt){
  const e = s.e;
  s.t += dt;
  const ct = fxTime(e, s.t);
  if (ct >= e.emit_start && ct < e.emit_stop){
    s.acc += fxRate(e) * dt;
    while (s.acc >= 1){ s.acc -= 1; if (s.p.length < s.cap) fxEmit(s); }
  } else s.acc = 0;
  const grav = (e.gravity || []).map(g => {
    const dir = fxRot(s.pR, g.dir), pos = fxRot(s.pR, g.pos);
    return {g, dir, pos: [pos[0] + e.pt[0], pos[1] + e.pt[1], pos[2] + e.pt[2]]};
  });
  const keep = [];
  for (const q of s.p){
    q.age += dt;
    if (q.age >= q.life) continue;
    for (const {g, dir, pos} of grav){
      if (g.type === 0){
        let decay = 1;
        if (g.decay) decay = Math.exp(-g.decay * Math.abs((q.x - pos[0]) * dir[0] + (q.y - pos[1]) * dir[1] + (q.z - pos[2]) * dir[2]));
        const f = g.force * dt * decay * 1.6;
        q.vx += dir[0] * f; q.vy += dir[1] * f; q.vz += dir[2] * f;
      } else {
        let dx = pos[0] - q.x, dy = pos[1] - q.y, dz = pos[2] - q.z; const L = Math.hypot(dx, dy, dz) || 1;
        const f = g.force * dt * (g.decay ? Math.exp(-g.decay * L) : 1) * 1.6 / L;
        q.vx += dx * f; q.vy += dy * f; q.vz += dz * f;
      }
    }
    q.x += q.vx * dt; q.y += q.vy * dt; q.z += q.vz * dt;
    keep.push(q);
  }
  s.p = keep;
}

function fxDraw(s){
  const e = s.e, geo = s.pts.geometry, P = geo.attributes.position.array, C = geo.attributes.pcolor.array,
        Z = geo.attributes.psize.array, keys = e.colors || [];
  let n = 0;
  for (const q of s.p){
    if (n >= s.cap) break;
    // (OpenMW's grow and fade: a fade longer than the life starts the particle already small)
    let size = e.size * 2;
    if (e.grow && q.age < e.grow) size *= q.age / e.grow;
    if (e.fade && q.life - q.age < e.fade) size *= (q.life - q.age) / e.fade;
    // (vertex colours ignored, vertex mode 0, as many of the game's are: the game draws no colours over life)
    const c = e.vc && e.vc[1] === 0 ? FX_WHITE : fxColor(keys, q.age / q.life) || s.base;
    P[3 * n] = q.x; P[3 * n + 1] = q.y; P[3 * n + 2] = q.z;
    // (as the game sums it: the material's own glow, plus the colour times the light on it; colours that are their
    // own light, vertex mode 1, are just themselves. A white glow washes a colour white, as it does in the game)
    for (let k = 0; k < 3; k++) C[4 * n + k] = e.self_lit ? c[k] : Math.min(1, s.em[k] + c[k] * s.dif[k] * s.tint[k]);
    C[4 * n + 3] = c[3] * (e.alpha == null ? 1 : e.alpha);
    Z[n] = size;
    n++;
  }
  geo.setDrawRange(0, n);
  geo.attributes.position.needsUpdate = geo.attributes.pcolor.needsUpdate = geo.attributes.psize.needsUpdate = true;
}

// each frame (v3Loop): the near ones run, the far ones wait; gone ones are let go
function fxTick(dt){
  if (!PFX.live.length || !V3.camera) return;
  const cam = V3.camera.position, scale = V3.renderer.domElement.height / (2 * Math.tan(V3.camera.fov * Math.PI / 360));
  const tmp = new THREE.Vector3();
  let total = 0;
  PFX.live = PFX.live.filter(s => s.g.parent);
  // (the light the view gives the place: its ambient, sky and sun, as the game's particles take the place's light)
  const room = [0, 0, 0];
  for (const [l, k] of [[V3.amb, 1], [V3.hemi, 1], [V3.sun, 0.5]]) if (l)
    for (const [i, ch] of ['r', 'g', 'b'].entries()) room[i] += l.color[ch] * l.intensity * k;
  for (const s of PFX.live) fxLight(s, room.map(x => Math.min(1, x)));
  for (const s of PFX.live){
    s.pts.getWorldPosition(tmp);
    const near = tmp.distanceTo(cam) < PFX.near && s.g.visible !== false && total < PFX.max;
    s.pts.visible = near;
    if (!near) continue;
    s.pts.material.uniforms.scale.value = scale;
    s.pts.material.uniforms.oscale.value = s.g.scale.x || 1;
    fxStep(s, dt);
    fxDraw(s);
    total += s.p.length;
  }
}

// the sliders in Model & textures (fxedit.py does the same to the file): factors on the effect's own numbers, and a
// colour that each colour over life takes on at its own brightness, the texture drawn grey under it
const FX_WHITE = [1, 1, 1, 1];
function fxRecolour(k, c){
  const m = Math.max(...c) || 1, L = 0.299 * k[1] + 0.587 * k[2] + 0.114 * k[3];
  return [k[0], ...c.map(x => Math.min(1, L * x / m)), k[4]];
}
function fxTweak(s, t){
  if (!s.e0) s.e0 = JSON.parse(JSON.stringify(s.e));
  const e = s.e, o = s.e0;
  e.per_second = o.per_second * t.rate;
  e.life = o.life * t.life; e.life_random = o.life_random * t.life;
  e.speed = o.speed * t.speed; e.speed_random = o.speed_random * t.speed;
  e.size = o.size * t.size;
  e.gravity = o.gravity.map(g => Object.assign({}, g, {force: g.force * t.pull}));
  if (t.colour){
    const keys = o.colors.length ? o.colors : [[0, ...o.color], [1, ...o.color]];
    e.colors = keys.map(k => fxRecolour(k, t.colour));
  } else e.colors = o.colors;
  // (a colour picked is drawn even where the model ignored its colours: fxedit gives it a property that takes them)
  const glows = (o.emissive || [0, 0, 0]).reduce((a, b) => a + b, 0) > 0.05;
  e.vc = t.colour && glows ? [o.vc ? o.vc[0] : 0, 1, 0] : t.colour && o.vc && o.vc[1] === 0 ? [o.vc[0], 2, o.vc[2]] : o.vc;
  e.self_lit = !!(e.vc && e.vc[1] === 1);
  s.pts.material.uniforms.grey.value = t.colour ? 1 : 0;
}
