// ---------- Animation & text keys: a creature's or a moving object's animations played, its text keys edited ----------
// Opened from the asset window (assets.js) when the model moves. The model is built as the game builds it:
// its node tree as bones, skinned shapes bent by them (each bone's place times its skin transform), other
// shapes riding on their nodes; the keyframes (the .kf beside a creature's x-model, or the model's own)
// move the bones. The text keys name the groups (Idle, WalkForward, Attack1…) and time the sounds; they can
// be changed, added and taken out, and saved everywhere (over the game's file, in your mod's folder) or as
// a new copy of the creature with its own files (nifanim.py).
// People move with layers, as the game puts them together: everyone's animation, the women's or beast folk's,
// then their own model's; each group comes from the last file that has it, and its text keys are that
// file's. "For this person only" puts a group into their own animation file (their own model). A group's
// motion goes to Blender and comes back as keyframes (animglb.py).
const AN = {d: null, ri: null, bg: null, three: null, t: 0, playing: false, speed: 1, group: null, keys: [], dirty: false, raf: 0,
  src: null, cache: {}, motion: null, timer: 0, blender: null, people: null, ptrial: null};

// (a freshly read animation in place: its keys, its layers, the group shown)
function anSet(d, groupName){
  AN.d = d; AN.keys = d.keys.map(k => ({t: k[0], text: k[1]})); AN.dirty = false;
  AN.src = d.src != null ? d.src : null; AN.cache = {};
  if (AN.src != null) AN.cache[AN.src] = {tracks: d.tracks, keys: d.keys, length: d.length};
  AN.group = (groupName && d.groups.find(g => g.name.toLowerCase() === groupName.toLowerCase())) || d.groups.find(g => /^idle$/i.test(g.name)) || d.groups[0] || null;
  AN.t = AN.group ? AN.group.start : 0;
}

// a group picked: for a person, its layer's tracks and keys first (read once, when first wanted)
async function anPick(g){
  const d = AN.d;
  if (d.sources && g.src != null && g.src !== AN.src){
    if (AN.dirty && !confirm(`${g.name} is in ${d.sources[g.src].label} animation file. Drop your text key changes in this one?`)) return;
    try {
      if (!AN.cache[g.src]){ anMsg('Reading ' + d.sources[g.src].file.replace('meshes/', '') + '…'); const s = await api('/api/anim/source?file=' + encodeURIComponent(d.sources[g.src].file)); AN.cache[g.src] = s; anMsg(''); }
    } catch (e){ return anMsg(e.message, true); }
    const s = AN.cache[g.src];
    d.tracks = s.tracks; d.length = s.length; d.keyfile = d.sources[g.src].file; AN.src = g.src;
    AN.keys = s.keys.map(k => ({t: k[0], text: k[1]})); AN.dirty = false;
  }
  AN.group = g; AN.t = g.start; AN.playing = true; anDraw(); anBuild(true);
}

async function anReload(i, groupName){
  if (i != null) AN.ri = i;
  const d = await api('/api/anim/record?i=' + AN.ri);
  const want = groupName && d.groups.find(g => g.name.toLowerCase() === groupName.toLowerCase());
  anSet(d);
  if (want && want.src !== AN.src) return anPick(want);
  if (want) AN.group = want, AN.t = want.start;
  anDraw(); anBuild(true);
}

async function anShow(ri, label){
  AN.ri = ri;
  if (AN.bg) anClose();
  const bg = document.createElement('div'); bg.className = 'modal-bg'; AN.bg = bg;
  bg.innerHTML = `<div class="modal an-win"><h2>🎞 ${esc(label || 'Animation')}</h2><div id="an-body"><div class="msg"><span class="spin"></span>Reading the animation…</div></div>
    <div class="actions" style="margin-top:8px"><span class="msg" id="an-msg" style="flex:1"></span><button class="btn" id="an-close">Close</button></div></div>`;
  document.body.appendChild(bg);
  // (the asset window it came from steps aside, and comes back on Close)
  AN.under = typeof AS !== 'undefined' && AS.bg ? AS.bg : null;
  if (AN.under) AN.under.style.display = 'none';
  anCss();
  bg.querySelector('#an-close').onclick = anClose;
  try {
    await ensureThree();
    const [d, bl] = await Promise.all([api('/api/anim/record?i=' + ri), api('/api/assets/blenderhere').catch(() => ({blender: null}))]);
    AN.blender = bl.blender; AN.motion = null; AN.ptrial = null; AN.trial = null; AN.own = null;
    anSet(d); AN.playing = true;
    anDraw();
    anBuild();
  } catch (e){ const b = $('#an-body'); if (b) b.innerHTML = `<div class="msg err">${esc(e.message)}</div>`; }
}

function anClose(){
  if (AN.dirty && !confirm('Close without saving your changes to the text keys?')) return;
  if (AN.motion && !confirm('Stop watching for Blender saving the motion? Saves after this are not brought back.')) return;
  cancelAnimationFrame(AN.raf); AN.raf = 0;
  clearInterval(AN.timer); AN.timer = 0; AN.motion = null;
  if (AN.three){ AN.three.renderer.dispose(); AN.three = null; }
  if (AN.bg) AN.bg.remove(); AN.bg = null;
  if (AN.under){ AN.under.style.display = ''; AN.under = null; }
}

function anMsg(t, err){ const m = $('#an-msg'); if (m){ m.className = 'msg' + (err ? ' err' : ''); m.textContent = t; } }

