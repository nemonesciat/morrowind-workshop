// ---------- Item editor: any existing item, spell or enchantment, with its stats, looks, script,
// effects and enchantment ----------
const IE = {id: null, data: null, orig: null};
const IE_TYPES = 'WEAP,ARMO,CLOT,ALCH,INGR,MISC,LIGH,LOCK,PROB,REPA,APPA,BOOK,SPEL,ENCH';
const IE_LABEL = {WEAP: 'Weapon', ARMO: 'Armor', CLOT: 'Clothing', ALCH: 'Potion', INGR: 'Ingredient', MISC: 'Misc item', LIGH: 'Light',
  LOCK: 'Lockpick', PROB: 'Probe', REPA: 'Repair tool', APPA: 'Apparatus', BOOK: 'Book', SPEL: 'Spell', ENCH: 'Enchantment'};
const IE_ENCH = ['Cast once', 'Cast when strikes', 'Cast when used', 'Constant effect'];
const IE_SPELL = ['Spell', 'Ability', 'Blight disease', 'Disease', 'Curse', 'Power'];

function ieShow(id){ IE.id = id || IE.id; IE.data = null; showView('itemed'); }
async function ieOpts(){
  CR.opts = CR.opts || {};
  if (!CR.opts.magic) CR.opts.magic = await api('/api/items/options');
  return CR.opts.magic;
}
async function renderItemEd(){
  await ieOpts();
  const box = $('#itemed');
  if (!IE.id){ ieWelcome(); return; }
  if (!IE.data){
    box.innerHTML = '<div class="msg" style="padding:30px"><span class="spin"></span>Loading…</div>';
    try { IE.data = await api('/api/item?id=' + encodeURIComponent(IE.id)); IE.orig = JSON.stringify(IE.data); }
    catch (e){ box.innerHTML = `<div class="wrap"><div class="msg err" style="padding:30px">${esc(e.message)}</div></div>`; return; }
  }
  ieRender();
}
function ieWelcome(){
  $('#itemed').innerHTML = `<div class="wrap" style="max-width:760px"><h1>✎ Edit an item, spell or enchantment</h1>
    <p class="lead">Change anything about an item that already exists: its stats, name, looks and script, a potion's effects, a spell's effects and cost, or an enchantment, including the ones the game's own artifacts have.</p>
    <div class="dd"><input class="inp" id="ie-find" placeholder="Find one… (e.g. Trebonius' Staff, Fireball, Ring of Keley)" autocomplete="off"><div class="ddlist" id="ie-find-l"></div></div></div>`;
  ddSearch('ie-find', IE_TYPES, r => ieShow(r.id));
}

