// ---------- Model & textures: what an object is drawn with, and changing its textures ----------
// Opened from the object window's "🧩 Model & textures…" or the right-click menu. Shows the model (where its
// file comes from, shapes, triangles, size, what else is in it), what uses it, and its textures with
// pictures. "Change everywhere" puts a copy of the game's texture in your mod's own folder under the same
// name, so the game draws your copy wherever it is used; "For this one only" copies it under a new name
// and makes a new record of the object drawn with it. Either way it opens in your picture editor, and while
// this window is open the 3D view draws it again each time you save (assets.py).
const AS = {ri: null, data: null, watch: {}, timer: 0, bg: null,
  // the model out in Blender: {file, stamp, how ('everywhere'|'own' once chosen), lost, pending (changed, not yet back)}
  glb: null, blender: null, found: {}};

const AS_HAS = {collision: ['🧱', 'Collision', 'It has its own collision shape (what you bump into)'], animation: ['🎞', 'Animation', 'Moves: keyframes or text keys'],
  skin: ['🦴', 'Skinned', 'Bent by a skeleton (bodies, creatures)'], particles: ['✨', 'Particles', 'Smoke, sparks, flames'], light: ['💡', 'Light', 'A light inside the model'],
  flipbook: ['🎞', 'Flipbook', 'Its texture changes frame by frame'], 'scrolling texture': ['〰', 'Scrolling texture', 'Its texture slides (water, lava)'],
  morphs: ['🫧', 'Morphs', 'Shape changes'], billboard: ['🪧', 'Billboard', 'Always turns to face you'], switch: ['⇄', 'Switch', 'Shows one of several parts']};

async function asShow(ri, label){
  if (ri == null) return toast('That has no record to look at.', true);
  AS.ri = ri;
  if (AS.bg) AS.bg.remove();
  const bg = document.createElement('div'); bg.className = 'modal-bg'; AS.bg = bg;
  bg.innerHTML = `<div class="modal as-win"><h2>🧩 ${esc(label || 'Model & textures')}</h2><div id="as-body"><div class="msg"><span class="spin"></span>Reading the model…</div></div>
    <div class="actions" style="margin-top:10px"><span class="msg" id="as-msg" style="flex:1"></span><button class="btn" id="as-close">Close</button></div></div>`;
  document.body.appendChild(bg);
  asCss();
  bg.querySelector('#as-close').onclick = asClose;
  bg.addEventListener('click', e => { if (e.target === bg) asClose(); });
  bg.addEventListener('click', asClick);
  try {
    const [d, ed, bl] = await Promise.all([api('/api/assets/record?i=' + ri), api('/api/assets/editors').catch(() => ({found: [], chosen: ''})),
      api('/api/assets/blenderhere').catch(() => ({blender: null}))]);
    AS.data = d; AS.editors = ed; AS.blender = bl.blender; AS.glb = null; AS.found = {};
    asDraw();
  } catch (e){ const b = $('#as-body'); if (b) b.innerHTML = `<div class="msg err">${esc(e.message)}</div>`; }
}

function asClose(){
  clearInterval(AS.timer); AS.timer = 0; AS.watch = {};
  if (AS.bg) AS.bg.remove(); AS.bg = null;
}

function asKB(n){ return n >= 1048576 ? (n / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(n / 1024)) + ' KB'; }

