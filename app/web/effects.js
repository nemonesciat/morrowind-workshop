// ---------- Your own magic effects (Create > New magic effect; myeffects.py) ----------
// A new effect looks like one of the game's (its template: school, icon, colours, sounds, spell pictures),
// with its own name, icon, base cost and description; what it does is what you pick here, written into
// small OpenMW Lua scripts for the mod. The spell, enchantment and potion editors then offer it with the
// game's effects. Needs OpenMW 0.50 or newer, and the mod as an .omwaddon (a plain .esp can't carry Lua).
const MX = {data: null, sel: null, form: null};

async function renderMyEffects(){
  const nb = document.querySelector('nav [data-view="createv"]'); if (nb) nb.classList.add('on');
  const box = $('#myeff');
  if (!S.summary || !S.summary.project){ box.innerHTML = '<div class="wrap"><h1>Magic effects</h1><p class="lead">Start a mod first.</p></div>'; return; }
  box.innerHTML = '<div class="msg" style="padding:30px"><span class="spin"></span>Loading…</div>';
  try { MX.data = await api('/api/myeffects'); } catch (e){ box.innerHTML = `<div class="msg err" style="padding:30px">${esc(e.message)}</div>`; return; }
  if (!MX.form) mxNew();
  mxDraw();
}
function mxNew(){
  const t = (MX.data && MX.data.templates.find(x => x.name === 'Shield')) || (MX.data && MX.data.templates[0]) || {};
  MX.sel = null;
  MX.form = {id: '', name: '', template: t.index, cost: t.cost, icon: '', description: '', magnitude: t.magnitude !== false, duration: t.duration !== false, does: []};
}
function mxOpen(id){
  const e = MX.data.effects.find(x => x.id === id); if (!e) return;
  MX.sel = id; MX.form = JSON.parse(JSON.stringify(e)); mxDraw();
}
function mxTpl(){ return MX.data.templates.find(x => x.index === +MX.form.template) || {}; }
const MX_WHEN = {land: 'as it lands', second: 'each second', end: 'as it ends'};
const MX_ONLY = {any: 'on anyone', npc: 'only on people', creature: 'only on creatures', undead: 'only on undead', daedra: 'only on Daedra', player: 'only on the player', notplayer: 'on anyone but the player'};
const MX_STATS = {health: 'health', magicka: 'magicka', fatigue: 'fatigue'};
const mxSel = (k, n, opts, cur) => `<select class="inp" data-mxd="${k}" data-n="${n}" style="width:auto">${Object.entries(opts).map(([v, t]) => `<option value="${v}" ${String(cur) === v ? 'selected' : ''}>${esc(t)}</option>`).join('')}</select>`;
const mxNum = (k, n, v, w, ph) => `<input class="inp" type="number" step="any" data-mxd="${k}" data-n="${n}" value="${v != null ? v : ''}" ${ph ? `placeholder="${esc(ph)}"` : ''} style="width:${w || 80}px">`;
function mxDoesRow(d, n){
  const K = MX.data.does.find(x => x.kind === d.kind) || {};
  let inner = '';
  // (when, whom, how likely: every step has them; some kinds only make sense at one time)
  const fixedWhen = {scale: 'land', calm: 'land', frenzy: 'land', swap: 'land', aura: 'second', leech: 'second'}[d.kind];
  if (!d.when) d.when = fixedWhen || (['health', 'magicka', 'fatigue'].includes(d.kind) ? (d.per === 'once' ? 'land' : 'second') : 'land');
  const common = `<div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;width:100%;margin-top:4px">
      ${fixedWhen ? `<span class="msg">${esc(MX_WHEN[fixedWhen])}${d.kind === 'scale' || d.kind === 'calm' || d.kind === 'frenzy' ? ', undone as it ends' : ''}</span>` : mxSel('when', n, MX_WHEN, d.when)}
      ${mxSel('only', n, MX_ONLY, d.only || 'any')}
      <span class="msg">chance</span>${mxNum('chance', n, d.chance != null ? d.chance : 100, 70)}<span class="msg">%</span></div>`;
  if (['health', 'magicka', 'fatigue'].includes(d.kind)){
    inner = `${mxSel('sign', n, {'-1': 'takes away', '1': 'gives back'}, d.sign < 0 ? '-1' : '1')}
      <span class="msg">the magnitude${d.when === 'second' ? ' each second' : ''}</span>`;
  } else if (['push', 'pull', 'launch', 'dash'].includes(d.kind)){
    inner = `${mxNum('feet', n, d.feet || '', 90, 'magnitude')}<span class="msg">feet ${d.kind === 'launch' ? 'up' : d.kind === 'dash' ? 'forward' : d.kind === 'pull' ? 'towards the caster' : 'away from the caster'} (empty: the magnitude, in feet)</span>`;
  } else if (d.kind === 'scale'){
    inner = `<span class="msg">times</span>${mxNum('factor', n, d.factor != null ? d.factor : 2, 80)}<span class="msg">their size (2 twice as big, 0.5 half)</span>`;
  } else if (d.kind === 'aura'){
    inner = `${mxSel('sign', n, {'-1': 'takes', '1': 'gives'}, d.sign > 0 ? '1' : '-1')}<span class="msg">the magnitude of</span>${mxSel('stat', n, MX_STATS, d.stat || 'health')}
      <span class="msg">from everyone within</span>${mxNum('feet', n, d.feet || 10, 70)}<span class="msg">feet, each second</span>`;
  } else if (d.kind === 'leech'){
    inner = `<span class="msg">takes the magnitude of their</span>${mxSel('stat', n, MX_STATS, d.stat || 'health')}<span class="msg">each second and gives it to the caster</span>`;
  } else if (d.kind === 'calm' || d.kind === 'frenzy' || d.kind === 'swap'){
    inner = `<span class="msg">${esc(K.what || '')}</span>`;
  } else if (d.kind === 'cast'){
    inner = `<div class="dd" style="flex:1"><input class="inp" id="mx-cast-${n}" data-mxd="id" data-n="${n}" value="${esc(d.id || '')}" placeholder="A spell… (search)" autocomplete="off"><div class="ddlist" id="mx-cast-${n}-l"></div></div>`;
  } else if (d.kind === 'weather'){
    inner = mxSel('weather', n, Object.fromEntries((MX.data.weathers || []).map(w => [w, w])), d.weather || 'thunderstorm') + '<span class="msg">in the region they are in</span>';
  } else if (d.kind === 'transmute'){
    const pairs = d.pairs && d.pairs.length ? d.pairs : (d.pairs = [{from: '', to: ''}]);
    inner = `<div style="flex:1">${pairs.map((p, i) => `<div style="display:flex;gap:6px;align-items:center;margin-bottom:4px">
        <div class="dd" style="flex:1"><input class="inp" id="mx-tf-${n}-${i}" data-mxp="from" data-n="${n}" data-i="${i}" value="${esc(p.from || '')}" placeholder="An item… (e.g. iron ore)" autocomplete="off"><div class="ddlist" id="mx-tf-${n}-${i}-l"></div></div>
        <span class="msg">becomes</span>
        <div class="dd" style="flex:1"><input class="inp" id="mx-tt-${n}-${i}" data-mxp="to" data-n="${n}" data-i="${i}" value="${esc(p.to || '')}" placeholder="…this item" autocomplete="off"><div class="ddlist" id="mx-tt-${n}-${i}-l"></div></div></div>`).join('')}
      <button class="btn sm" data-mxpair="${n}">+ Another pair</button><span class="msg"> The first pair they carry is the one changed;</span>${mxNum('count', n, d.count || 1, 60)}<span class="msg">at a time.</span></div>`;
  } else if (d.kind === 'lua'){
    inner = `<div style="flex:1;width:100%">
        <div style="display:flex;gap:6px;align-items:center"><input class="inp" data-mxd="brief" data-n="${n}" value="${esc(d.brief || '')}" placeholder="Say what it does, e.g. every enemy within 15 feet is thrown back" style="flex:1">
          <button class="btn sm" data-mxai="${n}" title="The Assistant writes the Lua from what you say (uses your API key)">✦ Write it for me</button></div>
        <textarea class="inp code" data-mxd="code" data-n="${n}" rows="7" spellcheck="false" style="width:100%;margin-top:6px;font-family:monospace" placeholder="-- the body of function(ctx): ctx.self, ctx.caster, ctx.magnitude, ctx.change('health', -5), ctx.push(10), ctx.launch(8), ctx.scale(2), ctx.weather('thunderstorm'), ctx.cast('fireball'), ctx.message('...')">${esc(d.code || '')}</textarea>
        <div class="msg" id="mx-ai-${n}"></div></div>`;
  } else if (d.kind === 'teleport'){
    inner = `<input class="inp" data-mxd="cell" data-n="${n}" value="${esc(d.cell || '')}" placeholder="Cell name (empty: outside)" style="max-width:220px">
      <span class="msg">x</span><input class="inp" type="number" data-mxd="x" data-n="${n}" value="${d.x || 0}" style="width:90px">
      <span class="msg">y</span><input class="inp" type="number" data-mxd="y" data-n="${n}" value="${d.y || 0}" style="width:90px">
      <span class="msg">z</span><input class="inp" type="number" data-mxd="z" data-n="${n}" value="${d.z || 0}" style="width:80px">
      ${W && W.key ? `<button class="btn sm" data-mxhere="${n}" title="The place open on the World map and the middle of its view">Here on the map</button>` : ''}`;
  } else if (d.kind === 'spawn'){
    inner = `<div class="dd" style="flex:1"><input class="inp" id="mx-spawn-${n}" data-mxd="id" data-n="${n}" value="${esc(d.id || '')}" placeholder="An object or creature… (search)" autocomplete="off"><div class="ddlist" id="mx-spawn-${n}-l"></div></div>`;
  } else if (d.kind === 'global'){
    inner = `<div class="dd"><input class="inp" id="mx-glob-${n}" data-mxd="name" data-n="${n}" value="${esc(d.name || '')}" placeholder="A global variable… (search)" autocomplete="off" style="max-width:240px"><div class="ddlist" id="mx-glob-${n}-l"></div></div>
      <span class="msg">to</span><input class="inp" type="number" data-mxd="value" data-n="${n}" value="${d.value || 0}" style="width:90px">`;
  } else if (d.kind === 'message'){
    inner = `<input class="inp" data-mxd="text" data-n="${n}" value="${esc(d.text || '')}" placeholder="What the player reads" style="flex:1">`;
  }
  return `<div class="effrow" style="flex-wrap:wrap" title="${esc(K.what || '')}"><b style="min-width:130px">${esc(K.label || d.kind)}</b>${inner}<button class="btn sm danger" data-mxdel="${n}" title="Take this out">✕</button>${common}</div>`;
}
function mxDraw(){
  const box = $('#myeff'), D = MX.data, f = MX.form, t = mxTpl();
  const schools = [...new Set(D.templates.map(x => x.school))];
  box.innerHTML = `<aside class="dside"><div class="actions" style="margin-top:0"><button class="btn sm primary" id="mx-new">+ New effect</button><button class="btn sm" id="mx-back">← Create</button></div>
      <h3>Your effects</h3>
      ${D.effects.length ? D.effects.map(e => `<div class="li ${MX.sel === e.id ? 'on' : ''}" data-mxopen="${esc(e.id)}" style="cursor:pointer;padding:6px 8px;border-radius:6px">${esc(e.name)}<div class="msg">${esc(e.id)}</div></div>`).join('') : '<div class="msg">None yet.</div>'}
      <div class="msg" style="margin-top:14px;line-height:1.6">Your own magic effects, for spells, enchantments and potions, made the way Tamriel Data makes its own in OpenMW.
        Each looks like one of the game's effects and does what you pick. They need OpenMW 0.50 or newer.</div></aside>
    <main class="dmain"><div class="wrap" style="max-width:860px">
      <h1>${MX.sel ? esc(f.name || MX.sel) : 'New magic effect'}</h1>
      <div class="frow">
        <label>Name</label><input class="inp" id="mx-name" maxlength="31" value="${esc(f.name || '')}" placeholder="e.g. Storm Call">
        <label>ID</label><div><input class="inp" id="mx-id" maxlength="31" value="${esc(f.id || '')}" placeholder="filled in from the name: WS_StormCall" style="max-width:280px"><div class="hint">Its handle in scripts. Changing it later changes it in your spells too.</div></div>
        <label>Looks like</label><div><select class="inp" id="mx-tpl">${schools.map(s => `<optgroup label="${esc(s || 'Other')}">${D.templates.filter(x => x.school === s).map(x => `<option value="${x.index}" ${x.index === +f.template ? 'selected' : ''}>${esc(x.name)}</option>`).join('')}</optgroup>`).join('')}</select>
          <div class="hint">Its school, colours, the sounds and pictures of casting, flying and hitting come from this one. What it does doesn't: that's below.</div></div>
        <label>Icon</label><div><input class="inp" id="mx-icon" value="${esc(f.icon || '')}" placeholder="${esc(t.icon || '')} (the one it looks like)">
          <div class="hint">An icon file under Icons\\, e.g. s\\tx_s_shield.dds. Pick another effect's: <select class="inp" id="mx-iconfrom" style="max-width:260px"><option value="">…</option>${D.templates.filter(x => x.icon).map(x => `<option value="${esc(x.icon)}">${esc(x.name)}</option>`).join('')}</select></div></div>
        <label>Base cost</label><div><input class="inp" type="number" step="0.1" min="0" id="mx-cost" value="${f.cost != null ? f.cost : t.cost}" style="max-width:120px"><div class="hint">What a point of it costs to cast or enchant; ${esc(t.name || 'the one it looks like')} costs ${t.cost}.</div></div>
        <label>Has</label><div style="display:flex;gap:16px">${chk('mx-mag', 'a magnitude', f.magnitude)}${chk('mx-dur', 'a duration', f.duration)}</div>
        <label>Description</label><textarea class="inp" id="mx-desc" rows="2" placeholder="What the game says it does">${esc(f.description || '')}</textarea>
      </div>
      <h3 style="margin-top:18px">What it does</h3>
      <div class="msg" style="margin-bottom:8px">On the one it lands on, while it lasts. A magnitude of 10 that takes away health per second takes 10 a second.</div>
      <div id="mx-does">${(f.does || []).map(mxDoesRow).join('') || '<div class="msg">Nothing yet: it would only look the part. Add what it does:</div>'}</div>
      <div class="actions" style="margin-top:6px">${D.does.map(d => `<button class="btn sm" data-mxadd="${d.kind}" title="${esc(d.what)}">+ ${esc(d.label)}</button>`).join('')}</div>
      <div class="actions" style="margin-top:20px"><button class="btn primary" id="mx-save">${MX.sel ? 'Save' : 'Make the effect'}</button>
        ${MX.sel ? '<button class="btn danger" id="mx-del">Remove it</button>' : ''}<span class="msg" id="mx-msg"></span></div>
      <div class="cwhat"><b>${MX.sel ? 'Save' : 'Make the effect'}</b> ${MX.sel ? 'changes' : 'adds'} the effect in your mod's scripts: made as the game loads, looking like ${esc(t.name || '…')}${(f.does || []).length ? ', doing ' + (f.does || []).length + ' thing' + ((f.does || []).length === 1 ? '' : 's') + ' when it lands' : ', doing nothing yet'}. Then pick it in a spell, enchantment or potion like any effect (it shows as "(yours)"). One Undo takes it back.</div>
    </div></main>`;
  box.style.display = '';
  $('#mx-new').onclick = () => { mxNew(); mxDraw(); };
  $('#mx-back').onclick = () => showView('createv');
  box.querySelectorAll('[data-mxopen]').forEach(el => el.onclick = () => mxOpen(el.dataset.mxopen));
  const keep = () => {
    f.name = $('#mx-name').value; f.id = $('#mx-id').value; f.template = +$('#mx-tpl').value; f.icon = $('#mx-icon').value;
    f.cost = $('#mx-cost').value === '' ? null : +$('#mx-cost').value; f.magnitude = $('#mx-mag').checked; f.duration = $('#mx-dur').checked;
    f.description = $('#mx-desc').value;
  };
  ['mx-name', 'mx-id', 'mx-icon', 'mx-cost', 'mx-desc'].forEach(id => $('#' + id).oninput = keep);
  ['mx-mag', 'mx-dur'].forEach(id => $('#' + id).onchange = keep);
  $('#mx-tpl').onchange = () => { keep(); const nt = mxTpl(); f.cost = nt.cost; f.magnitude = nt.magnitude !== false; f.duration = nt.duration !== false; mxDraw(); };
  $('#mx-iconfrom').onchange = e => { if (e.target.value){ $('#mx-icon').value = e.target.value; keep(); } };
  box.querySelectorAll('[data-mxd]').forEach(el => el.oninput = el.onchange = () => {
    const d = f.does[+el.dataset.n], k = el.dataset.mxd;
    d[k] = ['sign', 'x', 'y', 'z', 'value', 'chance', 'factor', 'count'].includes(k) ? +el.value : k === 'feet' ? (el.value === '' ? '' : +el.value) : el.value;
    if (k === 'when' && el.tagName === 'SELECT') mxDraw();
  });
  box.querySelectorAll('[data-mxp]').forEach(el => el.oninput = () => { f.does[+el.dataset.n].pairs[+el.dataset.i][el.dataset.mxp] = el.value; });
  box.querySelectorAll('[data-mxpair]').forEach(b => b.onclick = () => { keep(); f.does[+b.dataset.mxpair].pairs.push({from: '', to: ''}); mxDraw(); });
  box.querySelectorAll('[data-mxai]').forEach(b => b.onclick = async () => {
    const n = +b.dataset.mxai, d = f.does[n], out = $('#mx-ai-' + n);
    keep();
    if (!(d.brief || '').trim()){ out.className = 'msg err'; out.textContent = 'Say first what it should do, in the line to the left.'; return; }
    const done = slowWait(b, out, 'Writing…');
    try {
      const r = await post('/api/ai/effectlua', {name: f.name, description: f.description, brief: d.brief, when: d.when});
      done(); d.code = r.code; mxDraw();
      const o2 = $('#mx-ai-' + n);
      if (o2){ o2.className = r.problems.length ? 'msg err' : 'msg'; o2.textContent = r.problems.length ? 'The checker sees a problem on line ' + r.problems[0].line + ': ' + r.problems[0].text : 'Written. Read it over, change what you like, then Save.'; }
    } catch (e){ done(); out.className = 'msg err'; out.textContent = e.message; }
  });
  box.querySelectorAll('[data-mxdel]').forEach(b => b.onclick = () => { keep(); f.does.splice(+b.dataset.mxdel, 1); mxDraw(); });
  box.querySelectorAll('[data-mxadd]').forEach(b => b.onclick = () => {
    keep(); const k = b.dataset.mxadd;
    f.does.push(['health', 'magicka', 'fatigue'].includes(k) ? {kind: k, sign: -1, when: 'second'} : k === 'teleport' ? {kind: k, cell: '', x: 0, y: 0, z: 0}
      : k === 'scale' ? {kind: k, factor: 2} : k === 'aura' ? {kind: k, sign: -1, stat: 'health', feet: 10} : k === 'leech' ? {kind: k, stat: 'health'}
      : k === 'weather' ? {kind: k, weather: 'thunderstorm'} : k === 'transmute' ? {kind: k, pairs: [{from: '', to: ''}], count: 1} : {kind: k});
    mxDraw();
  });
  box.querySelectorAll('[data-mxhere]').forEach(b => b.onclick = () => {
    const d = f.does[+b.dataset.mxhere];
    d.cell = W.ext ? '' : ((W.info && W.info.name) || W.key); d.x = Math.round(W.cam.x); d.y = Math.round(W.cam.y); d.z = Math.round(W.cam.z || 0);
    mxDraw();
  });
  (f.does || []).forEach((d, n) => {
    if (d.kind === 'spawn' && $('#mx-spawn-' + n)) ddSearch('mx-spawn-' + n, 'CREA,NPC_,LEVC,STAT,ACTI,MISC,WEAP,ARMO,CLOT,LIGH,CONT,ALCH,INGR,BOOK', r => { d.id = r.id; $('#mx-spawn-' + n).value = r.id; });
    if (d.kind === 'global' && $('#mx-glob-' + n)) ddSearch('mx-glob-' + n, 'GLOB', r => { d.name = r.id; $('#mx-glob-' + n).value = r.id; });
    if (d.kind === 'cast' && $('#mx-cast-' + n)) ddSearch('mx-cast-' + n, 'SPEL', r => { d.id = r.id; $('#mx-cast-' + n).value = r.id; });
    if (d.kind === 'transmute') (d.pairs || []).forEach((p, i) => {
      const items = 'MISC,INGR,WEAP,ARMO,CLOT,ALCH,BOOK,APPA,LOCK,PROB,REPA,LIGH';
      if ($(`#mx-tf-${n}-${i}`)) ddSearch(`mx-tf-${n}-${i}`, items, r => { p.from = r.id; $(`#mx-tf-${n}-${i}`).value = r.id; });
      if ($(`#mx-tt-${n}-${i}`)) ddSearch(`mx-tt-${n}-${i}`, items, r => { p.to = r.id; $(`#mx-tt-${n}-${i}`).value = r.id; });
    });
  });
  $('#mx-save').onclick = async () => {
    keep();
    if (!await needProject()) return;
    try {
      const was = MX.sel;
      const r = await post('/api/myeffects/save', {effect: f, old_id: MX.sel});
      MX.data.effects = r.effects; MX.sel = r.effect.id; MX.form = JSON.parse(JSON.stringify(r.effect));
      if (CR.opts) CR.opts.magic = null;          // (the editors list it from now on)
      toast((was ? 'Saved ' : 'Made ') + r.effect.name + '. Pick it in a spell, enchantment or potion.');
      afterChange(); mxDraw();
    } catch (e){ $('#mx-msg').className = 'msg err'; $('#mx-msg').textContent = e.message; }
  };
  const del = $('#mx-del');
  if (del) del.onclick = async () => {
    if (!confirm('Remove the effect ' + f.name + '?')) return;
    try { const r = await post('/api/myeffects/delete', {id: MX.sel}); MX.data.effects = r.effects; if (CR.opts) CR.opts.magic = null; toast('Removed ' + f.name + '.'); afterChange(); mxNew(); mxDraw(); }
    catch (e){ $('#mx-msg').className = 'msg err'; $('#mx-msg').textContent = e.message; }
  };
}
// (a window over the 3D view too, like the other Create tools; viewwin.js)
if (typeof VW_HOST !== 'undefined')
  VW_HOST.myeff = {title: () => '🌀 ' + (MX.sel && MX.form ? MX.form.name || MX.sel : 'New magic effect'), render: () => renderMyEffects(), w: 1040};
