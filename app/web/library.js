// ---------- The Library: your own models and textures ----------
// Drop models (.nif, .obj with its .mtl and pictures, .gltf, .glb) or pictures (.png, .jpg, .tga, .dds,
// .bmp) here. Models from other programs become Morrowind models; everything goes into the folder your
// mods live in, so the game can use it at once and a mod that uses it takes it along when shared.
// Then place them like anything else, or retexture existing objects with your pictures.
const LIB = {items: null, filter: 'all'};

function libCss(){
  if ($('#lib-css')) return;
  const c = document.createElement('style'); c.id = 'lib-css';
  c.textContent = `
  .lib-card input[type=range], .modal input[type=range], .modal input[type=checkbox]{accent-color:#d9b26a}
  .lib-drop{border:2px dashed #6b5730;border-radius:12px;padding:26px;text-align:center;background:var(--bg2);color:var(--muted-c);transition:.15s}
  .lib-drop.over{border-color:var(--gold2);background:#221c12;color:var(--text-c)}
  .lib-drop b{color:var(--gold2);font-size:16px} .lib-drop .msg{margin-top:6px}
  .lib-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px;margin-top:14px}
  .lib-card{border:1px solid var(--line);border-radius:10px;background:var(--bg2);overflow:hidden;display:flex;flex-direction:column}
  .lib-card .pv{height:150px;background:var(--deep);display:flex;align-items:center;justify-content:center;cursor:pointer;color:var(--muted-b);font-size:12px}
  .lib-card .pv img{max-width:100%;max-height:150px;image-rendering:auto}
  .lib-card .bd{padding:8px 10px;display:flex;flex-direction:column;gap:4px;font-size:12px}
  .lib-card .nm{font:600 14px Inter,sans-serif;color:var(--text-c);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .lib-card .sub{color:var(--muted-b)} .lib-card .acts{display:flex;gap:4px;flex-wrap:wrap;margin-top:4px}
  .lib-tabs{display:flex;gap:4px;margin-top:14px}`;
  document.head.appendChild(c);
}

async function renderLibrary(){
  libCss();
  const box = $('#librarywrap'); if (!box) return;
  box.innerHTML = `<h1 style="margin:0 0 4px">Library</h1>
    <p class="msg" style="max-width:820px">Your own models and textures, for every mod you make. Drop them below: models made in Blender or other programs
      (.blend, .obj, .fbx, .dae, .gltf, .glb) are turned into Morrowind models, and Morrowind's own .nif models come in as they are. Pictures (.png, .jpg, .tga, .dds) can go on
      your models or <b>retexture</b> anything in the game: select it on the World map and choose 🎨 Retexture. Sounds (.wav, .mp3, .ogg) can play
      where you place them, on any object (select it and choose 🔊 Add a sound), or from your scripts.</p>
    <div class="lib-drop" id="lib-drop"><b>Drop models, pictures or sounds here</b>
      <div class="msg">A model with its pictures: drop them together (or the folder they're in).</div>
      <div style="margin-top:10px;display:flex;gap:6px;justify-content:center"><button class="btn sm primary" id="lib-pick">Choose files…</button><button class="btn sm" id="lib-pickdir">Choose a folder…</button></div>
      <input type="file" id="lib-files" multiple style="display:none" accept=".nif,.obj,.mtl,.gltf,.glb,.bin,.dae,.fbx,.blend,.png,.jpg,.jpeg,.tga,.dds,.bmp,.wav,.mp3,.ogg,.flac,.wspack">
      <input type="file" id="lib-dir" webkitdirectory style="display:none"></div>
    <div style="display:flex;gap:6px;align-items:center;margin-top:12px;flex-wrap:wrap"><b style="color:var(--gold2)">Packs</b>
      <span class="msg">Share prefabs, brushes and your models as one file, or open one someone shared.</span>
      <button class="btn sm primary" id="lib-browse">🗂 Browse packs…</button><button class="btn sm" id="lib-mkpack">⤓ Make a pack…</button><button class="btn sm" id="lib-oppack">⤒ Open a pack…</button>
      <input type="file" id="lib-packfile" accept=".wspack,.zip" style="display:none"></div>
    <div class="lib-tabs" id="lib-tabs"></div>
    <div class="lib-grid" id="lib-grid"><div class="msg"><span class="spin"></span>Loading…</div></div>`;
  const drop = $('#lib-drop');
  drop.ondragover = e => { e.preventDefault(); drop.classList.add('over'); };
  drop.ondragleave = () => drop.classList.remove('over');
  drop.ondrop = async e => { e.preventDefault(); drop.classList.remove('over'); libUpload(await libDropped(e.dataTransfer)); };
  $('#lib-mkpack').onclick = packMake;
  $('#lib-browse').onclick = packBrowse;
  $('#lib-oppack').onclick = () => $('#lib-packfile').click();
  $('#lib-packfile').onchange = e => { if (e.target.files[0]) packOpen(e.target.files[0]); e.target.value = ''; };
  $('#lib-pick').onclick = () => $('#lib-files').click();
  $('#lib-pickdir').onclick = () => $('#lib-dir').click();
  $('#lib-files').onchange = e => libUpload([...e.target.files].map(f => ({file: f, path: f.name})));
  $('#lib-dir').onchange = e => libUpload([...e.target.files].map(f => ({file: f, path: f.webkitRelativePath.split('/').slice(1).join('/') || f.name})));
  await libLoad();
}