// ----- the page ---------------------------------------------------------------------------------------
function anDraw(){
  const d = AN.d, box = $('#an-body'); if (!box) return;
  const G = d.groups;
  box.innerHTML = `<div class="an-grid">
    <div class="an-view"><canvas id="an-cv"></canvas><div class="an-hint">Drag to turn, wheel to zoom</div></div>
    <div class="an-side">
      <div class="an-h">Animation groups <span class="msg">(${G.length})</span></div>
      <div class="an-groups">${G.map((g, n) => `<button class="an-g ${AN.group === g ? 'on' : ''}${d.sources && g.src ? ' src' : ''}" data-ang="${n}" title="${g.start.toFixed(2)}–${g.stop.toFixed(2)} s${d.sources ? ' · from ' + esc(d.sources[g.src].label) + ' animation' : ''}">${esc(g.name)}</button>`).join('') ||
        '<span class="msg">No groups named: it plays from start to end.</span>'}</div>
      ${d.sources && d.sources.length > 1 ? `<div class="msg" style="font-size:11.5px;margin-top:3px">Layers: ${d.sources.map((s, n) => `<span class="${n ? 'an-lay' : ''}">${esc(s.label)}</span>`).join(' ▸ ')}. Dashed groups come from a later layer.</div>` : ''}
      <div class="an-play">
        <button class="btn sm" id="an-pp">${AN.playing ? '⏸ Pause' : '▶ Play'}</button>
        <label class="msg">Speed <select class="inp" id="an-speed">${[0.25, 0.5, 1, 2].map(v => `<option value="${v}" ${v === AN.speed ? 'selected' : ''}>${v}×</option>`).join('')}</select></label>
        <span class="msg" id="an-time"></span>
      </div>
      <div class="an-track" id="an-track"><div class="an-cursor" id="an-cursor"></div></div>
      ${AN.group && d.keyfile && !AN.trial ? `<div class="an-tools">
        <span class="msg">${esc(AN.group.name)}:</span>
        <button class="btn sm" id="an-trim-a" title="This group starts at the time shown (its Start key moves here)">⇤ Start here</button>
        <button class="btn sm" id="an-trim-b" title="This group stops at the time shown (its Stop key moves here)">Stop here ⇥</button>
        <span class="msg" style="margin-left:6px">Speed</span>
        <select class="inp" id="an-rate" title="Play the group faster or slower: the keyframes are moved, and the groups after it keep their timing">
          ${[['2', 'half speed'], ['1.5', '⅔ speed'], ['0.75', '1⅓× speed'], ['0.5', 'twice as fast']].map(([v, l]) => `<option value="${v}">${l}</option>`).join('')}</select>
        <button class="btn sm" id="an-rate-go">Apply…</button>
        ${/\.kf$/i.test(d.keyfile) && !AN.ptrial ? `<button class="btn sm" id="an-blender" title="${AN.blender ? 'This group\'s motion opens in Blender with the skeleton and body; each time you save there (Ctrl+S), the Workshop asks to bring it back' : 'Blender was not found: the motion is written as a .glb for any 3D program'}">${AN.blender ? '⬡ Edit in Blender' : '⬇ Motion as .glb'}</button>` : ''}</div>` : ''}
      ${AN.motion ? `<div class="an-tools an-bar">${AN.motion.pending
        ? `<span class="msg"><b>Blender saved ${esc(AN.motion.group)}.</b></span>
           ${AN.motion.how ? '' : `<button class="btn sm primary" data-anmo="everywhere" title="${d.type === 'NPC_' ? 'Over the animation file, for everyone who moves with it' : 'Every creature with this model moves this way'}">Bring it back everywhere</button>
           <button class="btn sm" data-anmo="own" title="${d.type === 'NPC_' ? 'Into this person\'s own animation: no one else changes' : 'A new copy of this creature with its own files'}">${d.type === 'NPC_' ? 'For this person only' : 'As its own…'}</button>`}
           <button class="btn sm" id="an-mo-x">Not this time</button>`
        : `<span class="msg">Watching for Blender saving ${esc(AN.motion.group)}${AN.motion.how ? ` (each save comes back ${AN.motion.how === 'own' ? 'as its own' : 'everywhere'})` : ''}…</span> <button class="btn sm" id="an-mo-stop">Stop watching</button>`}</div>` : ''}
      ${d.type === 'CREA' ? `<div class="an-tools">${AN.trial
        ? `<span class="msg"><b>Trying ${esc(AN.trial.name || AN.trial.id)}'s animation.</b></span>
           <button class="btn sm primary" data-anadopt="everywhere" title="Every creature with this model moves this way (your mod gets the animation file)">Keep it everywhere</button>
           <button class="btn sm" data-anadopt="own" title="A new copy of this creature that moves this way: nothing else changes">As its own…</button>
           <button class="btn sm" id="an-trial-x">Back to its own</button>`
        : `<div class="dd" style="flex:1;min-width:0"><input class="inp" id="an-adopt" placeholder="Try another creature's animation… (e.g. pack guar)" autocomplete="off"><div class="ddlist" id="an-adopt-l"></div></div>`}</div>` : ''}
      ${d.type === 'NPC_' ? `<div class="an-tools">${AN.ptrial
        ? `<span class="msg"><b>Trying ${esc(AN.ptrial.label)}.</b></span>
           <button class="btn sm primary" id="an-pkeep" title="This person's model (MODL) becomes it: no one else changes">Keep it for ${esc(d.name || d.id)}</button>
           <button class="btn sm" id="an-ptrial-x">Back</button>`
        : `<select class="inp" id="an-people" style="flex:1;min-width:0" title="Animations other people in the game move with (dancers, the dead, Khajiit…)"><option value="">Try another person's animation…</option>${(AN.people || []).filter(p => p.model !== d.modl).map(p => `<option value="${esc(p.model)}">${esc(p.model.replace(/\.nif$/i, ''))} · ${p.count} group${p.count === 1 ? '' : 's'} · ${esc(p.example)}${p.people > 1 ? ` and ${p.people - 1} more` : ''}${p.beast ? ' (beast folk)' : ''}</option>`).join('')}</select>
           ${d.modl ? `<button class="btn sm" id="an-pshared" title="Take their own model (${esc(d.modl)}) off: they move with the shared animation only">↺ The shared animation again</button>` : ''}`}</div>` : ''}
      ${d.shared && !AN.ptrial ? `<div class="msg" style="font-size:11.5px;margin-top:6px">${d.modl ? `${esc(d.name || d.id)} has an own model (${esc(d.modl)})${d.own ? ', one of your mod\'s that only they use' : ''}. ` : ''}Saving everywhere changes the file for everyone who moves with it; "For this person only" puts the group into ${esc(d.name || d.id)}'s own animation.</div>` : ''}
      <div class="an-h" style="margin-top:10px">Text keys <span class="msg">${d.keyfile ? `in ${esc(d.keyfile.replace('meshes/', ''))}${d.sources ? ` (${esc(d.sources[AN.src].label)})` : ''}` : '(none in this model)'}</span></div>
      <div class="an-keys" id="an-keys"></div>
      ${d.keyfile && !AN.ptrial ? `<div class="an-btns"><button class="btn sm" id="an-add" title="A new key at the time shown">＋ Key here</button>
        <span style="flex:1"></span>
        <button class="btn sm primary" id="an-save-all" ${AN.dirty ? '' : 'disabled'} title="${d.shared ? 'Over this file, in your mod\'s folder: everyone who moves with it changes' : 'Over the game\'s file, in your mod\'s folder: every creature with this animation changes'}">Save everywhere</button>
        <button class="btn sm" id="an-save-own" ${AN.dirty ? '' : 'disabled'} title="${d.shared ? 'The group shown goes into this person\'s own animation: no one else changes' : 'A new copy of this creature with its own files: nothing else changes'}">${d.shared ? 'For this person only' : 'Save as its own…'}</button></div>` : ''}
      ${(d.type === 'CREA' || d.type === 'NPC_') && !AN.trial && !AN.ptrial ? `<div class="an-btns"><label class="btn sm" title="An animation file made elsewhere (Blender's NIF tools, another mod): checked against this skeleton, then given to ${d.type === 'NPC_' ? 'this person as their own' : 'this creature'}">📂 Bring in a .kf…<input type="file" id="an-kf" accept=".kf" hidden></label></div>` : ''}
      <div class="msg" style="font-size:11.5px;margin-top:6px">Keys are "Group: Start", "Group: Loop Start", "Group: Loop Stop", "Group: Stop", and sounds: "SoundGen: Left" (the creature's footstep, moan, roar…) or "Sound: <sound id>".</div>
    </div></div>`;
  anKeysDraw(); anTrackDraw();
  box.querySelectorAll('[data-ang]').forEach(b => b.onclick = () => anPick(G[+b.dataset.ang]));
  const bl = $('#an-blender'); if (bl) bl.onclick = () => anBlender();
  box.querySelectorAll('[data-anmo]').forEach(b => b.onclick = () => anMotionBack(b.dataset.anmo));
  const mx = $('#an-mo-x'); if (mx) mx.onclick = () => { AN.motion.pending = false; anDraw(); anBuild(true); };
  const ms = $('#an-mo-stop'); if (ms) ms.onclick = () => { clearInterval(AN.timer); AN.timer = 0; AN.motion = null; anDraw(); anBuild(true); };
  const pp = $('#an-people');
  if (pp){
    if (!AN.people) api('/api/anim/people').then(r => { AN.people = r.rows; if ($('#an-people')) anDraw(), anBuild(true); }).catch(() => {});
    pp.onchange = () => { if (pp.value) anPersonTry(pp.value); };
  }
  const pk = $('#an-pkeep'); if (pk) pk.onclick = () => anPersonKeep(AN.ptrial.model);
  const px = $('#an-ptrial-x'); if (px) px.onclick = () => { AN.ptrial = null; anReload(null, AN.group && AN.group.name); };
  const psh = $('#an-pshared'); if (psh) psh.onclick = () => { if (confirm(`Take ${AN.d.name || AN.d.id}'s own model (${AN.d.modl}) off, so they move with the shared animation only?`)) anPersonKeep(''); };
  const kfin = $('#an-kf'); if (kfin) kfin.onchange = () => { if (kfin.files[0]) anBringKf(kfin.files[0]); };
  $('#an-pp').onclick = () => { AN.playing = !AN.playing; $('#an-pp').textContent = AN.playing ? '⏸ Pause' : '▶ Play'; };
  $('#an-speed').onchange = e => { AN.speed = +e.target.value; };
  const tr = $('#an-track');
  tr.onpointerdown = e => { const r = tr.getBoundingClientRect(), [a, b] = anSpan(); AN.t = a + (b - a) * Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)); AN.playing = false; $('#an-pp').textContent = '▶ Play'; };
  const add = $('#an-add'); if (add) add.onclick = () => { AN.keys.push({t: +AN.t.toFixed(3), text: AN.group ? AN.group.name + ': ' : 'SoundGen: Left'}); AN.dirty = true; anKeysDraw(); anTrackDraw(); anSaveBtns(); const last = $('#an-keys').querySelector('tr:last-child input[data-ank="text"]'); if (last) last.focus(); };
  const sa = $('#an-save-all'); if (sa) sa.onclick = () => anSave('everywhere');
  const so = $('#an-save-own'); if (so) so.onclick = () => anSave('own');
  // trimming: the group's own Start (and Loop Start, where it was the same) or Stop key moved to the cursor
  const trim = which => {
    const g = AN.group, name = g.name.toLowerCase(), t = +AN.t.toFixed(3);
    if (which === 'start' ? t >= g.stop : t <= g.start) return anMsg(which === 'start' ? 'The start must come before the stop.' : 'The stop must come after the start.', true);
    const re = which === 'start' ? /^(.+?):\s*(start|loop start)\s*$/i : /^(.+?):\s*(stop|loop stop)\s*$/i;
    // (a loop key moves too when it sat on the old start or stop, or would fall outside the group now)
    const outside = v => which === 'start' ? v < t : v > t;
    for (const k of AN.keys){
      const m = k.text.match(re); if (!m || m[1].trim().toLowerCase() !== name) continue;
      const loop = m[2].toLowerCase().startsWith('loop');
      if (!loop || Math.abs(k.t - g[which]) < 1e-3 || outside(k.t)) k.t = t;
    }
    const lk = 'loop_' + which;
    if (g[lk] != null && (Math.abs(g[lk] - g[which]) < 1e-3 || outside(g[lk]))) g[lk] = t;
    g[which] = t;
    AN.dirty = true; anKeysDraw(); anTrackDraw(); anSaveBtns(); anMsg(`${g.name} now ${which === 'start' ? 'starts' : 'stops'} at ${t.toFixed(2)} s: save to keep it.`);
  };
  const ta = $('#an-trim-a'); if (ta) ta.onclick = () => trim('start');
  const tb = $('#an-trim-b'); if (tb) tb.onclick = () => trim('stop');
  const rg = $('#an-rate-go'); if (rg) rg.onclick = () => anRetime(+$('#an-rate').value);
  // another creature's animation, tried on this skeleton
  if ($('#an-adopt') && typeof ddSearch === 'function') ddSearch('an-adopt', 'CREA', x => anTry(x));
  const tx = $('#an-trial-x'); if (tx) tx.onclick = () => { anTrialEnd(); };
  box.querySelectorAll('[data-anadopt]').forEach(b => b.onclick = () => anAdopt(b.dataset.anadopt));
}