function asDraw(){
  const d = AS.data, box = $('#as-body'); if (!box || !d) return;
  const has = Object.keys(d.has || {}).filter(k => AS_HAS[k]).map(k => `<span class="as-tag" title="${esc(AS_HAS[k][2])}">${AS_HAS[k][0]} ${AS_HAS[k][1]}</span>`).join('');
  const fromTag = (w, l) => `<span class="as-from as-from-${w || 'none'}">${esc(l || '')}</span>`;
  const ed = AS.editors || {found: [], chosen: ''};
  const tex = (d.textures || []).map((t, n) => {
    const mine = t.from === 'mod';
    const stamp = (AS.watch[t.path] || {}).stamp || '';
    const pic = t.path && !t.missing ? `<img class="as-pic" src="/api/assets/thumb?path=${encodeURIComponent(t.path)}&v=${stamp}" alt="" onerror="this.classList.add('none')">` : '<div class="as-pic none">missing</div>';
    const what = t.missing ? '<span class="msg err">The game can\'t find this file: the model draws without it.</span>'
      : `${esc(t.format || '?')}${t.w ? ` · ${t.w}×${t.h}` : ''}${t.mips > 1 ? ` · ${t.mips} sizes` : ''} · ${asKB(t.bytes || 0)}`;
    const found = AS.found[t.name];
    const btns = t.missing ? (found ? (found.length ? `<span class="as-sub">The game has a texture of that name:</span> ${found.map(f => `<button class="btn sm" data-as="fixto" data-n="${n}" data-to="${esc(f)}" title="Point the model at this texture">${esc(f.replace('textures/', ''))}</button>`).join('')}`
        : '<span class="as-sub">The game has no texture of that name anywhere.</span>')
      : `<button class="btn sm" data-as="find" data-n="${n}" title="Look through every data folder and archive for a texture of the same name">🔍 Look for it</button>`) : mine
      ? `<button class="btn sm" data-as="open" data-n="${n}" title="Open your copy in the picture editor again">✎ Open your copy</button>
         <button class="btn sm" data-as="giveback" data-n="${n}" title="Take your copy out of the mod (to the Recycle Bin); the game draws its own again">↺ The game's own again</button>`
      : `<button class="btn sm primary" data-as="everywhere" data-n="${n}" title="Your copy under the same name: it shows everywhere this texture is used">✎ Change everywhere</button>
         <button class="btn sm" data-as="own" data-n="${n}" title="A copy under a new name, on a new record of this object only">✎ For this one only…</button>`;
    return `<div class="as-tex">${pic}<div class="as-texinfo"><div class="as-texname" title="${esc(t.path || t.name)}">${esc(t.name)} ${t.missing ? '' : fromTag(t.from, t.from === 'mod' ? "your mod's copy" : t.from_label)}</div>
      <div class="as-sub">${what}</div><div class="as-btns">${btns}</div></div></div>`;
  }).join('') || '<div class="msg">This model draws with no textures (plain colours only).</div>';
  const usedBy = d.n_records > 1 ? `<details class="as-uses"><summary>Used by ${d.n_records} records, placed in ${d.places} place${d.places === 1 ? '' : 's'}</summary>${
    d.records.map(r => `<span class="as-rec">${esc(r.name || r.id)} <small>${esc(r.id)} · ${esc(r.type)}</small></span>`).join('')}</details>`
    : `<div class="as-sub">Only this record uses it${d.places ? `, placed in ${d.places} place${d.places === 1 ? '' : 's'}` : ''}.</div>`;
  box.innerHTML = `
    <div class="as-model">
      <div class="as-row"><b>${esc(d.model)}</b> ${fromTag(d.from, d.from === 'mod' ? "your mod's folder" : d.from_label)}</div>
      ${d.missing ? '<div class="msg err">The game can\'t find this model file.</div>' : `
      <div class="as-sub">${d.shapes} shape${d.shapes === 1 ? '' : 's'} · ${d.triangles.toLocaleString()} triangles · ${d.vertices.toLocaleString()} points${d.size ? ` · ${d.size[0]} × ${d.size[1]} × ${d.size[2]} units` : ''} · ${asKB(d.bytes)} · NIF ${esc((d.version || '').replace('Version ', ''))}</div>
      ${has ? `<div class="as-tags">${has}</div>` : ''}`}
      ${usedBy}
    </div>
    ${d.missing ? '' : asModelHtml(d)}
    <h3 style="margin:12px 0 6px">Textures <span class="msg">(${(d.textures || []).length})</span></h3>
    <div class="as-texs">${tex}</div>
    <div class="as-ed"><span>Textures open in</span><select class="inp" id="as-editor">
      <option value="">What Windows opens the file with</option>
      ${ed.found.map(f => `<option value="${esc(f.exe)}" ${f.exe === ed.chosen ? 'selected' : ''}>${esc(f.name)}</option>`).join('')}
      ${ed.chosen && !ed.found.some(f => f.exe === ed.chosen) ? `<option value="${esc(ed.chosen)}" selected>${esc(ed.chosen)}</option>` : ''}
      <option value="?">Another program…</option></select></div>
    <div class="as-sub" style="margin-top:4px">Each save shows in the 3D view while this window is open. GIMP, Paint.NET and Photoshop (DDS plug-in) open .dds files.</div>`;
  const sel = $('#as-editor');
  if (sel) sel.onchange = async () => {
    let exe = sel.value;
    if (exe === '?'){
      exe = await askText('The program to open textures in: its .exe, e.g. C:\\Program Files\\GIMP 2\\bin\\gimp-2.10.exe', ed.chosen || '');
      if (exe == null){ sel.value = ed.chosen || ''; return; }
    }
    try { await post('/api/settings', {image_editor: exe}); AS.editors.chosen = exe; asDraw(); asMsg(exe ? 'Textures open in ' + exe.split('\\').pop() + ' now.' : 'Textures open in what Windows chooses.'); }
    catch (e){ asMsg(e.message, true); sel.value = ed.chosen || ''; }
  };
}