// files from a drop, with folders opened up (a model's pictures often sit in a sub-folder)
async function libDropped(dt){
  const out = [], entries = [...dt.items].map(i => i.webkitGetAsEntry && i.webkitGetAsEntry()).filter(Boolean);
  if (!entries.length) return [...dt.files].map(f => ({file: f, path: f.name}));
  const walk = (en, base) => new Promise(res => {
    if (en.isFile) return en.file(f => { out.push({file: f, path: base + f.name}); res(); }, () => res());
    const rd = en.createReader(), all = [];
    const more = () => rd.readEntries(async list => {
      if (!list.length){ for (const c of all) await walk(c, base + en.name + '/'); return res(); }
      all.push(...list); more();
    }, () => res());
    more();
  });
  for (const en of entries) await walk(en, '');
  // (the top folder's own name isn't part of the paths)
  if (entries.length === 1 && entries[0].isDirectory) out.forEach(f => f.path = f.path.split('/').slice(1).join('/'));
  return out;
}

async function libUpload(files){
  files = files.filter(f => f.file && f.file.size);
  const packs = files.filter(f => /\.wspack$/i.test(f.path));
  for (const p of packs) await packOpen(p.file);
  files = files.filter(f => !/\.wspack$/i.test(f.path));
  if (!files.length) return;
  const batch = Math.random().toString(36).slice(2, 12) + Date.now().toString(36);
  const total = files.reduce((s, f) => s + f.file.size, 0);
  toast(`Bringing in ${files.length} file${files.length === 1 ? '' : 's'} (${(total / 1048576).toFixed(1)} MB)…`);
  try {
    for (const f of files){
      const r = await fetch('/api/library/upload?' + new URLSearchParams({batch, name: f.path}), {method: 'POST', body: f.file});
      if (!r.ok) throw new Error((await r.json()).error || 'Upload failed');
    }
    const info = await post('/api/library/inspect', {batch});
    libImportModal(batch, info);
  } catch (e){ toast(e.message, true); }
}

