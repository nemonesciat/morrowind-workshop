// Secret entrances: the "Secret entrance" entries of the right-click menu on a placed object (map and 3D
// view) and their dialogs. The work is done by app/mechanism.py: a door to somewhere (an existing place,
// a new one copied from the game, or one built from pieces), an ordinary object again, a rotating panel
// (a door that swings on the edge you choose) and a sliding panel (an activator with a script, used
// directly or pulled by another object). Each is one change: one Undo takes it back.

function sdMenuItems(ck, r){
  const items = [];
  const scenery = ['STAT', 'ACTI', 'CONT', 'LIGH', 'MISC'].includes(r.type);    // (anything with a model: a log pile too)
  if (scenery || (r.type === 'DOOR' && !r.to)) items.push({label: '🚪 Make this a door to…', act: () => sdDoorTo(ck, r)});
  if (r.type === 'DOOR' || r.type === 'ACTI') items.push({label: '▭ Make this an ordinary object again', act: () => sdPlain(ck, r)});
  items.push({label: '↪ Rotating panel…', act: () => sdSwing(ck, r)});
  items.push({label: '⇆ Sliding panel…', act: () => sdSlide(ck, r)});
  return items;
}

// A box with a title, a form, Cancel and one primary button. bind(bg) runs once the box is in the page;
// go(bg) runs on the button (throw to show a message and stay; return false to stay quietly).
function sdDialog(title, html, okLabel, go, bind){
  const bg = document.createElement('div'); bg.className = 'modal-bg';
  bg.innerHTML = `<div class="modal" style="width:min(580px,94vw)"><h2>${title}</h2>${html}
    <div class="foot"><span class="msg err" id="sd-err" style="flex:1;align-self:center"></span><button class="btn" id="sd-no">Cancel</button><button class="btn primary" id="sd-ok">${esc(okLabel || 'OK')}</button></div></div>`;
  const close = () => bg.remove();
  bg.querySelector('#sd-no').onclick = close;
  bg.onclick = e => { if (e.target === bg) close(); };
  bg.addEventListener('keydown', e => { if (e.key === 'Escape') close(); });
  const okb = bg.querySelector('#sd-ok');
  okb.onclick = async () => {
    okb.disabled = true; bg.querySelector('#sd-err').textContent = '';
    try { const r = await go(bg); if (r !== false) close(); else okb.disabled = false; }
    catch (e){ bg.querySelector('#sd-err').textContent = e.message; okb.disabled = false; }
  };
  document.body.appendChild(bg);
  if (bind) bind(bg);
  return bg;
}
async function sdInfo(ck, r){
  try { return await post('/api/secret/info', {cell: ck, ref: r.k}); }
  catch (e){ toast(e.message, true); return null; }
}
const SD_SOUND_NAMES = {wood: 'Wooden door', creaky: 'Creaky door', heavy: 'Heavy door', metal: 'Metal door', stone: 'Stone', dwemer: 'Dwemer machinery'};
function sdSoundSelect(info, id){
  return `<select class="inp" id="${id}">${info.sounds.map(s => `<option value="${s}" ${s === info.sound ? 'selected' : ''}>${esc(SD_SOUND_NAMES[s] || s)}</option>`).join('')}</select>`;
}
// what the server did, shown on the map and in the panels (the way refAction does)
function sdApply(ck, m, keepRef){
  W.cells[ck] = prepCell(m); if (ck === W.key) W.info = m;
  if (keepRef) selectRef(ck, keepRef, true);
  drawMap(); renderWside(); afterChange();
}
// a search box for a place (any cell), like the door panel's: onPick({key, name})
function sdPlaceSearch(bg, inputId, onPick){
  const inp = bg.querySelector('#' + inputId), list = bg.querySelector('#' + inputId + '-l');
  let t, seq = 0;
  inp.oninput = () => { clearTimeout(t); t = setTimeout(async () => {
    const q = inp.value.trim(); const my = ++seq;
    if (!q){ list.style.display = 'none'; return; }
    const res = await api('/api/search?' + new URLSearchParams({q, types: 'CELL', limit: 40}));
    if (my !== seq) return;
    list.innerHTML = res.rows.map((x, n) => `<div data-n="${n}">${esc(x.name || x.id)}<small>${esc(x.name ? x.id : '')}</small></div>`).join('') || '<div class="msg">No matches</div>';
    list.style.display = 'block';
    list.querySelectorAll('[data-n]').forEach(d => d.onclick = async ev => {
      ev.preventDefault(); list.style.display = 'none';
      const row = res.rows[+d.dataset.n]; inp.value = row.name || row.id;
      const m = await api('/api/cellmap?i=' + row.i);
      onPick({key: m.key, name: row.name || row.id});
    });
  }, 150); };
  inp.onblur = () => setTimeout(() => { if (!list.matches(':hover')) list.style.display = 'none'; }, 150);
}