// the model's own row: out to Blender, and back when it is saved there
function asModelHtml(d){
  const G = AS.glb, mine = d.from === 'mod';
  const out = AS.blender
    ? `<button class="btn sm primary" data-as="blender" title="Opens it in Blender; each save there (Ctrl+S) comes back here">⬡ Open in Blender</button>`
    : `<button class="btn sm primary" data-as="export" title="The model as a .glb (glTF binary) with its textures, for Blender or any 3D program">⬇ Export for Blender (.glb)</button>`;
  const lost = (G && G.lost && G.lost.length) ? `<div class="msg err" style="margin-top:4px">This model also has ${esc(G.lost.join(', '))}: those stay behind, so coming back it is shapes and textures only.</div>` : '';
  let state = '';
  if (G){
    state = `<div class="as-sub" style="margin-top:6px">Out at <span class="lnk" data-as="showfile">${esc(G.file.split('\\').pop())}</span>. ${G.blender
      ? 'Save in Blender (Ctrl+S) and it comes back here.' : 'In your 3D program, export it again as glTF binary over the same file and it comes back here.'}
      ${G.how ? ` It comes back <b>${G.how === 'own' ? 'as its own object' : 'everywhere'}</b>.` : ''}</div>${lost}`;
    if (G.pending && !G.how) state += `<div class="as-back"><b>The model changed.</b> Bring it back:
      <button class="btn sm primary" data-as="back" data-how="everywhere" title="Over the game's model, in your mod's folder: every object drawn with it changes">Everywhere</button>
      <button class="btn sm" data-as="back" data-how="own" title="As a new model and a new record of this object: nothing else changes">For this one only</button>
      <button class="btn sm" data-as="backno">Not now</button></div>`;
  }
  const anim = d.animated && typeof anShow === 'function' ? `<button class="btn sm" data-as="anim" title="Its animations played here, and its text keys (the groups and their sounds) to change">🎞 Animation & text keys…</button>` : '';
  return `<div class="as-btns" style="margin-top:10px">${out}${anim}${mine ? `<button class="btn sm" data-as="giveback-model" title="Take your copy of the model out of the mod (to the Recycle Bin); the game draws its own again">↺ The game's own model again</button>` : ''}</div>${state}`;
}

async function asBack(how){
  const G = AS.glb; if (!G) return;
  try {
    asMsg('Bringing it back…');
    // (after the first return as its own object, each save goes over that same new model)
    const r = await post('/api/assets/import', {file: G.file, how, i: AS.ri, into: how === 'own' ? G.into : null});
    const first = !G.how;
    G.how = G.how || how; G.pending = false;
    if (how === 'own' && !G.into) G.into = r.path;
    if (how === 'own' && !first){ if (typeof v3ModelReload === 'function') v3ModelReload(r.ids || []); asMsg('Saved in Blender: drawn again.'); AS.data = await api('/api/assets/record?i=' + AS.ri); asDraw(); return; }
    if (typeof v3ModelReload === 'function') v3ModelReload(r.ids || []);
    if (typeof afterChange === 'function') afterChange();
    asMsg(how === 'own' ? `Back as ${r.id}: place it to see it${r.pictures_new ? `, with ${r.pictures_new} repainted texture${r.pictures_new === 1 ? '' : 's'}` : ''}.`
      : `Back: the 3D view draws it again${r.pictures_new ? `, with ${r.pictures_new} repainted texture${r.pictures_new === 1 ? '' : 's'}` : ''}.`);
    if (how === 'own'){ AS.ri = r.i != null ? r.i : AS.ri; }
    AS.data = await api('/api/assets/record?i=' + AS.ri); asDraw();
  } catch (e){ asMsg(e.message, true); }
}

function asMsg(t, err){ const m = $('#as-msg'); if (m){ m.className = 'msg' + (err ? ' err' : ''); m.textContent = t; } }