// the import window: what it is, how big, what kind of thing
function libImportModal(batch, info){
  const m = info.model, bg = document.createElement('div'); bg.className = 'modal-bg';
  const many = info.models.length > 1, only_pics = !info.models.length;
  const base = (info.models[0] || info.pictures[0] || 'item').replace(/\.[^.]+$/, '').replace(/[_\-]+/g, ' ');
  const sizeRows = m && m.size ? `
    <label>Size</label><div class="radios">
      <label><input type="radio" name="li-sz" value="m" ${info.looks_like === 'metres' ? 'checked' : ''}> It was made in metres (about ${info.height_as_metres} game units tall)</label>
      <label><input type="radio" name="li-sz" value="u" ${info.looks_like !== 'metres' ? 'checked' : ''}> It is already in game units (${info.height_as_is} tall)</label>
      <label><input type="radio" name="li-sz" value="h"> A height I choose</label></div>
    <div style="display:flex;gap:6px;align-items:center;margin-top:6px"><span class="msg">Height:</span><input class="inp" type="number" id="li-h" min="1" max="50000" value="${Math.round(info.height_as_metres || 100)}" style="width:90px"><span class="msg">game units</span></div>
    <div class="msg">For a sense of size: a person is about 128 units tall, a door 200, a table 70.</div>
    <label>Which way is up</label><div class="radios"><label><input type="radio" name="li-up" value="y" ${info.up !== 'z' ? 'checked' : ''}> Y (Blender's exports, glTF)</label><label><input type="radio" name="li-up" value="z" ${info.up === 'z' ? 'checked' : ''}> Z</label></div>
    <label>Bumping into it</label><div class="radios">
      <label><input type="radio" name="li-col" value="shape" ${(m.triangles || 0) <= 3000 ? 'checked' : ''}> Solid, as it's shaped</label>
      <label><input type="radio" name="li-col" value="box" ${(m.triangles || 0) > 3000 ? 'checked' : ''}> Solid, as a plain box (best for detailed models)</label>
      <label><input type="radio" name="li-col" value="none"> Walk through it (plants, cobwebs, light beams)</label></div>` : '';
  const snds = info.sounds || [], only_snd = !info.models.length && !info.pictures.length && snds.length;
  bg.innerHTML = `<div class="modal" style="width:min(600px,94vw)"><h2>${only_snd ? 'Add sounds' : only_pics ? 'Add pictures' : 'Add a model'}</h2>
    <div class="msg">${only_snd ? `${snds.length} sound${snds.length === 1 ? '' : 's'}: ${esc(snds.slice(0, 6).join(', '))}${snds.length > 6 ? '…' : ''}`
      : only_pics ? `${info.pictures.length} picture${info.pictures.length === 1 ? '' : 's'}: ${esc(info.pictures.slice(0, 6).join(', '))}${info.pictures.length > 6 ? '…' : ''}`
      : many ? `${info.models.length} models: ${esc(info.models.join(', '))}. They come in with the same settings.`
      : `${esc(info.models[0])}${m && m.triangles ? ` · ${m.triangles} triangles` : ''}${m && m.pictures && m.pictures.length ? ` · pictures: ${esc(m.pictures.join(', '))}` : ''}`}
      ${info.other.length ? `<br>Left out (not something the Workshop can use): ${esc(info.other.slice(0, 5).join(', '))}` : ''}</div>
    ${m && m.objects ? `<label>Which part</label><select class="inp" id="li-obj">
      <option value="">All ${m.objects.length} objects together, as one model</option>
      <option value="*each*">Each object as its own model (${m.objects.length} models)</option>
      ${m.objects.map(o => `<option value="${esc(o.name)}">${esc(o.name)} · ${o.triangles} triangles</option>`).join('')}</select>
      <div class="msg">This file holds several objects (a kit or a bundle). Pick one, or bring them all in.</div>` : ''}
    <label>Name</label><input class="inp" id="li-name" value="${esc(many || snds.length > 1 ? '' : (only_snd ? snds[0].replace(/\.[^.]+$/, '').replace(/[_\-]+/g, ' ') : base).replace(/^./, c => c.toUpperCase()))}" placeholder="${many || snds.length > 1 ? 'Each gets its file name' : ''}">
    ${only_snd ? `<label>How far it carries</label>${sel('li-reach', [['near', 'Close by only (a ticking clock, a small fire)'], ['room', 'Across a room (a fireplace, chimes)'], ['far', 'Far (a waterfall, a forge, a crowd)']], 'room')}
      <div class="msg">Place a sound like a model (it plays over and over where it stands, unseen), or select something on the map and choose 🔊 Add a sound. Scripts can play it too.</div>` : ''}
    ${only_pics ? '' : `<label>It is</label>${sel('li-kind', [['static', 'Scenery (stays where it is put)'], ['container', 'A container (holds things)'], ['activator', 'An activator (can be clicked, e.g. for a script)'], ['item', 'A small item (can be picked up)'], ['door', 'A door (opens, or leads to another place)'], ['light', 'A lamp or light (lights up what is round it)']], 'static')}
    <div id="li-door" style="display:none"><div class="msg">It swings on its left edge, the way the game's doors do. Once placed, choose where it leads like any other door.</div>
      <label>Sound</label>${sel('li-dsnd', [['wood', 'Wooden door'], ['creaky', 'Creaky door'], ['heavy', 'Heavy door'], ['metal', 'Metal door'], ['stone', 'Stone door'], ['dwemer', 'Dwemer door']], 'wood')}</div>
    <div id="li-light" style="display:none">
      <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:6px"><span class="msg">Colour</span><input type="color" id="li-lcol" value="#ffc88c">
        <span class="msg">Reach</span><input type="range" id="li-lrad" min="64" max="1024" step="16" value="256"><span class="msg" id="li-lradv">256</span></div>
      <label>It</label>${sel('li-lfl', [['steady', 'shines steadily'], ['flicker', 'flickers'], ['flicker_slow', 'flickers slowly'], ['pulse', 'pulses'], ['pulse_slow', 'pulses slowly'], ['fire', 'is a fire (flickers, crackles)']], 'steady')}
      <label class="msg" style="display:block;margin-top:6px"><input type="checkbox" id="li-lcarry"> Can be picked up and carried (a lantern or torch)</label></div>`}
    ${sizeRows}
    <div class="actions"><button class="btn primary" id="li-go">Add to the Library</button><button class="btn" id="li-no">Cancel</button><span class="msg" id="li-msg"></span></div></div>`;
  document.body.appendChild(bg);
  const lh = $('#li-h'); if (lh) lh.oninput = () => { const r = document.querySelector('[name=li-sz][value=h]'); if (r) r.checked = true; };
  const lk = $('#li-kind');
  if (lk) lk.onchange = () => { $('#li-door').style.display = lk.value === 'door' ? 'block' : 'none'; $('#li-light').style.display = lk.value === 'light' ? 'block' : 'none'; };
  const lr = $('#li-lrad'); if (lr) lr.oninput = () => { $('#li-lradv').textContent = lr.value; };
  const lo = $('#li-obj');
  if (lo) lo.onchange = () => {
    const nm = $('#li-name');
    nm.value = lo.value === '*each*' ? '' : lo.value || base.charAt(0).toUpperCase() + base.slice(1);
    nm.placeholder = lo.value === '*each*' ? 'Each gets its object name' : '';
    nm.disabled = lo.value === '*each*';
  };
  $('#li-no').onclick = () => bg.remove();
  $('#li-go').onclick = async () => {
    // how tall it ends up: as made in metres (the Workshop scales it), as it is, or a height you give
    const sz = (document.querySelector('[name=li-sz]:checked') || {}).value;
    const size = sz === 'u' ? info.height_as_is : sz === 'h' ? +$('#li-h').value : null;
    const body = {batch, name: $('#li-name').value, up: (document.querySelector('[name=li-up]:checked') || {}).value || 'y',
      kind: ($('#li-kind') || {}).value || 'static', size, collision: (document.querySelector('[name=li-col]:checked') || {}).value || 'shape',
      object: lo ? lo.value : ''};
    if (body.kind === 'door') body.door_sound = $('#li-dsnd').value;
    if ($('#li-reach')) body.reach = $('#li-reach').value;
    if (body.kind === 'light'){
      const hex = $('#li-lcol').value;
      body.light = {color: [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16)), radius: +$('#li-lrad').value,
        flicker: $('#li-lfl').value, carry: $('#li-lcarry').checked};
    }
    $('#li-go').disabled = true; $('#li-msg').innerHTML = '<span class="spin"></span>Bringing it in…';
    try {
      const r = await post('/api/library/import', body);
      // small items get an inventory icon: a picture of the model
      for (const a of r.added) if (a.type === 'model' && (body.kind === 'item' || (body.kind === 'light' && body.light.carry))){ try { await libMakeIcon(a); } catch (e){} }
      bg.remove();
      const names = r.added.length > 4 ? `${r.added.length} models` : r.added.map(a => a.name).join(', ');
      toast(`Added ${names} to the Library.` + (r.added.some(a => a.note) ? ' ' + r.added.find(a => a.note).note : '') +
        (typeof LINK !== 'undefined' && LINK.connected ? ' The game that is running now sees new models only after you start it again.' : ''));
      LIB.items = null; await libLoad();
    } catch (e){ $('#li-msg').className = 'msg err'; $('#li-msg').textContent = e.message; $('#li-go').disabled = false; }
  };
}