// ---------------------------------------------------------------- 1. a door to somewhere
async function sdDoorTo(ck, r){
  if (!await needProject()) return;
  const info = await sdInfo(ck, r); if (!info) return;
  const name = r.name || r.id;
  const here = W.info && W.info.name ? W.info.name : '';
  const html = `<div class="msg">${esc(name)} becomes a door that looks just the same (a new door record with its model) and leads where you choose. You arrive just inside, in front of the door back to here. A place with no door back gets one (move it afterwards if it stands oddly).</div>
    <div style="margin-top:12px"><label class="msg" style="display:flex;gap:6px;align-items:center"><input type="radio" name="sd-kind" value="existing" checked> <b>A place that exists</b></label>
      <div class="dd" style="margin:4px 0 0 22px"><input class="inp" id="sd-place" placeholder="Search a place… (any interior, or an outdoor cell)" autocomplete="off" style="width:100%"><div class="ddlist" id="sd-place-l"></div></div>
      <div class="msg" id="sd-place-pick" style="margin-left:22px"></div></div>
    <div style="margin-top:10px"><label class="msg" style="display:flex;gap:6px;align-items:center"><input type="radio" name="sd-kind" value="copy"> <b>A new place, copied from one the game made</b></label>
      <div id="sd-copy" style="margin:4px 0 0 22px;display:none">
        <select class="inp" id="sd-tpl" style="width:100%"><option value="">Loading the game's places…</option></select>
        <input class="inp" id="sd-name" placeholder="Name of the new place, e.g. ${esc(here ? here + ', Hidden Room' : 'Hidden Room')}" style="margin-top:6px;width:100%">
        <div class="msg" style="margin-top:6px">${[['furnished', 'With everything in it'], ['lights', 'Walls and lights only'], ['empty', 'Walls only']].map(([v, l], n) => `<label style="margin-right:12px"><input type="radio" name="sd-contents" value="${v}" ${n === 0 ? 'checked' : ''}> ${l}</label>`).join('')}</div>
      </div></div>
    <div style="margin-top:10px"><label class="msg" style="display:flex;gap:6px;align-items:center"><input type="radio" name="sd-kind" value="build"> <b>A new place built from pieces</b></label>
      <div class="msg" style="margin-left:22px">The door is made now and Create opens. Lay out the rooms; for "Outside door" pick <i>Through the hidden door you made</i>. Once it's built, this door leads into it.</div></div>
    <div class="frow" style="margin-top:12px"><label>Door sound</label>${sdSoundSelect(info, 'sd-sound')}</div>`;
  sdDialog('🚪 Make this a door to…', html, 'Make the door', async bg => {
    const kind = bg.querySelector('[name=sd-kind]:checked').value, sound = bg.querySelector('#sd-sound').value;
    if (kind === 'existing'){
      if (!bg._picked) throw new Error('Search for a place and pick it from the list.');
      const m = await post('/api/secret/door', {cell: ck, ref: r.k, target: bg._picked.key, sound});
      sdApply(ck, m, r.k);
      sdDoorToast(m.made);
    } else if (kind === 'copy'){
      const tpl = bg.querySelector('#sd-tpl').value, nm = bg.querySelector('#sd-name').value.trim();
      if (!tpl) throw new Error('Pick a place to copy.');
      if (!nm) throw new Error('Give the new place a name.');
      const m = await post('/api/secret/door', {cell: ck, ref: r.k, sound, new: {template: tpl, name: nm, contents: (bg.querySelector('[name=sd-contents]:checked') || {}).value || 'furnished'}});
      sdApply(ck, m, r.k);
      sdDoorToast(m.made);
    } else {
      // the door now; the place from Create, with this door as its way in (see the end of this file)
      const m = await post('/api/ref/secret', {cell: ck, ref: r.k, kind: 'door', sound});
      sdApply(ck, m, r.k);
      const d = findRef(ck, r.k);
      W.doorEntrance = {cell: ck, ref: r.k, x: d.p[0], y: d.p[1], z: d.p[2], rz: d.p[5], name: d.name || d.id, cellName: (W.cells[ck] || {}).name || ck, armed: false};
      toast('Now a door that looks like ' + name + '. Lay out the new place; for "Outside door" pick "Through the hidden door you made".');
      CR.kind = 'build'; showView('createv'); await renderCreate();
      if (CR.bmode === 'copy' && typeof crBuildMode === 'function') crBuildMode('plan');
    }
  }, async bg => {
    bg.querySelectorAll('[name=sd-kind]').forEach(x => x.onchange = () => { bg.querySelector('#sd-copy').style.display = bg.querySelector('[name=sd-kind]:checked').value === 'copy' ? '' : 'none'; });
    sdPlaceSearch(bg, 'sd-place', v => { bg._picked = v; bg.querySelector('#sd-place-pick').textContent = 'Leads to ' + v.name + '.'; });
    bg.querySelector('#sd-place').focus();
    // the game's places to copy, by style, the style of this place first
    try {
      const all = (await api('/api/create/interiors?all=1')).filter(x => !(S.summary && S.summary.project) || x.key !== ck);
      const sel = bg.querySelector('#sd-tpl'); if (!sel.isConnected) return;
      const styles = [...new Set(all.map(x => x.style))].sort();
      const mine = sdStyleGuess((W.cells[ck] || {}).refs || []);
      if (mine && styles.includes(mine)){ styles.splice(styles.indexOf(mine), 1); styles.unshift(mine); }
      else { for (const s of ['Imperial', 'Hlaalu', 'Redoran', 'Telvanni', 'Velothi'].reverse()) if (styles.includes(s)){ styles.splice(styles.indexOf(s), 1); styles.unshift(s); } }
      sel.innerHTML = styles.map(s => `<optgroup label="${esc(s)}">${all.filter(x => x.style === s).map(x => `<option value="${esc(x.key)}">${esc(x.name)} · ${x.objects} things</option>`).join('')}</optgroup>`).join('');
    } catch (e){}
  });
}
function sdStyleGuess(refs){
  // the style of a place from its walls' IDs (in_hlaalu_…, T_Imp_SetGC_…): the same words mapdata.style_of goes by
  const words = {hlaalu: 'Hlaalu', hla: 'Hlaalu', redoran: 'Redoran', telvanni: 'Telvanni', velothi: 'Velothi', imp: 'Imperial', nord: 'Nordic',
                 dwrv: 'Dwemer', dwemer: 'Dwemer', daed: 'Daedric', cave: 'Cave', com: 'Common', c: 'Common', r: 'Redoran', t: 'Telvanni', v: 'Velothi'};
  const votes = {};
  for (const r of refs){
    if (!r.arch) continue;
    const parts = r.id.toLowerCase().split('_');
    const s = parts.map(p => words[p]).find(Boolean);
    if (s) votes[s] = (votes[s] || 0) + 1;
  }
  return Object.keys(votes).sort((a, b) => votes[b] - votes[a])[0] || null;
}
function sdDoorToast(made){
  let s = 'Now a door to ' + made.target_name + '.';
  if (made.made_back) s += ' A ' + made.back + ' was put there to come back through: move it where it should stand.';
  else if (made.back) s += ' ' + made.back + ' there leads back here.';
  toast(s + (LINK.connected ? ' Already live in game.' : ''));
}