async function anRetime(factor){
  if (!await needProject()) return;
  if (AN.dirty) return anMsg('Save or drop your text key changes first.', true);
  const g = AN.group, slower = factor > 1 ? 'slower' : 'faster', person = !!AN.d.shared;
  const own = !confirm(person
    ? `Make ${g.name} ${slower} for everyone who moves with ${AN.d.keyfile.replace('meshes/', '')}?\n\nOK: everyone (your mod gets the file).\nCancel: for ${AN.d.name || AN.d.id} only (their own animation).`
    : `Make ${g.name} ${slower} everywhere?\n\nOK: everywhere (your mod gets the animation file; every one using it changes).\nCancel: as a new copy of this one with its own files.`);
  try {
    const r = await post('/api/anim/retime', {i: AN.ri, group: g.name, factor, how: own ? 'own' : 'everywhere'});
    await anReload(own && r.i != null ? r.i : null, g.name);
    if (typeof afterChange === 'function') afterChange();
    const len = (r.group.stop - r.group.start).toFixed(2);
    anMsg(own ? (person ? `${g.name} now lasts ${len} s for ${AN.d.name || AN.d.id} only.` : `Made ${r.id}: ${g.name} now lasts ${len} s.`) : `${g.name} now lasts ${len} s.`);
  } catch (e){ anMsg(e.message, true); }
}