async function libLoad(){
  const grid = $('#lib-grid'); if (!grid) return;
  try { LIB.items = (await api('/api/library')).items; } catch (e){ grid.innerHTML = `<div class="msg err">${esc(e.message)}</div>`; return; }
  const n = t => LIB.items.filter(i => t === 'all' || i.type === t).length;
  $('#lib-tabs').innerHTML = [['all', 'Everything'], ['model', 'Models'], ['texture', 'Pictures'], ['sound', 'Sounds']].map(([k, l]) =>
    `<button class="btn sm ${LIB.filter === k ? 'primary' : ''}" data-lf="${k}">${l} ${n(k)}</button>`).join('');
  document.querySelectorAll('[data-lf]').forEach(b => b.onclick = () => { LIB.filter = b.dataset.lf; libLoad(); });
  const items = LIB.items.filter(i => LIB.filter === 'all' || i.type === LIB.filter);
  if (!items.length){ grid.innerHTML = `<div class="msg">${LIB.items.length ? 'Nothing of this kind yet.' : 'Nothing here yet. Drop a model or a picture above to start.'}</div>`; return; }
  grid.innerHTML = items.map(it => `<div class="lib-card" data-li="${esc(it.id)}">
    <div class="pv" data-lpv="${esc(it.id)}">${it.type === 'texture' ? `<img src="/api/file?path=${encodeURIComponent(it.file)}" alt="">`
      : it.type === 'sound' ? `<div style="display:flex;flex-direction:column;gap:6px;align-items:center;width:100%;padding:0 8px"><span style="font-size:28px">🔊</span>
          <audio controls preload="none" src="/api/file?path=${encodeURIComponent(it.file)}" style="width:100%;height:32px"></audio></div>` : '🧊 Click for a 3D look'}</div>
    <div class="bd"><span class="nm" title="${esc(it.name)}">${esc(it.name)}</span>
      <span class="sub">${it.type === 'model' ? (it.size ? `${it.size.map(Math.round).join(' × ')} units` : 'Model') : it.type === 'sound' ? `Sound${it.records && it.records.SOUN ? ` · for scripts: <code>PlaySound "${esc(it.records.SOUN)}"</code>` : ''}` : 'Picture'}${{door: ' · 🚪 door', light: ' · 💡 light', container: ' · container', activator: ' · activator', item: ' · item'}[it.kind] || ''} · from ${esc(it.from || '?')}${it.ok ? '' : ' · <span style="color:#ff8a6a">file missing</span>'}</span>
      <div class="acts">${it.type === 'sound' ? `<button class="btn sm primary" data-lplace="${esc(it.id)}" title="Put it in the world: it plays over and over where it stands, unseen">Place</button>
        <select class="inp" data-lreach="${esc(it.id)}" title="How far it carries" style="width:auto;padding:2px 4px">${[['near', 'Close by'], ['room', 'A room'], ['far', 'Far']].map(([v, l]) => `<option value="${v}" ${(it.reach || 'room') === v ? 'selected' : ''}>${l}</option>`).join('')}</select>
        <input type="range" min="0" max="100" value="${Math.round((it.volume ?? 0.8) * 100)}" data-lvol="${esc(it.id)}" title="How loud" style="width:70px">
        ${it.records && it.records.SOUN ? '' : `<button class="btn sm" data-lsrec="${esc(it.id)}" title="Make it a sound your scripts can play">For scripts</button>`}`
      : it.type === 'model' ? `<button class="btn sm primary" data-lplace="${esc(it.id)}" title="Put it in the world">Place</button>
        ${it.kind === 'item' || (it.kind === 'light' && it.light && it.light.carry) ? `<button class="btn sm" data-licon="${esc(it.id)}" title="Make its inventory icon again, from the model">${it.icon ? `<img src="/api/file?path=${encodeURIComponent('icons/' + it.icon.replace(/\\/g, '/'))}" style="width:16px;height:16px;vertical-align:middle"> ` : ''}Icon</button>` : ''}` : `<span class="sub">Use it with 🎨 Retexture on the map</span>`}
        <button class="btn sm" data-lrm="${esc(it.id)}" title="Take it off this list (its file stays, mods may use it)">✕</button></div></div></div>`).join('');
  grid.querySelectorAll('[data-lpv]').forEach(p => p.onclick = () => {
    const it = LIB.items.find(i => i.id === p.dataset.lpv); if (!it || it.type !== 'model') return;
    p.onclick = null; p.style.cursor = 'default'; showModel(p, {model: it.model}, 'library');
  });
  grid.querySelectorAll('[data-lplace]').forEach(b => b.onclick = () => libPlace(b.dataset.lplace));
  // a sound: how far it carries, how loud, and a record scripts can play
  const sndSet = async (id, data) => { if (data.record && !await needProject()) return; try { await post('/api/library/sound', Object.assign({id}, data)); LIB.items = null; libLoad(); } catch (e){ toast(e.message, true); } };
  grid.querySelectorAll('[data-lreach]').forEach(s => s.onchange = () => sndSet(s.dataset.lreach, {reach: s.value}));
  grid.querySelectorAll('[data-lvol]').forEach(s => s.onchange = () => sndSet(s.dataset.lvol, {volume: s.value / 100}));
  grid.querySelectorAll('[data-lsrec]').forEach(b => b.onclick = () => sndSet(b.dataset.lsrec, {record: true}));
  grid.querySelectorAll('[data-licon]').forEach(b => b.onclick = async () => {
    try { await libMakeIcon(LIB.items.find(i => i.id === b.dataset.licon)); toast('Made its inventory icon.' + (typeof LINK !== 'undefined' && LINK.connected ? ' The running game shows it after you start it again.' : '')); libLoad(); } catch (e){ toast(e.message, true); }
  });
  grid.querySelectorAll('[data-lrm]').forEach(b => b.onclick = async () => {
    const it = LIB.items.find(i => i.id === b.dataset.lrm);
    if (!confirm(`Take "${it.name}" off the Library? Its file stays, as mods may use it.`)) return;
    await post('/api/library/remove', {id: it.id}); libLoad();
  });
}