function ieDirty(){
  const x = JSON.stringify(IE.data) !== IE.orig, b = $('#ie-save'); if (!b) return;
  b.disabled = !x; b.textContent = x ? '💾 Save' : 'Saved'; $('#ie-revert').style.visibility = x ? 'visible' : 'hidden';
}
function ieField(f, n){
  const v = f.value;
  if (f.kind === 'opts') return cField(f.label, `<select class="inp" data-ief="${n}">${f.opts.map((o, i) => `<option value="${i}" ${i === +v ? 'selected' : ''}>${esc(o)}</option>`).join('')}</select>`);
  if (f.kind === 'bits') return `<label class="cfield"><span>${esc(f.label)}</span><div class="cchecks">${f.bits.map(([bit, name]) => `<label><input type="checkbox" data-iebit="${n}" data-bit="${bit}" ${(+v & bit) ? 'checked' : ''}> ${esc(name)}</label>`).join('')}</div></label>`;
  if (f.kind === 'str') return cField(f.label, `<input class="inp" data-ief="${n}" value="${esc(v)}" ${f.label === 'Name' ? 'maxlength="31"' : ''}>`);
  return cField(f.label, `<input class="inp num" type="number" step="${f.float ? 'any' : '1'}" data-ief="${n}" value="${f.float ? Math.round(v * 1000) / 1000 : v}">`);
}
function ieRender(){
  const d = IE.data, t = d.tag;
  const strs = d.fields.map((f, n) => [f, n]).filter(([f]) => f.kind === 'str');
  const nums = d.fields.map((f, n) => [f, n]).filter(([f]) => f.kind !== 'str');
  let body = `<div class="cgrid2"><div class="card"><h3 style="margin-top:0">${IE_LABEL[t] || t}</h3>
      ${strs.map(([f, n]) => ieField(f, n)).join('')}
      ${t !== 'ENCH' && t !== 'SPEL' ? cField('Script', `<div class="dd"><input class="inp" id="ie-script" value="${esc(d.script)}" placeholder="None (search for a script…)" autocomplete="off"><div class="ddlist" id="ie-script-l"></div></div>`, 'Runs while the item is in the world or carried.') : ''}
      ${['WEAP', 'ARMO', 'CLOT', 'MISC', 'LIGH', 'ALCH', 'INGR', 'BOOK', 'APPA', 'LOCK', 'PROB', 'REPA'].includes(t) ? '<div class="mv" id="ie-view" style="height:220px;margin-top:8px"></div>' : ''}</div>
    ${nums.length ? `<div class="card"><h3 style="margin-top:0">Stats</h3><div class="iegrid">${nums.map(([f, n]) => ieField(f, n)).join('')}</div></div>` : ''}</div>`;
  if (t === 'BOOK') body += `<div class="card" style="margin-top:14px"><h3 style="margin-top:0">Text</h3>
    <textarea class="inp" id="ie-text" rows="10" style="width:100%;font-family:inherit">${esc(d.text || '')}</textarea>
    <div class="msg">The game's book markup works here, e.g. &lt;BR&gt; for a new line and &lt;DIV ALIGN="CENTER"&gt; to centre text.</div></div>`;
  if (t === 'ALCH') body += `<div class="card" style="margin-top:14px"><h3 style="margin-top:0">Effects when drunk</h3><div id="ie-effects"></div></div>`;
  if (t === 'SPEL'){
    const s = d.spell;
    body += `<div class="card" style="margin-top:14px"><h3 style="margin-top:0">The spell</h3>
      <div class="crow">${cField('Kind', `<select class="inp" id="ie-stype">${IE_SPELL.map((x, i) => `<option value="${i}" ${i === s.type ? 'selected' : ''}>${x}</option>`).join('')}</select>`, 'Abilities, diseases and curses are always on; powers work once a day.')}
        ${cField('Magicka cost', `<input class="inp num" type="number" id="ie-scost" value="${s.cost}" ${s.auto ? 'disabled' : ''}>`)}</div>
      <label class="msg plrow"><input type="checkbox" id="ie-sauto" ${s.auto ? 'checked' : ''}> Work the cost out from the effects (<span id="ie-scalc">${d.cost_now || '…'}</span> magicka)</label>
      <h3>Effects</h3><div id="ie-effects"></div></div>`;
  }
  if (t === 'ENCH') body += ieEnchHtml(d, true);
  if (d.can_enchant) body += ieEnchHtml(d.enchant, false);
  $('#itemed').innerHTML = `<div class="wrap cwrap"><div class="chead"><div><h1 style="margin:0">${esc(d.name || d.id)}</h1>
      <div class="msg">${IE_LABEL[t] || t} · ${esc(d.id)} · ${d.mine ? (d.created ? 'made in your mod' : 'changed in your mod') : 'from ' + esc(d.src) + '. Saving puts your version in your mod.'}</div></div>
      <div class="chbtns"><button class="btn sm" id="ie-other">Edit another…</button><button class="btn sm" id="ie-rec">Record</button><button class="btn sm" id="ie-revert" style="visibility:hidden">↺ Undo edits</button><button class="btn primary" id="ie-save" disabled>Saved</button></div></div>
    ${body}</div>`;
  ieBind();
}
function ieEnchHtml(e, direct){
  const d = IE.data;
  if (!direct && !e){
    return `<div class="card" style="margin-top:14px"><h3 style="margin-top:0">Enchantment</h3>
      <div class="msg">${d.enchant_missing ? `It points to an enchantment that doesn't exist (${esc(d.enchant_missing)}). ` : 'Not enchanted.'}</div>
      <div class="actions"><button class="btn sm" id="ie-addench">✨ Enchant it</button>${d.enchant_missing ? '<button class="btn sm" id="ie-dropench">Remove the broken link</button>' : ''}</div></div>`;
  }
  const x = direct ? d : e;
  const others = (x.used_by || []).filter(u => u.id.toLowerCase() !== d.id.toLowerCase());
  return `<div class="card" style="margin-top:14px"><h3 style="margin-top:0">${direct ? 'The enchantment' : 'Enchantment'}${!direct ? ` <small style="color:var(--faint)">${esc(x.id || 'new')}</small>` : ''}</h3>
    <div class="crow">${cField('Works', `<select class="inp" id="ie-etype">${IE_ENCH.map((n, i) => `<option value="${i}" ${i === +x.type ? 'selected' : ''}>${n}</option>`).join('')}</select>`)}
      ${+x.type !== 3 ? cField('Charge', `<input class="inp num" type="number" id="ie-echarge" value="${x.charge}">`, 'How much it can hold; each use takes the cost.') : ''}
      ${cField(+x.type === 3 ? 'Enchant cost' : 'Cost per use', `<input class="inp num" type="number" id="ie-ecost" value="${x.cost}" ${x.auto ? 'disabled' : ''}>`)}</div>
    <label class="msg plrow"><input type="checkbox" id="ie-eauto" ${x.auto ? 'checked' : ''}> Work the cost out from the effects (<span id="ie-ecalc">…</span>)</label>
    ${+x.type === 3 ? '<div class="msg">Constant effects work on the wearer only, so every effect is on Self.</div>' : ''}
    <h3>Effects</h3><div id="ie-eeffects"></div>
    ${!direct && others.length ? `<div class="cplaced" style="margin-top:8px">${others.length} other item${others.length === 1 ? '' : 's'} use${others.length === 1 ? 's' : ''} this enchantment too (${others.slice(0, 4).map(u => esc(u.name)).join(', ')}${others.length > 4 ? '…' : ''}). When you save changes:
      <div class="radios" style="margin-top:6px"><label><input type="radio" name="ie-scope" value="this" ${e.scope !== 'all' ? 'checked' : ''}>Only this item (it gets a copy of its own)</label><label><input type="radio" name="ie-scope" value="all" ${e.scope === 'all' ? 'checked' : ''}>Change it for all of them</label></div></div>` : ''}
    ${direct && x.used_by && x.used_by.length ? `<div class="cplaced" style="margin-top:8px"><b>Used by:</b> ${x.used_by.slice(0, 20).map(u => `<a href="#" data-ieopen="${esc(u.id)}">${esc(u.name)}</a>`).join(' · ')}</div>` : ''}
    ${!direct ? '<div class="actions"><button class="btn sm danger" id="ie-dropench">Take the enchantment off</button></div>' : ''}</div>`;
}
async function ieCost(){
  const d = IE.data, M = CR.opts.magic;
  try {
    if (d.tag === 'SPEL'){ const r = await post('/api/spells/cost', {effects: d.effects}); $('#ie-scalc').textContent = r.cost; if (d.spell.auto){ $('#ie-scost').value = r.cost; } }
    const e = d.tag === 'ENCH' ? d : d.enchant;
    if (e && $('#ie-ecalc')){ const r = await post('/api/spells/cost', {effects: e.effects, constant: +e.type === 3}); $('#ie-ecalc').textContent = r.cost; if (e.auto) $('#ie-ecost').value = r.cost; }
  } catch (err){}
}
function ieBind(){
  const d = IE.data, box = $('#itemed');
  box.querySelectorAll('[data-ief]').forEach(el => el.addEventListener(el.tagName === 'SELECT' ? 'change' : 'input', () => {
    const f = d.fields[+el.dataset.ief]; f.value = f.kind === 'str' ? el.value : (el.value === '' ? 0 : +el.value); ieDirty();
  }));
  box.querySelectorAll('[data-iebit]').forEach(el => el.onchange = () => {
    const f = d.fields[+el.dataset.iebit], bit = +el.dataset.bit; f.value = el.checked ? (+f.value | bit) : (+f.value & ~bit); ieDirty();
  });
  if ($('#ie-script')){
    ddSearch('ie-script', 'SCPT', r => { d.script = r.id; $('#ie-script').value = r.id; ieDirty(); });
    $('#ie-script').addEventListener('change', () => { d.script = $('#ie-script').value.trim(); ieDirty(); });
  }
  if ($('#ie-text')) $('#ie-text').oninput = () => { d.text = $('#ie-text').value; ieDirty(); };
  if ($('#ie-view')){ const model = (d.fields.find(f => f.label === 'Model') || {}).value; if (model) showModel($('#ie-view'), {id: d.id}, 'itemed'); else $('#ie-view').style.display = 'none'; }
  // effects lists, with the shared effects editor from Create
  if ($('#ie-effects')) effectsEditor('ie-effects', d.effects, () => { ieDirty(); ieCost(); });
  if (d.tag === 'SPEL'){
    $('#ie-stype').onchange = () => { d.spell.type = +$('#ie-stype').value; ieDirty(); };
    $('#ie-scost').oninput = () => { d.spell.cost = +$('#ie-scost').value; ieDirty(); };
    $('#ie-sauto').onchange = () => { d.spell.auto = $('#ie-sauto').checked; $('#ie-scost').disabled = d.spell.auto; ieCost(); ieDirty(); };
  }
  const e = d.tag === 'ENCH' ? d : d.enchant;
  if (e && $('#ie-eeffects')){
    effectsEditor('ie-eeffects', e.effects, () => { if (+e.type === 3) e.effects.forEach(x => x.range = 0); ieDirty(); ieCost(); });
    $('#ie-etype').onchange = () => { e.type = +$('#ie-etype').value; if (e.type === 3) e.effects.forEach(x => x.range = 0); ieRender(); ieDirty(); };
    if ($('#ie-echarge')) $('#ie-echarge').oninput = () => { e.charge = +$('#ie-echarge').value; ieDirty(); };
    $('#ie-ecost').oninput = () => { e.cost = +$('#ie-ecost').value; ieDirty(); };
    $('#ie-eauto').onchange = () => { e.auto = $('#ie-eauto').checked; $('#ie-ecost').disabled = e.auto; ieCost(); ieDirty(); };
    box.querySelectorAll('[name=ie-scope]').forEach(r => r.onchange = () => { e.scope = r.value; ieDirty(); });
  }
  const add = $('#ie-addench'); if (add) add.onclick = () => {
    const M = CR.opts.magic, first = M.effects.find(x => x.name === 'Fire Damage') || M.effects[0];
    d.enchant = {id: '', type: 1, charge: 200, cost: 10, auto: true, used_by: [], effects: [{effect: first.index, skill: -1, attribute: -1, range: 1, min: 5, max: 15, duration: 1, area: 0}]};
    ieRender(); ieDirty();
  };
  const drop = $('#ie-dropench'); if (drop) drop.onclick = () => { d.enchant = null; d.enchant_missing = null; ieRender(); ieDirty(); };
  box.querySelectorAll('[data-ieopen]').forEach(a => a.onclick = ev => { ev.preventDefault(); ieShow(a.dataset.ieopen); });
  $('#ie-other').onclick = () => { if (JSON.stringify(IE.data) !== IE.orig && !confirm('Leave your unsaved changes?')) return; IE.id = null; IE.data = null; ieWelcome(); };
  $('#ie-rec').onclick = () => { openRecord(d.i, true); showView('browse'); };
  $('#ie-revert').onclick = () => { IE.data = JSON.parse(IE.orig); ieRender(); };
  $('#ie-save').onclick = async () => {
    if (!await needProject()) return;
    const b = $('#ie-save'); b.disabled = true; b.innerHTML = '<span class="spin"></span>Saving…';
    try {
      const r = await post('/api/item/save', {id: d.id, data: IE.data});
      IE.data = r; IE.orig = JSON.stringify(r);
      toast('Saved ' + (r.name || r.id) + (r.notes && r.notes.length ? ': ' + r.notes.join('; ') : ''));
      afterChange(); ieRender();
    } catch (err){ toast(err.message, true); ieDirty(); }
  };
  ieDirty(); ieCost();
}