// ----- a person's own animation: another person's tried and kept ---------------------------------------
async function anPersonTry(model){
  try {
    anMsg('Reading ' + model + '…');
    const d = await api('/api/anim/record?i=' + AN.ri + '&modl=' + encodeURIComponent(model));
    const p = (AN.people || []).find(x => x.model === model);
    const keep = AN.group && AN.group.name;
    anSet(d, keep);
    // (show one of the groups the other animation brings, where there is one)
    const theirs = d.groups.filter(g => g.src === d.sources.length - 1 && d.sources[g.src].model === model);
    AN.ptrial = {model, label: model.replace(/\.nif$/i, '') + (p ? ` (${p.example}'s)` : '')};
    if (theirs.length && !theirs.includes(AN.group)) return anPick(theirs[0]).then(() => anMsg(`Trying ${model}: dashed groups are its own.`));
    AN.playing = true; anDraw(); anBuild(true);
    anMsg(`Trying ${model}: dashed groups are its own.`);
  } catch (e){ anMsg(e.message, true); }
}

async function anPersonKeep(model){
  if (!await needProject()) return;
  try {
    const r = await post('/api/anim/personadopt', {i: AN.ri, model});
    AN.ptrial = null;
    await anReload(r.i, AN.group && AN.group.name);
    if (typeof afterChange === 'function') afterChange();
    anMsg(model ? `${AN.d.name || AN.d.id} now moves with ${model} (${r.matched} of ${r.bones} bones match).` : `${AN.d.name || AN.d.id} moves with the shared animation again.`);
  } catch (e){ anMsg(e.message, true); }
}

// ----- an animation file brought in ---------------------------------------------------------------------
async function anBringKf(file){
  if (!await needProject()) return;
  const person = AN.d.type === 'NPC_';
  const how = person ? 'own' : (confirm(`Give ${AN.d.name || AN.d.id} the animation in ${file.name} everywhere?\n\nOK: everywhere (every creature with this model moves this way).\nCancel: as a new copy of this creature.`) ? 'everywhere' : 'own');
  if (person && !confirm(`Give ${AN.d.name || AN.d.id} the animation in ${file.name} as their own?\n\nIts groups play over the shared animation; no one else changes.`)) return;
  try {
    anMsg('Reading ' + file.name + '…');
    const buf = new Uint8Array(await file.arrayBuffer());
    let bin = ''; for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
    const r = await post('/api/anim/bringkf', {i: AN.ri, data: btoa(bin), how});
    await anReload(how === 'own' && r.i != null ? r.i : null, r.groups && r.groups[0]);
    if (typeof afterChange === 'function') afterChange();
    anMsg(`${how === 'own' && !person ? 'Made ' + r.id + ', moving' : (AN.d.name || AN.d.id) + ' now moves'} with ${file.name}: ${r.groups.length} group${r.groups.length === 1 ? '' : 's'} (${r.groups.slice(0, 4).join(', ')}${r.groups.length > 4 ? '…' : ''}), ${r.matched} of ${r.bones} bones found.`);
  } catch (e){ anMsg(e.message, true); }
}