// placing: the Library model gets a record in the mod (once), then it's placed like anything else
async function libPlace(id){
  if (!await needProject()) return;
  const it = LIB.items.find(i => i.id === id);
  try {
    const r = await post('/api/library/record', {id, kind: it.kind});
    toast(`"${it.name}" is in your mod as ${r.id}. Click where it goes on the World map (or in 3D).`);
    showView('world');
    setMode('place', {id: r.id, name: it.name, type: r.type});
  } catch (e){ toast(e.message, true); }
}

// ----- an inventory icon for an item made from your model: a picture of it, like the game's icons
async function libMakeIcon(it){
  await ensureThree();
  const m = await api('/api/model?' + new URLSearchParams({model: it.model}));
  if (m.error) throw new Error(m.error);
  const T = window.THREE, S = 128;
  const renderer = new T.WebGLRenderer({antialias: true, alpha: true, preserveDrawingBuffer: true});
  renderer.setSize(S, S); renderer.setClearColor(0x000000, 0);
  const scene = new T.Scene();
  scene.add(new T.HemisphereLight(0xfff4e0, 0x403020, 1.0));
  const sun = new T.DirectionalLight(0xffffff, 0.8); sun.position.set(1, 2, 1.5); scene.add(sun);
  const group = new T.Group(); group.rotation.x = -Math.PI / 2;
  const waits = [];
  for (const s of m.shapes){
    const g = new T.BufferGeometry();
    g.setAttribute('position', new T.Float32BufferAttribute(s.p, 3));
    if (s.uv && s.uv.length) g.setAttribute('uv', new T.Float32BufferAttribute(s.uv, 2));
    g.setIndex(s.i); g.computeVertexNormals();
    const mat = new T.MeshLambertMaterial({color: 0xd8cfbf, side: T.DoubleSide, alphaTest: s.alpha ? 0.5 : 0, transparent: !!s.alpha});
    if (s.tex){
      const loader = s.tex.endsWith('.dds') ? new T.DDSLoader() : s.tex.endsWith('.tga') ? new T.TGALoader() : new T.TextureLoader();
      waits.push(new Promise(res => loader.load('/api/file?path=' + encodeURIComponent(s.tex), tex => {
        if (!s.tex.endsWith('.dds')) tex.flipY = false; else { tex.minFilter = T.LinearFilter; tex.generateMipmaps = false; if (tex.mipmaps) tex.mipmaps = tex.mipmaps.slice(0, 1); }
        mat.map = tex; mat.color.set(0xffffff); mat.needsUpdate = true; res();
      }, undefined, res)));
    }
    group.add(new T.Mesh(g, mat));
  }
  await Promise.all(waits);
  scene.add(group);
  const box = new T.Box3().setFromObject(group), size = box.getSize(new T.Vector3()), c = box.getCenter(new T.Vector3());
  const r = Math.max(size.x, size.y, size.z, 1) * 0.62;
  // seen from above and to one side, filling the square, like the game's own icons
  const cam = new T.OrthographicCamera(-r, r, r, -r, r / 50, r * 20);
  cam.position.set(c.x + r * 2.2, c.y + r * 2.6, c.z + r * 2.2); cam.lookAt(c);
  renderer.render(scene, cam);
  const out = document.createElement('canvas'); out.width = out.height = 32;
  out.getContext('2d').drawImage(renderer.domElement, 0, 0, 32, 32);
  renderer.dispose(); renderer.forceContextLoss && renderer.forceContextLoss();
  const blob = await new Promise(res => out.toBlob(res, 'image/png'));
  const res = await fetch('/api/library/icon?id=' + encodeURIComponent(it.id), {method: 'POST', body: blob});
  const j = await res.json(); if (!res.ok) throw new Error(j.error || 'Could not save the icon');
  return j;
}