async function asClick(e){
  const b = e.target.closest('[data-as]'); if (!b) return;
  const d = AS.data, t = d.textures[+b.dataset.n], how = b.dataset.as;
  if (how === 'blender' || how === 'export'){
    try {
      asMsg(how === 'blender' ? 'Opening in Blender…' : 'Exporting…');
      const r = await post('/api/assets/export', {i: AS.ri, blender: how === 'blender'});
      AS.glb = {file: r.file, stamp: r.stamp, lost: r.lost, blender: !!r.blender, how: null, pending: false};
      asWatch(); asDraw();
      asMsg(how === 'blender' ? 'Opened in Blender.' : `Exported with ${r.pictures} texture${r.pictures === 1 ? '' : 's'}: open it in your 3D program (File ▸ Import ▸ glTF).`);
    } catch (er){ asMsg(er.message, true); }
    return;
  }
  if (how === 'showfile') return post('/api/assets/showfile', {file: AS.glb.file}).catch(er => asMsg(er.message, true));
  if (how === 'anim') return anShow(AS.ri, (d.name || d.id) + ': animation & text keys');
  if (how === 'back'){ if (!await needProject()) return; return asBack(b.dataset.how); }
  if (how === 'backno'){ AS.glb.pending = false; asDraw(); return; }
  if (how === 'giveback-model'){
    if (!confirm(`Take your copy of ${d.model} out of your mod?\n\nIt goes to the Recycle Bin, and the game draws its own model again.`)) return;
    try {
      const r = await post('/api/assets/giveback', {path: d.path});
      if (typeof v3ModelReload === 'function') v3ModelReload((d.records || []).map(x => x.id));
      AS.data = await api('/api/assets/record?i=' + AS.ri); asDraw(); asMsg('The game\'s own model again, from ' + r.now + '.');
    } catch (er){ asMsg(er.message, true); }
    return;
  }
  if (how === 'find'){
    try { AS.found[t.name] = (await api('/api/assets/findtex?name=' + encodeURIComponent(t.name))).found; asDraw(); } catch (er){ asMsg(er.message, true); }
    return;
  }
  if (how === 'fixto'){
    if (!await needProject()) return;
    const own = !confirm(`Point ${d.model} at ${b.dataset.to}?\n\nOK: everywhere (your mod gets a copy of the model, so every object drawn with it is fixed).\nCancel: for this one only (a new model and record).`);
    try {
      const r = await post('/api/assets/fixtex', {i: AS.ri, name: t.name, to: b.dataset.to, how: own ? 'own' : 'everywhere'});
      if (typeof v3ModelReload === 'function') v3ModelReload(own ? [r.id] : (d.records || []).map(x => x.id));
      if (typeof afterChange === 'function') afterChange();
      if (own && r.i != null) AS.ri = r.i;
      AS.data = await api('/api/assets/record?i=' + AS.ri); AS.found = {}; asDraw();
      asMsg(own ? `Made ${r.id}, drawn with ${b.dataset.to}.` : 'Fixed in your copy of the model.');
    } catch (er){ asMsg(er.message, true); }
    return;
  }
  if (how === 'everywhere' || how === 'own'){
    if (!await needProject()) return;
    if (how === 'everywhere' && !confirm(`Change ${t.name} everywhere?\n\nA copy goes into your mod's own folder under the same name, so the game draws your copy wherever this texture is used, on other objects too. "The game's own again" takes it back out.`)) return;
    try {
      asMsg('Copying…');
      const r = await post('/api/assets/edit', {path: t.path, how, i: AS.ri});
      AS.watch[r.path] = {file: r.file, stamp: r.stamp, path: r.path, shown: t.path};
      asWatch();
      if (how === 'own'){
        asMsg(`Made ${r.id}, drawn with its own copy of the texture. It opened in your picture editor; place ${r.id} to see it.`);
        if (typeof afterChange === 'function') afterChange();
      } else {
        asMsg(`Your copy opened in ${r.editor ? r.editor.split('\\').pop() : 'your picture editor'}. Save it there, and the 3D view draws it again.`);
        AS.data = await api('/api/assets/record?i=' + AS.ri); asDraw();
      }
    } catch (er){ asMsg(er.message, true); }
  } else if (how === 'open'){
    try { const r = await post('/api/assets/open', {file: t.file}); AS.watch[t.path] = AS.watch[t.path] || {file: t.file, stamp: null, path: t.path, shown: t.path}; asWatch(); asMsg('Opened ' + (r.editor ? 'in ' + r.editor.split('\\').pop() : 'your copy') + '.'); }
    catch (er){ asMsg(er.message, true); }
  } else if (how === 'giveback'){
    if (!confirm(`Take your copy of ${t.name} out of your mod?\n\nIt goes to the Recycle Bin, and the game draws its own texture again.`)) return;
    try {
      const r = await post('/api/assets/giveback', {path: t.path});
      delete AS.watch[t.path];
      if (typeof v3TexReload === 'function') v3TexReload(t.path);
      AS.data = await api('/api/assets/record?i=' + AS.ri); asDraw();
      asMsg('The game\'s own texture again, from ' + r.now + '.');
    } catch (er){ asMsg(er.message, true); }
  }
}