// ----- a group's motion to Blender and back ---------------------------------------------------------------
async function anBlender(){
  const g = AN.group; if (!g) return;
  try {
    anMsg(AN.blender ? 'Opening the motion in Blender…' : 'Writing the motion…');
    const r = await post('/api/anim/blender', {i: AN.ri, group: g.name, open: !!AN.blender});
    AN.motion = {file: r.file, stamp: r.stamp, group: r.group, how: null, ri: AN.ri, pending: false};
    anWatch(); anDraw(); anBuild(true);
    anMsg(AN.blender ? `${g.name} is open in Blender (${r.bones} bones, ${r.frames} frames). Change it there and save (Ctrl+S).`
      : `Written: ${r.file}. Open it in your 3D program (File ▸ Import ▸ glTF), and save it back over the same file as .glb.`);
  } catch (e){ anMsg(e.message, true); }
}

// (a look every two seconds at the file Blender saves over; asked the first time, then the same way each save)
function anWatch(){
  if (AN.timer) return;
  AN.timer = setInterval(async () => {
    const M = AN.motion; if (!M || !AN.bg || M.pending || M.busy) return;
    let st; try { st = await api('/api/assets/stamp?files=' + encodeURIComponent(M.file)); } catch (e){ return; }
    if (!st[M.file] || st[M.file] === M.stamp) return;
    M.stamp = st[M.file];
    if (M.how) return anMotionBack(M.how);
    M.pending = true; anDraw(); anBuild(true);
  }, 2000);
}

async function anMotionBack(how){
  const M = AN.motion; if (!M) return;
  if (!await needProject()) return;
  const person = AN.d.type === 'NPC_';
  if (how === 'everywhere' && !M.how && person && !confirm(`Bring ${M.group} back over ${AN.d.keyfile.replace('meshes/', '')}?\n\nEveryone who moves with that file changes.`)) return;
  try {
    M.busy = true; anMsg('Bringing the motion back…');
    const r = await post('/api/anim/motion', {i: M.ri, file: M.file, how});
    // (later saves: a person's own file again; a new creature copy's own files, over them)
    if (how === 'own' && !person && r.i != null){ M.ri = r.i; M.how = 'everywhere'; } else M.how = how;
    if (person && r.i != null) M.ri = r.i;            // (their record, now the mod's own copy of it)
    M.pending = false;
    await anReload(M.ri, M.group);
    if (typeof afterChange === 'function') afterChange();
    anMsg(`${M.group} came back from Blender: ${r.bones} bones, ${r.length.toFixed(2)} s${r.missing && r.missing.length ? ` (${r.missing.length} bone${r.missing.length === 1 ? '' : 's'} with no track left out: ${r.missing.slice(0, 3).join(', ')})` : ''}${how === 'own' && !person && r.id ? `, as ${r.id}` : ''}.`);
  } catch (e){ anMsg(e.message, true); }
  if (AN.motion) AN.motion.busy = false;
}

async function anTry(x){
  try {
    let i = x.i;
    if (i == null){ const s = await api('/api/search?q=' + encodeURIComponent(x.id) + '&types=CREA&limit=20'); const h = s.rows.find(r => r.id.toLowerCase() === x.id.toLowerCase()); i = h && h.i; }
    if (i == null) return anMsg('That creature was not found.', true);
    const o = await api('/api/anim/tracks?i=' + i);
    const mine = new Set(AN.d.tree.nodes.map(n => n.name.toLowerCase())), names = Object.keys(o.tracks);
    const hit = names.filter(n => mine.has(n.toLowerCase())).length;
    if (!names.length || hit < 0.8 * names.length) return anMsg(`${o.name || o.id}'s animation moves bones this one hasn't (${hit} of ${names.length} match).`, true);
    AN.own = AN.own || {tracks: AN.d.tracks, keys: AN.keys, groups: AN.d.groups, length: AN.d.length};
    AN.trial = {i, id: o.id, name: o.name};
    AN.d.tracks = o.tracks; AN.d.groups = o.groups; AN.d.length = o.length; AN.keys = o.keys.map(k => ({t: k[0], text: k[1]}));
    AN.group = o.groups.find(g => /^idle$/i.test(g.name)) || o.groups[0] || null; AN.t = AN.group ? AN.group.start : 0; AN.playing = true;
    anDraw(); anBuild(true);
    anMsg(`Trying ${o.name || o.id}'s animation on this one. Keep it, or go back.`);
  } catch (e){ anMsg(e.message, true); }
}

function anTrialEnd(){
  if (!AN.own) return;
  Object.assign(AN.d, {tracks: AN.own.tracks, groups: AN.own.groups, length: AN.own.length}); AN.keys = AN.own.keys;
  AN.own = null; AN.trial = null;
  AN.group = AN.d.groups.find(g => /^idle$/i.test(g.name)) || AN.d.groups[0] || null; AN.t = AN.group ? AN.group.start : 0;
  anDraw(); anBuild(true); anMsg('');
}