// ----- packs: prefabs, brushes and Library models in one file to share
async function packMake(){
  const [pfs, brs, lib] = await Promise.all([api('/api/prefabs'), api('/api/brushes'), api('/api/library')]);
  const bg = document.createElement('div'); bg.className = 'modal-bg';
  const group = (title, key, rows, none) => `<label>${title}</label><div style="max-height:150px;overflow:auto;border:1px solid var(--line);border-radius:6px;padding:4px 8px">${rows.length
    ? rows.map(r => `<label class="msg" style="display:flex;gap:6px;align-items:center;margin:2px 0"><input type="checkbox" data-pk="${key}" value="${esc(r.v)}"> ${esc(r.t)}</label>`).join('')
    : `<div class="msg">${none}</div>`}</div>`;
  let shelf = null;
  try { shelf = await api('/api/packs/browse'); } catch (e){}
  const folders = shelf ? shelf.sources.filter(s => s.kind === 'folder') : [];
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem('ws-pack-author') || '{}'); } catch (e){}
  bg.innerHTML = `<div class="modal" style="width:min(560px,94vw)"><h2>⤓ Make a pack</h2>
    <div class="msg">One file with what you choose. Your own models that the prefabs and brushes use come along by themselves.</div>
    <label>Name</label><input class="inp" id="pk-name" placeholder="e.g. Ashlander camp kit">
    <label>What's in it <span class="msg">(shown on the pack shelf)</span></label><textarea class="inp" id="pk-desc" rows="2" placeholder="e.g. A yurt, a fire pit and bedrolls, with my own hide textures."></textarea>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px"><div><label>Made by</label><input class="inp" id="pk-author" value="${esc(saved.author || '')}" placeholder="Your name"></div>
      <div><label>A picture <span class="msg">(optional)</span></label><input type="file" id="pk-pic" accept=".png,.jpg,.jpeg" class="inp"></div></div>
    ${group('Prefabs', 'prefabs', pfs.map(p => ({v: p.file, t: `${p.name} (${p.items.length} object${p.items.length === 1 ? '' : 's'})`})), 'No prefabs yet: select a few objects on the map and use "Save as a prefab".')}
    ${group('Brushes', 'brushes', brs.brushes.map(b => ({v: b.id, t: `${b.name} (${b.items.length})`})), 'No brushes of your own yet.')}
    ${group('Library', 'library', lib.items.map(i => ({v: i.id, t: `${i.name} (${{model: 'model', sound: 'sound'}[i.type] || 'picture'})`})), 'The Library is empty.')}
    <label>Save it</label><select class="inp" id="pk-where"><option value="file">as a file to download (send it to people yourself)</option>
      ${folders.map((f, k) => `<option value="${k}">into ${esc(f.name || f.where)} (everyone with that folder sees it on their pack shelf)</option>`).join('')}</select>
    <div class="actions"><button class="btn primary" id="pk-go">Save the pack</button><button class="btn" id="pk-no">Cancel</button><span class="msg" id="pk-msg"></span></div></div>`;
  document.body.appendChild(bg);
  $('#pk-no').onclick = () => bg.remove();
  $('#pk-go').onclick = async () => {
    const pick = k => [...bg.querySelectorAll(`[data-pk="${k}"]:checked`)].map(c => c.value);
    const name = $('#pk-name').value.trim() || 'My pack';
    const author = $('#pk-author').value.trim(), where = $('#pk-where').value;
    try { localStorage.setItem('ws-pack-author', JSON.stringify({author})); } catch (e){}
    let picture = null;
    const pf = $('#pk-pic').files[0];
    if (pf) picture = await new Promise(res => { const fr = new FileReader(); fr.onload = () => res(fr.result); fr.readAsDataURL(pf); });
    try {
      const r = await fetch('/api/pack/make', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name, prefabs: pick('prefabs'), brushes: pick('brushes'), library: pick('library'), description: $('#pk-desc').value,
                              author, picture, share: where !== 'file', share_to: where === 'file' ? null : +where})});
      if (!r.ok) throw new Error((await r.json()).error || 'Could not make the pack');
      if (where !== 'file'){
        const j = await r.json();
        bg.remove(); return toast('Put the pack in your folder: ' + j.shared);
      }
      const a = document.createElement('a'); a.href = URL.createObjectURL(await r.blob());
      a.download = name.replace(/[^\w\- ]+/g, '_') + '.wspack'; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 3000);
      bg.remove(); toast('Saved the pack. Share the .wspack file; others open it with ⤒ Open a pack, or put it in a folder or online for their pack shelf.');
    } catch (e){ $('#pk-msg').className = 'msg err'; $('#pk-msg').textContent = e.message; }
  };
}