// ---------------------------------------------------------------- 2. an ordinary object again
async function sdPlain(ck, r){
  if (!await needProject()) return;
  try {
    const m = await post('/api/secret/plain', {cell: ck, ref: r.k});
    sdApply(ck, m, r.k);
    const d = m.made;
    let s = (r.name || r.id) + ' is an ordinary object again (' + d.id + ').';
    const where = d.to ? (d.to.cell || d.to.label || 'outdoors') : '';
    if (d.far && d.far.length) s += ' The door at the other end, ' + d.far.join(' and ') + ' in ' + where + ', still leads here: make it an ordinary object too if you like.';
    else if (d.to) s += ' It no longer leads to ' + where + '.';
    toast(s);
  } catch (e){ toast(e.message, true); }
}

// ---------------------------------------------------------------- 3. a rotating panel
async function sdSwing(ck, r){
  if (!await needProject()) return;
  const info = await sdInfo(ck, r); if (!info) return;
  const name = r.name || r.id;
  const sz = info.size || {};
  const wide = sz.left != null ? Math.round(sz.left) : '?', deep = sz.back != null ? Math.round(sz.back) : '?';
  const html = `<div class="msg">${esc(name)} becomes a door that leads nowhere and swings open when used, like a door on a hinge. It is ${wide} units wide and ${deep} deep${info.front_learnt ? '' : '; which side is its front was guessed from its shape (the thinner side faces the room)'}.</div>
    <div class="msg" style="margin-top:8px">The game turns a door round its model's origin, so a copy of the model is made with its origin at the hinge and the piece is re-seated on that point: nothing looks to have moved, and in game it swings a quarter turn round the edge you pick.</div>
    <div style="margin-top:12px">${[['left', 'Hinge on the left', 'your left as you look at it from the room, at the wall side'], ['right', 'Hinge on the right', 'your right as you look at it, at the wall side'], ['centre', 'Turns round its middle', 'like a revolving door: half of it swings into the wall']].map(([v, l, d], n) => `<label class="msg" style="display:flex;gap:6px;align-items:center;margin-top:4px"><input type="radio" name="sd-hinge" value="${v}" ${n === 0 ? 'checked' : ''}> <b>${l}</b> · ${d}</label>`).join('')}</div>
    <div class="frow" style="margin-top:12px"><label>Open and close sound</label>${sdSoundSelect(info, 'sd-sound')}</div>
    <div class="msg" style="margin-top:10px;font-size:11.5px">If it swings the wrong way in game, Undo and pick the other edge. To make it lead somewhere as well, use "Make it lead somewhere…" afterwards.</div>`;
  sdDialog('↪ Rotating panel', html, 'Make it swing', async bg => {
    const hinge = bg.querySelector('[name=sd-hinge]:checked').value, sound = bg.querySelector('#sd-sound').value;
    const m = await post('/api/secret/swing', {cell: ck, ref: r.k, hinge, sound});
    sdApply(ck, m, r.k);
    const d = m.made;
    toast(name + ' now swings open on its ' + (d.hinge === 'centre' ? 'middle' : d.hinge + ' edge') + ' (' + d.id + '). Its origin moved ' + Math.round(Math.hypot(d.moved[0], d.moved[1])) + ' units to the hinge; it stands where it did.');
  });
}