async function anAdopt(how){
  if (!await needProject()) return;
  const T = AN.trial; if (!T) return;
  if (how === 'everywhere' && !confirm(`Give ${AN.d.name || AN.d.id} ${T.name || T.id}'s animation everywhere?\n\nYour mod gets the animation file, so every creature with this model moves this way.`)) return;
  try {
    const r = await post('/api/anim/adopt', {i: AN.ri, from: T.i, how});
    AN.own = null; AN.trial = null;
    await anReload(how === 'own' && r.i != null ? r.i : null);
    if (typeof afterChange === 'function') afterChange();
    anMsg(how === 'own' ? `Made ${r.id}, moving with ${T.name || T.id}'s animation (${r.matched} of ${r.bones} bones).` : `Now moves with ${T.name || T.id}'s animation (${r.matched} of ${r.bones} bones).`);
  } catch (e){ anMsg(e.message, true); }
}

function anSpan(){ return AN.group ? [AN.group.start, AN.group.stop] : [0, Math.max(0.1, AN.d.length)]; }

function anKeysDraw(){
  const box = $('#an-keys'); if (!box) return;
  const [a, b] = anSpan();
  const order = AN.keys.map((k, n) => [k, n]).sort((x, y) => x[0].t - y[0].t);
  // (the keys of the group shown first; the rest folded under)
  const inG = order.filter(([k]) => k.t >= a - 1e-4 && k.t <= b + 1e-4), rest = order.filter(([k]) => !(k.t >= a - 1e-4 && k.t <= b + 1e-4));
  const row = ([k, n]) => `<tr><td><input class="inp num" data-ank="t" data-n="${n}" value="${k.t}" ${AN.d.keyfile ? '' : 'disabled'}></td>
    <td><input class="inp" data-ank="text" data-n="${n}" value="${esc(k.text)}" ${AN.d.keyfile ? '' : 'disabled'}></td>
    <td>${AN.d.keyfile ? `<button class="btn sm" data-ankx="${n}" title="Take this key out">✕</button>` : ''}</td></tr>`;
  box.innerHTML = `<table class="an-table">${inG.map(row).join('')}</table>${rest.length ? `<details class="an-rest"><summary>${rest.length} more key${rest.length === 1 ? '' : 's'} in other groups</summary><table class="an-table">${rest.map(row).join('')}</table></details>` : ''}`;
  box.oninput = e => {
    const el = e.target, n = +el.dataset.n; if (!el.dataset.ank) return;
    if (el.dataset.ank === 't'){ const v = parseFloat(el.value); if (!isFinite(v) || v < 0) return; AN.keys[n].t = v; }
    else AN.keys[n].text = el.value;
    AN.dirty = true; anSaveBtns(); anTrackDraw();
  };
  box.onclick = e => { const x = e.target.closest('[data-ankx]'); if (x){ AN.keys.splice(+x.dataset.ankx, 1); AN.dirty = true; anKeysDraw(); anTrackDraw(); anSaveBtns(); } };
}

function anSaveBtns(){ for (const id of ['an-save-all', 'an-save-own']){ const b = $('#' + id); if (b) b.disabled = !AN.dirty; } }

// (the time line of the group shown, with a tick at each text key: sounds amber, the group's own keys gold)
function anTrackDraw(){
  const tr = $('#an-track'); if (!tr) return;
  const [a, b] = anSpan();
  tr.querySelectorAll('.an-tick').forEach(x => x.remove());
  for (const k of AN.keys){
    if (k.t < a - 1e-4 || k.t > b + 1e-4) continue;
    const el = document.createElement('div');
    el.className = 'an-tick' + (/^sound/i.test(k.text) ? ' snd' : '');
    el.style.left = (100 * (k.t - a) / Math.max(1e-4, b - a)) + '%';
    el.title = k.t.toFixed(3) + ' s · ' + k.text;
    tr.appendChild(el);
  }
}

async function anSave(how){
  if (!await needProject()) return;
  const person = !!AN.d.shared;
  if (how === 'everywhere' && !confirm(`Save the text keys over ${AN.d.keyfile}?\n\nYour mod gets its own copy of the file, so every ${person ? 'person who moves with it' : 'creature using this animation'} changes. "The game's own again" in the Model & textures window takes it back out.`)) return;
  if (how === 'own' && person && !AN.group) return anMsg('Pick the group to keep for this person.', true);
  try {
    const r = await post('/api/anim/textkeys', {i: AN.ri, keys: AN.keys.map(k => [k.t, k.text]), how, file: AN.d.keyfile, group: AN.group && AN.group.name});
    AN.dirty = false; anSaveBtns();
    if (typeof afterChange === 'function') afterChange();
    if (how === 'own' && person){ await anReload(r.i, AN.group.name); return anMsg(`${AN.group.name} is now ${AN.d.name || AN.d.id}'s own (in ${r.path.replace('meshes/', '')}).`); }
    anMsg(how === 'own' ? `Made ${r.id}, a copy with its own animation files: place it to use it.` : `Saved in your mod's copy of ${r.path.replace('meshes/', '')}.`);
  } catch (e){ anMsg(e.message, true); }
}

// ----- the 3D view: the skeleton, the shapes, the keyframes ---------------------------------------------
function anMat4(R, t, s){
  const m = new THREE.Matrix4();
  m.set(R[0][0] * s, R[0][1] * s, R[0][2] * s, t[0], R[1][0] * s, R[1][1] * s, R[1][2] * s, t[1], R[2][0] * s, R[2][1] * s, R[2][2] * s, t[2], 0, 0, 0, 1);
  return m;
}