// ----- the pack shelf: packs other people share, from folders and links you choose
async function packBrowse(){
  libCss();
  const bg = document.createElement('div'); bg.className = 'modal-bg';
  bg.innerHTML = `<div class="modal" style="width:min(1000px,96vw);max-height:92vh;display:flex;flex-direction:column"><h2>🗂 Pack shelf</h2>
    <div class="lib-tabs"><button class="btn sm primary" data-pt="packs">Packs</button><button class="btn sm" data-pt="places">Places</button>
      <span style="flex:1"></span><button class="btn sm" id="ps-again" title="Look again">↻</button><button class="btn sm" id="ps-close">Close</button></div>
    <div id="ps-body" style="overflow:auto;margin-top:10px;min-height:200px"><div class="msg"><span class="spin"></span>Looking through your places…</div></div></div>`;
  document.body.appendChild(bg);
  let data = null, tab = 'packs';
  const kb = n => n == null ? '' : n > 1048576 ? (n / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(n / 1024)) + ' KB';
  const show = () => {
    bg.querySelectorAll('[data-pt]').forEach(b => b.classList.toggle('primary', b.dataset.pt === tab));
    const body = $('#ps-body');
    if (!data){ body.innerHTML = '<div class="msg"><span class="spin"></span>Looking through your places…</div>'; return; }
    if (tab === 'places') return showPlaces(body);
    const probs = data.problems.map(p => `<div class="msg err">${esc(p)}</div>`).join('');
    if (!data.packs.length){
      body.innerHTML = probs + `<div class="msg" style="max-width:640px">No packs yet. Packs show up here from the <b>places</b> you list: a folder (one that syncs, like Dropbox or Google Drive,
        shared with friends; a USB stick) or a link (to a pack, a web page or folder that links to packs, or a packs.json list).
        Your own folder to start with: <code>${esc(data.shared_folder)}</code>. Put .wspack files in it, or save packs into it from ⤓ Make a pack.</div>`;
      return;
    }
    body.innerHTML = probs + `<div class="lib-grid">${data.packs.map((p, k) => {
      const what = [p.prefabs && p.prefabs.length && `${p.prefabs.length} prefab${p.prefabs.length === 1 ? '' : 's'}`, p.brushes && p.brushes.length && `${p.brushes.length} brush${p.brushes.length === 1 ? '' : 'es'}`,
        p.models && `${p.models} model${p.models === 1 ? '' : 's'}`, p.pictures && `${p.pictures} picture${p.pictures === 1 ? '' : 's'}`, p.sounds && `${p.sounds} sound${p.sounds === 1 ? '' : 's'}`].filter(Boolean).join(' · ');
      const pic = p.picture_url ? `<img src="${esc(p.picture_url)}" alt="">` : (p.local && p.has_picture) ? `<img src="/api/packs/picture?source=${p.source}&ref=${encodeURIComponent(p.ref)}" alt="">` : '<span style="font-size:44px;opacity:.6">🗂</span>';
      return `<div class="lib-card"><div class="pv" data-pk="${k}">${pic}</div><div class="bd"><div class="nm" title="${esc(p.name)}">${esc(p.name)}</div>
        <div class="sub">${p.author ? 'by ' + esc(p.author) + ' · ' : ''}${esc((data.sources[p.source] || {}).name || (data.sources[p.source] || {}).where || '')}</div>
        ${p.description ? `<div class="msg" style="max-height:48px;overflow:hidden">${esc(p.description)}</div>` : ''}
        <div class="sub">${what || (p.local ? 'empty' : 'not looked at yet')}${p.size ? ' · ' + kb(p.size) : ''}</div>
        <div class="acts"><button class="btn sm ${p.added ? '' : 'primary'}" data-pa="${k}">${p.added ? '✓ Added ' + esc(p.added) + ' (add again)' : '＋ Add to my Library'}</button>
          ${p.local ? '' : `<button class="btn sm" data-pl="${k}">Look inside</button>`}</div></div></div>`;
    }).join('')}</div>`;
    body.querySelectorAll('[data-pa]').forEach(b => b.onclick = async () => {
      const p = data.packs[+b.dataset.pa]; b.disabled = true; b.textContent = 'Adding…';
      try {
        const r = await post('/api/packs/add', {source: p.source, ref: p.ref});
        const got = [r.library.length && `${r.library.length} Library item${r.library.length === 1 ? '' : 's'}`, r.prefabs.length && `${r.prefabs.length} prefab${r.prefabs.length === 1 ? '' : 's'}`,
          r.brushes && `${r.brushes} brush${r.brushes === 1 ? '' : 'es'}`].filter(Boolean).join(', ');
        toast(`Added "${r.name}": ${got || 'nothing new'}.` + (r.missing_count ? ` ${r.missing_count} object${r.missing_count === 1 ? '' : 's'} left out (your load order doesn't have ${r.missing_count === 1 ? 'it' : 'them'}).` : ''));
        W.prefabs = null; if (window.V3) V3.scatSets = null; LIB.items = null; libLoad();
        load();
      } catch (e){ toast(e.message, true); b.disabled = false; b.textContent = '＋ Add to my Library'; }
    });
    body.querySelectorAll('[data-pl]').forEach(b => b.onclick = async () => {
      const p = data.packs[+b.dataset.pl]; b.disabled = true; b.textContent = 'Downloading…';
      try { Object.assign(p, await post('/api/packs/look', {source: p.source, ref: p.ref}), {local: true}); show(); }
      catch (e){ toast(e.message, true); b.disabled = false; b.textContent = 'Look inside'; }
    });
  };
  const showPlaces = body => {
    const rows = data.sources.map((s, k) => `<div style="display:flex;gap:6px;align-items:center;margin:4px 0">
      <span title="${s.kind === 'folder' ? 'A folder' : 'A link'}">${s.kind === 'folder' ? '📁' : '🔗'}</span>
      <input class="inp" data-pn="${k}" value="${esc(s.name || '')}" placeholder="A name" style="width:200px">
      <input class="inp" data-pw="${k}" value="${esc(s.where)}" style="flex:1"><button class="btn sm" data-px="${k}" title="Take it off the list">✕</button></div>`).join('');
    body.innerHTML = `<div class="msg" style="max-width:760px">Where packs come from. <b>A folder</b>: paste its path, e.g. a Dropbox or Google Drive folder you share with friends
      (whatever anyone puts in it shows up for everyone), or a USB stick. <b>A link</b>: to one .wspack, to a web page or folder listing that links to packs,
      or to a <code>packs.json</code> list. Dropbox and Google Drive share links work as they are.</div>
      <div style="margin:10px 0">${rows || '<div class="msg">No places yet.</div>'}</div>
      <div style="display:flex;gap:6px"><input class="inp" id="ps-new" placeholder="Paste a folder path or a link" style="flex:1"><button class="btn sm" id="ps-add">＋ Add</button></div>
      <div class="actions"><button class="btn primary" id="ps-save">Save places</button><span class="msg" id="ps-msg"></span></div>`;
    const list = () => data.sources.map((s, k) => ({where: (body.querySelector(`[data-pw="${k}"]`) || {}).value || s.where, name: (body.querySelector(`[data-pn="${k}"]`) || {}).value || ''}));
    body.querySelectorAll('[data-px]').forEach(b => b.onclick = () => { data.sources = list().filter((_s, k) => k !== +b.dataset.px); showPlaces(body); });
    $('#ps-add').onclick = () => { const v = $('#ps-new').value.trim(); if (!v) return; data.sources = list().concat([{where: v, name: '', kind: /^https?:/i.test(v) ? 'link' : 'folder'}]); showPlaces(body); };
    $('#ps-save').onclick = async () => {
      try { await post('/api/packs/sources', {sources: list()}); toast('Saved. Looking through them…'); tab = 'packs'; load(); }
      catch (e){ $('#ps-msg').className = 'msg err'; $('#ps-msg').textContent = e.message; }
    };
  };
  const load = async () => {
    data = null; show();
    try { data = await api('/api/packs/browse'); } catch (e){ $('#ps-body').innerHTML = `<div class="msg err">${esc(e.message)}</div>`; return; }
    show();
  };
  bg.querySelectorAll('[data-pt]').forEach(b => b.onclick = () => { tab = b.dataset.pt; show(); });
  $('#ps-close').onclick = () => bg.remove();
  $('#ps-again').onclick = load;
  load();
}
async function packOpen(file){
  toast('Opening the pack…');
  try {
    const res = await fetch('/api/pack/open', {method: 'POST', body: file});
    const r = await res.json(); if (!res.ok) throw new Error(r.error || 'Could not open it');
    const got = [r.library.length && `${r.library.length} Library item${r.library.length === 1 ? '' : 's'}`, r.prefabs.length && `${r.prefabs.length} prefab${r.prefabs.length === 1 ? '' : 's'}`,
      r.brushes && `${r.brushes} brush${r.brushes === 1 ? '' : 'es'}`].filter(Boolean).join(', ');
    toast(`Opened "${r.name}": ${got || 'nothing new'}.` + (r.missing_count ? ` ${r.missing_count} object${r.missing_count === 1 ? '' : 's'} left out (your load order doesn't have ${r.missing_count === 1 ? 'it' : 'them'}: ${r.missing.slice(0, 3).join(', ')}${r.missing_count > 3 ? '…' : ''}).` : ''), !got);
    W.prefabs = null; if (window.V3) V3.scatSets = null; LIB.items = null; libLoad();
  } catch (e){ toast(e.message, true); }
}