// (a look every two seconds at the copies being edited; a save redraws the picture here and in the 3D view)
function asWatch(){
  if (AS.timer) return;
  AS.timer = setInterval(async () => {
    const w = Object.values(AS.watch), G = AS.glb; if ((!w.length && !G) || !AS.bg) return;
    const files = w.map(x => x.file).concat(G ? [G.file] : []);
    let st; try { st = await api('/api/assets/stamp?files=' + encodeURIComponent(files.join('|'))); } catch (e){ return; }
    // (the model back from Blender: asked the first time, then the same way at every save)
    if (G && st[G.file] && G.stamp && st[G.file] !== G.stamp){
      G.stamp = st[G.file];
      if (G.how) asBack(G.how); else { G.pending = true; asDraw(); asMsg('The model changed: bring it back?'); }
    } else if (G && st[G.file]) G.stamp = st[G.file];
    let changed = false;
    for (const x of w){
      const s = st[x.file];
      if (s && x.stamp && s !== x.stamp){ changed = true; if (typeof v3TexReload === 'function') v3TexReload(x.path); asMsg('Saved: drawn again.'); }
      if (s) x.stamp = s;
    }
    if (changed) asDraw();
  }, 2000);
}

function asCss(){
  if ($('#as-css')) return;
  const c = document.createElement('style'); c.id = 'as-css';
  c.textContent = `
  .as-win{width:min(760px,94vw);max-height:88vh;overflow:auto}
  .as-model{border:1px solid var(--line);border-radius:8px;padding:10px 12px;background:var(--panel2)}
  .as-row{display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-size:13px}
  .as-sub{font-size:12px;color:var(--muted);margin-top:3px}
  .as-tags{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px}
  .as-tag{font-size:11.5px;border:1px solid var(--line2);border-radius:10px;padding:1px 8px;color:var(--text)}
  .as-from{font-size:11px;border-radius:4px;padding:1px 6px;background:var(--hover);color:var(--muted);white-space:nowrap}
  .as-from-mod{background:color-mix(in srgb,var(--green) 22%,var(--panel));color:var(--text)}
  .as-from-library{background:color-mix(in srgb,var(--blue) 22%,var(--panel));color:var(--text)}
  .as-from-none{background:color-mix(in srgb,var(--red) 22%,var(--panel));color:var(--text)}
  .as-uses{margin-top:6px;font-size:12px}.as-uses summary{cursor:pointer;color:var(--muted)}
  .as-rec{display:inline-block;margin:3px 8px 0 0}.as-rec small{color:var(--faint)}
  .as-texs{display:flex;flex-direction:column;gap:8px}
  .as-tex{display:grid;grid-template-columns:72px 1fr;gap:10px;align-items:center;border:1px solid var(--line);border-radius:8px;padding:6px}
  .as-pic{width:72px;height:72px;object-fit:cover;border-radius:6px;background:#000;image-rendering:auto}
  .as-pic.none{display:flex;align-items:center;justify-content:center;font-size:11px;color:var(--faint);background:var(--hover)}
  .as-texname{font-size:13px;display:flex;gap:6px;align-items:center;flex-wrap:wrap;word-break:break-all}
  .as-btns{display:flex;gap:5px;flex-wrap:wrap;margin-top:5px}
  .as-ed{display:flex;gap:8px;align-items:center;margin-top:12px;font-size:12.5px}.as-ed select{width:auto;min-width:240px}
  .as-back{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-top:8px;padding:6px 8px;border-radius:6px;border:1px solid var(--gold);background:var(--hl);font-size:12.5px}`;
  document.head.appendChild(c);
}