function anBuild(keepView){
  const T = THREE, d = AN.d, cv = $('#an-cv'); if (!cv) return;
  let V = AN.three;
  if (!V || V.canvas !== cv){
    if (V) V.renderer.dispose();
    const renderer = new T.WebGLRenderer({canvas: cv, antialias: true});
    const scene = new T.Scene(); scene.background = new T.Color(0x24211c);
    const cam = new T.PerspectiveCamera(40, 1, 1, 50000); cam.up.set(0, 0, 1);
    scene.add(new T.HemisphereLight(0xfff4e0, 0x50453a, 0.9));
    const sun = new T.DirectionalLight(0xffffff, 0.7); sun.position.set(0.5, -1, 1.4); scene.add(sun);
    V = AN.three = {canvas: cv, renderer, scene, cam, yaw: -0.9, pitch: 0.25, dist: null, root: null};
    cv.addEventListener('pointerdown', e => { V.drag = [e.clientX, e.clientY]; cv.setPointerCapture(e.pointerId); });
    cv.addEventListener('pointerup', () => { V.drag = null; });
    cv.addEventListener('pointermove', e => { if (!V.drag) return; V.yaw -= (e.clientX - V.drag[0]) * 0.01; V.pitch = Math.max(-1.2, Math.min(1.4, V.pitch + (e.clientY - V.drag[1]) * 0.01)); V.drag = [e.clientX, e.clientY]; });
    cv.addEventListener('wheel', e => { e.preventDefault(); V.dist *= e.deltaY > 0 ? 1.15 : 1 / 1.15; }, {passive: false});
  }
  if (V.root) V.scene.remove(V.root);
  // the bones: one per node, with the node's own transform; the root's own is ignored, as the game does
  const bones = d.tree.nodes.map(n => { const b = new T.Bone(); b.name = n.name; anMat4(n.R, n.t, n.s).decompose(b.position, b.quaternion, b.scale); return b; });
  const root = new T.Group();
  d.tree.nodes.forEach((n, i) => { if (n.parent >= 0) bones[n.parent].add(bones[i]); else root.add(bones[i]); });
  V.scene.add(root); V.root = root; V.bones = bones;
  root.updateMatrixWorld(true);
  const mats = {};
  const mat = s => {
    const k = (s.tex || '') + (s.alpha ? 'a' : '');
    if (!mats[k]){
      const m = new T.MeshLambertMaterial({color: 0xcfc6b5, side: T.DoubleSide, alphaTest: s.alpha ? 0.5 : 0});
      if (s.tex && typeof v3Tex === 'function') v3Tex(s.tex, tx => { m.map = tx; m.color.setHex(0xffffff); m.needsUpdate = true; });
      mats[k] = m;
    }
    return mats[k];
  };
  for (const s of d.tree.shapes){
    const g = new T.BufferGeometry();
    g.setAttribute('position', new T.Float32BufferAttribute(s.p, 3));
    if (s.uv && s.uv.length === s.p.length / 3 * 2) g.setAttribute('uv', new T.Float32BufferAttribute(s.uv, 2));
    g.setIndex(s.i);
    g.computeVertexNormals();
    const sk = s.skin;
    if (sk && sk.inv && sk.inv.length && sk.bones.every(b => b >= 0)){
      // skinned: each vertex bent by up to four bones (the heaviest), as the game draws it
      const n = s.p.length / 3, si = new Uint16Array(n * 4), sw = new Float32Array(n * 4);
      for (let v = 0; v < n; v++){
        const ws = (sk.weights[v] || []).slice().sort((x, y) => y[1] - x[1]).slice(0, 4);
        const tot = ws.reduce((a, w) => a + w[1], 0) || 1;
        ws.forEach((w, k) => { si[v * 4 + k] = w[0]; sw[v * 4 + k] = w[1] / tot; });
        if (!ws.length) sw[v * 4] = 1;
      }
      g.setAttribute('skinIndex', new T.Uint16BufferAttribute(si, 4));
      g.setAttribute('skinWeight', new T.Float32BufferAttribute(sw, 4));
      const mesh = new T.SkinnedMesh(g, mat(s));
      const sb = sk.bones.map(b => bones[b]);
      const inv = sk.inv.map(x => anMat4(x.R, x.t, x.s));
      mesh.bind(new T.Skeleton(sb, inv), new T.Matrix4());
      mesh.frustumCulled = false;
      root.add(mesh);
    } else {
      const mesh = new T.Mesh(g, mat(s));
      if (s.M){
        // (a person's body part: its own placing in its file, mirrored for the left side, on its bone)
        const m = new T.Matrix4(); m.set(...s.M); mesh.matrixAutoUpdate = false; mesh.matrix.copy(m);
      } else anMat4(s.R, s.t, s.s).decompose(mesh.position, mesh.quaternion, mesh.scale);
      (s.node >= 0 ? bones[s.node] : root).add(mesh);
    }
  }
  // (a person's race: taller or broader than the skeleton)
  if (d.build) root.scale.set(d.build.weight || 1, d.build.weight || 1, d.build.height || 1);
  // the tracks, by bone
  V.tracks = [];
  const byName = {}; bones.forEach(b => { byName[b.name.toLowerCase()] = b; });
  for (const [name, k] of Object.entries(d.tracks)){
    const b = byName[name.toLowerCase()]; if (b) V.tracks.push({b, k});
  }
  anPose(AN.t);
  if (!keepView || V.dist == null){
    root.updateMatrixWorld(true);
    const box = new T.Box3().setFromObject(root), c = box.getCenter(new T.Vector3()), sz = box.getSize(new T.Vector3());
    V.center = c; V.dist = Math.max(80, Math.max(sz.x, sz.y, sz.z) * 1.8);
  }
  if (!AN.raf){ AN.last = performance.now(); AN.raf = requestAnimationFrame(anTick); }
}

function anLerpKeys(keys, t, f){
  if (!keys.length) return null;
  if (t <= keys[0][0]) return f(keys[0][1], keys[0][1], 0);
  for (let i = 0; i < keys.length - 1; i++){
    const a = keys[i], b = keys[i + 1];
    if (t >= a[0] && t <= b[0]) return f(a[1], b[1], (t - a[0]) / Math.max(1e-6, b[0] - a[0]));
  }
  const z = keys[keys.length - 1]; return f(z[1], z[1], 0);
}
let AN_QA = null, AN_QB = null;            // (two quaternions reused each frame; made once three.js is loaded)