// ----- retexturing an object on the map with pictures from the Library (or any texture in the game)
// a sound from the Library, playing where a selected object stands (an unseen sound source placed on it)
async function libAttachSound(sel, cell){
  const snds = (await api('/api/library')).items.filter(i => i.type === 'sound' && i.ok);
  if (!snds.length) return toast('There are no sounds in your Library yet: drop some .wav, .mp3 or .ogg files on the Library page first.');     // (a hint, not a fault)
  const bg = document.createElement('div'); bg.className = 'modal-bg';
  bg.innerHTML = `<div class="modal" style="width:min(560px,94vw)"><h2>🔊 A sound for ${esc(sel.name || sel.id)}</h2>
    <div class="msg">It plays over and over where this stands, and gets louder as you come closer. Listen, then pick one.</div>
    <div style="display:flex;flex-direction:column;gap:6px;margin:10px 0;max-height:50vh;overflow:auto">${snds.map(s => `<label style="display:grid;grid-template-columns:auto 1fr 200px;gap:8px;align-items:center">
      <input type="radio" name="as-pick" value="${esc(s.id)}"><span>${esc(s.name)} <span class="msg">(${{near: 'close by', room: 'a room', far: 'far'}[s.reach || 'room']})</span></span>
      <audio controls preload="none" src="/api/file?path=${encodeURIComponent(s.file)}" style="width:200px;height:28px"></audio></label>`).join('')}</div>
    <div class="actions"><button class="btn primary" id="as-go">Add it</button><button class="btn" id="as-no">Cancel</button><span class="msg" id="as-msg"></span></div></div>`;
  document.body.appendChild(bg);
  const first = bg.querySelector('[name=as-pick]'); if (first) first.checked = true;
  $('#as-no').onclick = () => bg.remove();
  $('#as-go').onclick = async () => {
    const id = (bg.querySelector('[name=as-pick]:checked') || {}).value; if (!id) return;
    try {
      const p = sel.p || [0, 0, 0];
      // (a little above its base: where a sound "comes from")
      const h = sel.b ? (sel.b[2] + sel.b[5]) / 2 * (sel.s || 1) : 40;
      const r = await post('/api/library/attach', {id, cell, p: [p[0], p[1], p[2] + h]});
      bg.remove();
      toast(`Added the sound (${r.id}) here. Undo takes it away again.`);
      if (typeof worldReloadCell === 'function') await worldReloadCell(cell);
      if (typeof afterChange === 'function') afterChange();
      if (typeof v3Refresh === 'function') v3Refresh();
    } catch (e){ const m = $('#as-msg'); m.className = 'msg err'; m.textContent = e.message; }
  };
}

async function libRetexture(sel){
  const t = await api('/api/library/textures?i=' + sel.ri);
  if (!t.textures.length) return toast('This object\'s model has no pictures to swap.', true);
  const lib = (await api('/api/library')).items.filter(i => i.type === 'texture');
  const bg = document.createElement('div'); bg.className = 'modal-bg';
  bg.innerHTML = `<div class="modal" style="width:min(620px,94vw)"><h2>🎨 Retexture ${esc(sel.name || sel.id)}</h2>
    <div class="msg">A new object like this one, with your pictures. The original stays as it is.</div>
    <div id="rt-rows" style="display:flex;flex-direction:column;gap:8px;margin:10px 0">${t.textures.map((x, n) => `<div style="display:grid;grid-template-columns:64px 1fr;gap:8px;align-items:center">
      ${x.path ? `<img src="/api/file?path=${encodeURIComponent(x.path)}" style="width:64px;height:64px;object-fit:cover;border-radius:6px;background:#000" onerror="this.style.visibility='hidden'">` : '<span></span>'}
      <div><div class="msg" style="margin-bottom:4px">${esc(x.name)}</div><select class="inp" data-rt="${n}"><option value="">Keep this picture</option>
        ${lib.map(l => `<option value="${esc(l.texture)}">${esc(l.name)}</option>`).join('')}</select></div></div>`).join('')}</div>
    ${lib.length ? '' : '<div class="msg">There are no pictures in your Library yet: add some on the Library page first.</div>'}
    <label>Name of the new object</label><input class="inp" id="rt-name" value="${esc((sel.name || sel.id) + ' (new look)')}">
    <div class="actions"><button class="btn primary" id="rt-go" ${lib.length ? '' : 'disabled'}>Make it</button><button class="btn" id="rt-no">Cancel</button><span class="msg" id="rt-msg"></span></div></div>`;
  document.body.appendChild(bg);
  $('#rt-no').onclick = () => bg.remove();
  $('#rt-go').onclick = async () => {
    const mapping = {};
    bg.querySelectorAll('[data-rt]').forEach(s => { if (s.value) mapping[t.textures[+s.dataset.rt].name] = s.value; });
    try {
      const name = $('#rt-name').value;
      const r = await post('/api/library/retexture', {i: sel.ri, mapping, name});
      bg.remove();
      toast(`Made ${r.id}. Click where it goes.`);
      showView('world');
      setMode('place', {id: r.id, name, type: r.type});
    } catch (e){ const m = $('#rt-msg'); if (m){ m.className = 'msg err'; m.textContent = e.message; } else toast(e.message, true); }
  };
}