// ---------------------------------------------------------------- 4. a sliding panel
async function sdSlide(ck, r){
  if (!await needProject()) return;
  const info = await sdInfo(ck, r); if (!info) return;
  const name = r.name || r.id;
  const sz = info.size || {};
  const ways = [['back', 'Back into the wall'], ['left', 'To the left'], ['right', 'To the right'], ['up', 'Up into the ceiling'], ['down', 'Down into the floor'], ['forward', 'Forward into the room']];
  const others = ((W.cells[ck] || {}).refs || []).filter(x => x.k !== r.k && ['ACTI', 'STAT', 'LIGH', 'BOOK', 'MISC', 'CONT', 'DOOR', 'WEAP', 'ARMO', 'CLOT'].includes(x.type));
  const html = `<div class="msg">${esc(name)} becomes an activator with a script: when used it slides the chosen way over a second and a half, with a sound, and slides back the next time. The script is written the way the game's own secret doors are (a timer, Move, SetAtStart) and opens in the Scripts editor afterwards.${info.front_learnt ? '' : ' Which side is its front was guessed from its shape (the thinner side faces the room).'}</div>
    <div class="frow" style="margin-top:12px"><label>Slides</label><select class="inp" id="sd-way">${ways.map(([v, l], n) => `<option value="${v}" ${n === 0 ? 'selected' : ''}>${l}${sz[v] != null ? ' (it is ' + Math.round(sz[v]) + ' units that way)' : ''}</option>`).join('')}</select></div>
    <div class="frow"><label>How far (units)</label><input class="inp" id="sd-dist" value="${sz.back != null ? Math.round(sz.back) : 128}"><div class="hint">Its own size that way slides it fully out of sight. 70 units are about a metre.</div></div>
    <div class="frow"><label>Sound</label>${sdSoundSelect(info, 'sd-sound')}</div>
    <div style="margin-top:12px"><label class="msg" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="sd-trig"> <b>Pulled by another object</b> (a lever, a candle, a book, a button…)</label>
      <div id="sd-trigbox" style="margin:4px 0 0 22px;display:none"><div class="dd"><input class="inp" id="sd-trigq" placeholder="Something in this place… (type to search, nearest first)" autocomplete="off" style="width:100%"><div class="ddlist" id="sd-trigq-l"></div></div>
        <div class="msg" id="sd-trigpick">That object carries the script instead (as a copy of its own, so others like it are left alone) and the panel moves when it is used; the panel itself does nothing when touched.</div></div></div>`;
  sdDialog('⇆ Sliding panel', html, 'Make it slide', async bg => {
    const way = bg.querySelector('#sd-way').value, distance = parseFloat(bg.querySelector('#sd-dist').value), sound = bg.querySelector('#sd-sound').value;
    if (isNaN(distance)) throw new Error('How far should it slide? A number of units.');
    const body = {cell: ck, ref: r.k, way, distance, sound};
    if (bg.querySelector('#sd-trig').checked){
      if (!bg._trig) throw new Error('Pick the object that pulls it, or untick "Pulled by another object".');
      body.trigger = {cell: ck, ref: bg._trig.k};
    }
    const m = await post('/api/secret/slide', body);
    sdApply(ck, m, r.k);
    const d = m.made, bad = d.check && d.check.errors;
    const nr = (d.riders || []).length;
    const ride = nr ? ' The ' + nr + ' thing' + (nr === 1 ? '' : 's') + ' on it ride along' : ' Things put on it ride along';
    toast(name + ' now slides ' + way + ' ' + Math.round(d.distance) + ' units' + (d.trigger ? ' when ' + d.trigger.was + ' is used' : ' when used') + '. Script ' + d.script + (bad ? ' has ' + bad + ' problem(s): see the Scripts editor.' : ' is attached and checked.') + ride + ' (the Lua script ' + (d.riders_script || 'wsriders') + ' in your mod\'s Scripts).', !!bad);
    if (typeof sOpen === 'function') sOpen(d.script);
  }, bg => {
    const way = bg.querySelector('#sd-way'), dist = bg.querySelector('#sd-dist');
    way.onchange = () => { if (sz[way.value] != null) dist.value = Math.round(sz[way.value]); };
    const tr = bg.querySelector('#sd-trig'); tr.onchange = () => { bg.querySelector('#sd-trigbox').style.display = tr.checked ? '' : 'none'; if (tr.checked) bg.querySelector('#sd-trigq').focus(); };
    const q = bg.querySelector('#sd-trigq'), list = bg.querySelector('#sd-trigq-l'), pick = bg.querySelector('#sd-trigpick');
    const away = x => Math.hypot(x.p[0] - r.p[0], x.p[1] - r.p[1], x.p[2] - r.p[2]);
    q.oninput = () => {
      const s = q.value.trim().toLowerCase();
      const rows = others.filter(x => !s || (x.name || '').toLowerCase().includes(s) || x.id.toLowerCase().includes(s)).sort((a, b) => away(a) - away(b)).slice(0, 30);
      list.innerHTML = rows.map((x, n) => `<div data-n="${n}">${esc(x.name || x.id)}<small>${esc(x.id)} · ${Math.round(away(x))} units away</small></div>`).join('') || '<div class="msg">Nothing like that here</div>';
      list.style.display = 'block';
      list.querySelectorAll('[data-n]').forEach(d => d.onclick = ev => { ev.preventDefault(); list.style.display = 'none'; bg._trig = rows[+d.dataset.n]; q.value = bg._trig.name || bg._trig.id; pick.textContent = (bg._trig.name || bg._trig.id) + ' will pull it: it gets the script as a copy of its own, and the panel itself does nothing when touched.'; });
    };
    q.onfocus = () => q.oninput();
    q.onblur = () => setTimeout(() => { if (!list.matches(':hover')) list.style.display = 'none'; }, 150);
  });
}