function anPose(t){
  const V = AN.three; if (!V || !V.tracks) return;
  if (!AN_QA){ AN_QA = new THREE.Quaternion(); AN_QB = new THREE.Quaternion(); }
  for (const {b, k} of V.tracks){
    // (the file's keys are w, x, y, z)
    if (k.rot.length) anLerpKeys(k.rot, t, (p, q, f) => { AN_QA.set(p[1], p[2], p[3], p[0]); AN_QB.set(q[1], q[2], q[3], q[0]); b.quaternion.copy(AN_QA).slerp(AN_QB, f); });
    if (k.pos.length) anLerpKeys(k.pos, t, (p, q, f) => { b.position.set(p[0] + (q[0] - p[0]) * f, p[1] + (q[1] - p[1]) * f, p[2] + (q[2] - p[2]) * f); });
    if (k.scale.length) anLerpKeys(k.scale, t, (p, q, f) => { const s = p + (q - p) * f; b.scale.set(s, s, s); });
  }
}

function anTick(now){
  const V = AN.three; if (!V || !AN.bg){ AN.raf = 0; return; }
  const dt = Math.min(0.1, (now - AN.last) / 1000); AN.last = now;
  const [a, b] = anSpan();
  if (AN.playing){
    AN.t += dt * AN.speed;
    // (a group loops between its loop keys when it has them, else from start to stop)
    const g = AN.group, ls = g && g.loop_start != null ? g.loop_start : a, le = g && g.loop_stop != null ? g.loop_stop : b;
    if (AN.t > le) AN.t = ls + ((AN.t - ls) % Math.max(0.01, le - ls));
  }
  anPose(AN.t);
  const cv = V.canvas, w = cv.clientWidth, h = cv.clientHeight;
  if (cv.width !== Math.round(w * devicePixelRatio) || cv.height !== Math.round(h * devicePixelRatio)){ V.renderer.setPixelRatio(devicePixelRatio); V.renderer.setSize(w, h, false); V.cam.aspect = w / Math.max(1, h); V.cam.updateProjectionMatrix(); }
  const c = V.center || new THREE.Vector3();
  V.cam.position.set(c.x + Math.cos(V.yaw) * Math.cos(V.pitch) * V.dist, c.y + Math.sin(V.yaw) * Math.cos(V.pitch) * V.dist, c.z + Math.sin(V.pitch) * V.dist);
  V.cam.lookAt(c);
  V.renderer.render(V.scene, V.cam);
  const tm = $('#an-time'); if (tm) tm.textContent = `${AN.t.toFixed(2)} s${AN.group ? ` · ${AN.group.name} ${(AN.t - a).toFixed(2)} of ${(b - a).toFixed(2)}` : ''}`;
  const cur = $('#an-cursor'); if (cur) cur.style.left = (100 * Math.max(0, Math.min(1, (AN.t - a) / Math.max(1e-4, b - a)))) + '%';
  AN.raf = requestAnimationFrame(anTick);
}

function anCss(){
  if ($('#an-css')) return;
  const c = document.createElement('style'); c.id = 'an-css';
  c.textContent = `
  .an-win{width:min(1120px,96vw);max-height:92vh;overflow:auto}
  .an-grid{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(320px,1fr);gap:12px}
  .an-view{position:relative;min-height:440px;border:1px solid var(--line2);border-radius:8px;overflow:hidden;background:#24211c}
  .an-view canvas{position:absolute;inset:0;width:100%;height:100%;display:block;cursor:grab}
  .an-hint{position:absolute;left:8px;bottom:6px;font-size:11px;color:#ffffff88;pointer-events:none}
  .an-h{font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--faint);margin:2px 0 4px}
  .an-groups{display:flex;flex-wrap:wrap;gap:4px;max-height:132px;overflow:auto}
  .an-g{font:inherit;font-size:12px;padding:2px 8px;border:1px solid var(--line2);border-radius:10px;background:none;color:var(--text);cursor:pointer}
  .an-g.on{background:var(--hl);border-color:var(--gold);color:var(--gold2)}.an-g.src{border-style:dashed}.an-lay{color:var(--gold2)}
  .an-bar{border:1px solid var(--gold);border-radius:6px;padding:4px 6px;background:var(--hl)}
  .an-play{display:flex;gap:8px;align-items:center;margin-top:8px}.an-play select{width:auto;padding:1px 4px}
  .an-track{position:relative;height:22px;margin-top:6px;border:1px solid var(--line2);border-radius:4px;background:var(--panel2);cursor:pointer}
  .an-cursor{position:absolute;top:0;bottom:0;width:2px;background:var(--gold2)}
  .an-tick{position:absolute;top:3px;bottom:3px;width:2px;margin-left:-1px;background:var(--gold);opacity:.8}.an-tick.snd{background:var(--amber)}
  .an-keys{max-height:250px;overflow:auto;border:1px solid var(--line);border-radius:6px;padding:4px}
  .an-table{width:100%;border-collapse:collapse}.an-table td{padding:1px 3px}.an-table td:first-child{width:72px}.an-table td:last-child{width:30px}
  .an-table input{width:100%;padding:1px 5px;font-size:12px}
  .an-rest{margin-top:4px;font-size:12px}.an-rest summary{cursor:pointer;color:var(--muted)}
  .an-btns{display:flex;gap:6px;align-items:center;margin-top:6px}
  .an-tools{display:flex;gap:5px;align-items:center;flex-wrap:wrap;margin-top:6px}.an-tools select{width:auto;padding:1px 4px}`;
  document.head.appendChild(c);
}