// ---------------------------------------------------------------- Build from pieces through a hidden door
// While a door waits (sdDoorTo, "built from pieces"), the Create page's "Outside door" choices get one more:
// the build then puts its own outside door on the hidden door's spot, and once the new place opens on the
// map the hidden door takes over where it led and the spare door goes (mechanism.adopt).
if (typeof placeOptions === 'function'){
  const _po = placeOptions, _pv = placeValue, _wo = worldOpen;
  placeOptions = function(required, noneLabel){
    let h = _po(required, noneLabel);
    const d = W.doorEntrance;
    if (!d) return h;
    const opt = `<option value="hidden" selected>Through the hidden door you made (${esc(d.name)} in ${esc(d.cellName)}), no new outside door</option>`;
    return h.startsWith('<select') ? h.replace('<select class="inp" id="cr-place">', '<select class="inp" id="cr-place">' + opt) : `<select class="inp" id="cr-place">${opt}</select>`;
  };
  placeValue = function(){
    const v = ($('#cr-place') || {}).value, d = W.doorEntrance;
    if (v === 'hidden' && d){ d.armed = true; return {cell: d.cell, x: d.x, y: d.y, z: d.z, rz: d.rz}; }
    return _pv();
  };
  worldOpen = async function(key, keepCam){
    const d = W.doorEntrance;
    const out = await _wo(key, keepCam);
    if (d && d.armed && key !== d.cell && !String(key).startsWith('#')){
      W.doorEntrance = null;
      try {
        const m = await post('/api/secret/adopt', {cell: d.cell, ref: d.ref, target: key});
        W.cells[d.cell] = prepCell(m);
        toast(d.name + ' in ' + d.cellName + ' now leads into ' + ((W.cells[key] || {}).name || key) + '.');
        afterChange();
      } catch (e){ toast('Built it, but the hidden door could not be linked: ' + e.message, true); }
    }
    return out;
  };
}
