// ---------- Lua scripts (OpenMW): a list on the Scripts page, an editor that checks as you type ----------
const LU = {name: null, data: null, orig: null, list: null, checkT: 0};
const LU_ATTACH_TYPES = 'NPC_,CREA,ACTI,CONT,DOOR,STAT,LIGH,WEAP,ARMO,CLOT,MISC,BOOK,ALCH,INGR,APPA,LOCK,PROB,REPA';

async function luMine(){
  const box = $('#s-lua'); if (!box) return;
  if (!S.summary || !S.summary.project){ box.innerHTML = '<div class="msg" style="padding:4px 2px">Start a mod to write Lua scripts.</div>'; return; }
  try { LU.list = await api('/api/lua'); } catch (e){ box.innerHTML = `<div class="msg">${esc(e.message)}</div>`; return; }
  box.innerHTML = (LU.list.scripts.length ? LU.list.scripts.map(s => `<div class="drow ${LU.name === s.name ? 'on' : ''}" data-luopen="${esc(s.name)}"><span>🌙 ${esc(s.name)}</span>
      <small>${s.errors ? `<span style="color:var(--red)">${s.errors} problem${s.errors === 1 ? '' : 's'}</span>` : esc((LU.list.kinds.find(k => k[0] === s.kind) || [0, s.kind])[1])}</small></div>`).join('')
    : '<div class="msg" style="padding:4px 2px">OpenMW Lua scripts can do what MWScript can\'t: new menus, keys, timers, changing the world as you play.</div>') +
    '<button class="btn sm" id="lu-new" style="margin-top:6px">+ New Lua script</button>';
  box.querySelectorAll('[data-luopen]').forEach(r => r.onclick = () => luOpen(r.dataset.luopen));
  $('#lu-new').onclick = luNewForm;
}
function luNewForm(){
  if (!LU.list) return;
  SC.id = null; LU.name = null; LU.data = null;
  $('#smain').innerHTML = `<div class="wrap" style="max-width:760px"><h1>🌙 New Lua script</h1>
    <p class="msg" style="line-height:1.6">Lua scripts are OpenMW's newer way of scripting. They live next to your mod (in a scripts folder) and are listed in
      a small .omwscripts file the Workshop writes for you, so the game knows when to run them. Start from an example:</p>
    <div class="frow"><label>Name</label><input class="inp" id="lu-nname" placeholder="e.g. welcome message" maxlength="40">
      <label>Start from</label><div class="radios">${LU.list.templates.map((t, i) => `<label><input type="radio" name="lu-tpl" value="${t.id}" ${i === 0 ? 'checked' : ''}>${esc(t.label)}</label>`).join('')}</div></div>
    <div class="actions"><button class="btn primary" id="lu-make">Make it</button><span class="msg" id="lu-nmsg"></span></div></div>`;
  $('#lu-make').onclick = async () => {
    if (!await needProject()) return;
    try {
      const r = await post('/api/lua/new', {name: $('#lu-nname').value, template: (document.querySelector('[name=lu-tpl]:checked') || {}).value});
      afterChange(); await luMine(); luOpen(r.name);
    } catch (e){ $('#lu-nmsg').className = 'msg err'; $('#lu-nmsg').textContent = e.message; }
  };
}
async function luOpen(name){
  if (LU.data && JSON.stringify(LU.data) !== LU.orig && !confirm('Leave your unsaved changes?')) return;
  if (!$('#scripts').classList.contains('on')) showView('scripts');
  SC.id = null;
  try { LU.data = await api('/api/lua/script?name=' + encodeURIComponent(name)); }
  catch (e){ return toast(e.message, true); }
  LU.name = LU.data.name;
  delete LU.data.problems;
  LU.orig = JSON.stringify(LU.data);
  luRender(); luMine();
}
function luRender(){
  const d = LU.data, kinds = LU.list ? LU.list.kinds : [];
  const kindInfo = kinds.find(k => k[0] === d.kind) || ['', '', ''];
  $('#smain').innerHTML = `<div class="wrap cwrap" style="max-width:1100px"><div class="chead"><div><h1 style="margin:0">🌙 ${esc(d.name)}</h1>
      <div class="msg">Lua · goes into your mod as ${esc(d.path)}</div></div>
      <div class="chbtns"><button class="btn sm" id="lu-ren">Rename</button><button class="btn sm danger" id="lu-del">Remove</button>
        <button class="btn sm" id="lu-revert" style="visibility:hidden">↺ Undo edits</button><button class="btn primary" id="lu-save" disabled>Saved</button></div></div>
    <div class="card" style="margin-bottom:12px"><div class="crow">
      ${cField('Runs', `<select class="inp" id="lu-kind">${kinds.map(k => `<option value="${k[0]}" ${k[0] === d.kind ? 'selected' : ''}>${esc(k[1])}</option>`).join('')}</select>`, esc(kindInfo[2]))}
      ${d.kind === 'CUSTOM' ? `<label class="cfield" style="flex:2"><span>On these</span><div class="ruchips" id="lu-att">${d.attach.map((a, n) => `<label class="on">${esc(a)} <a href="#" data-ludrop="${n}" title="Take it off">✕</a></label>`).join('') || '<span class="msg">Nothing chosen yet: the script runs nowhere.</span>'}</div>
        <div class="dd" style="margin-top:6px"><input class="inp" id="lu-addatt" placeholder="+ Add an NPC, creature or object… (search)" autocomplete="off"><div class="ddlist" id="lu-addatt-l"></div></div></label>` : ''}</div></div>
    <div class="luwrap"><pre class="lugut" id="lu-gut"></pre><textarea id="lu-text" spellcheck="false" wrap="off">${esc(d.text)}</textarea></div>
    <div id="lu-probs" class="luprobs"></div>
    <div class="msg" style="margin-top:8px;line-height:1.6">The Workshop writes the file and the .omwscripts list each time you save. In a running game, type <code>reloadlua</code> in the console
      (the ~ key) to load your changes without restarting. OpenMW's Lua guide: openmw.readthedocs.io → Lua scripting.</div></div>`;
  luGutter(); luProbs(null);
  const ta = $('#lu-text');
  ta.oninput = () => { d.text = ta.value; luGutter(); luDirty(); clearTimeout(LU.checkT); LU.checkT = setTimeout(luCheck, 400); };
  ta.onscroll = () => { $('#lu-gut').scrollTop = ta.scrollTop; };
  ta.onkeydown = e => {
    if (e.key === 'Tab'){ e.preventDefault(); const s = ta.selectionStart; ta.setRangeText('    ', s, ta.selectionEnd, 'end'); ta.oninput(); }
    if ((e.ctrlKey || e.metaKey) && e.key === 's'){ e.preventDefault(); $('#lu-save').click(); }
  };
  $('#lu-kind').onchange = () => { d.kind = $('#lu-kind').value; if (d.kind !== 'CUSTOM') d.attach = []; luRender(); luDirty(); luCheck(); };
  if ($('#lu-addatt')) ddSearch('lu-addatt', LU_ATTACH_TYPES, r => { if (!d.attach.some(a => a.toLowerCase() === r.id.toLowerCase())) d.attach.push(r.id); luRender(); luDirty(); });
  document.querySelectorAll('[data-ludrop]').forEach(a => a.onclick = e => { e.preventDefault(); d.attach.splice(+a.dataset.ludrop, 1); luRender(); luDirty(); });
  $('#lu-revert').onclick = () => { LU.data = JSON.parse(LU.orig); luRender(); };
  $('#lu-save').onclick = luSave;
  $('#lu-ren').onclick = async () => {
    const nn = prompt('New name for the script:', d.name); if (!nn || nn === d.name) return;
    try { const r = await post('/api/lua/save', {name: LU.name, data: Object.assign({}, d, {rename: nn})}); LU.data = r; LU.name = r.name; delete r.problems; LU.orig = JSON.stringify(r); afterChange(); luRender(); luMine(); }
    catch (e){ toast(e.message, true); }
  };
  $('#lu-del').onclick = async () => {
    if (!confirm(`Remove the Lua script "${d.name}" from your mod? (Undo brings it back.)`)) return;
    try { await post('/api/lua/delete', {name: LU.name}); LU.name = null; LU.data = null; afterChange(); luMine(); sWelcome(); toast('Removed ' + d.name); }
    catch (e){ toast(e.message, true); }
  };
  luDirty(); luCheck();
}
function luGutter(){
  const n = (LU.data.text.match(/\n/g) || []).length + 1, g = $('#lu-gut'); if (!g) return;
  g.textContent = Array.from({length: n}, (_, i) => i + 1).join('\n');
}
async function luCheck(){
  const d = LU.data; if (!d) return;
  try { const r = await post('/api/lua/check', {text: d.text, kind: d.kind}); luProbs(r.problems); } catch (e){}
}
function luProbs(list){
  const box = $('#lu-probs'); if (!box) return;
  if (!list){ box.innerHTML = '<span class="msg">Checking…</span>'; return; }
  box.innerHTML = list.length ? list.map(p => `<div class="luprob ${p.level}" data-line="${p.line}"><b>Line ${p.line}</b> ${p.level === 'error' ? '✖' : '⚠'} ${esc(p.text)}</div>`).join('')
    : '<div class="luprob ok">✔ No problems found. (The checker looks at the shape of the script and OpenMW\'s rules; the game finds the rest when it runs.)</div>';
  box.querySelectorAll('[data-line]').forEach(el => el.onclick = () => luGoto(+el.dataset.line));
}
function luGoto(line){
  const ta = $('#lu-text'), lines = ta.value.split('\n');
  const start = lines.slice(0, line - 1).reduce((a, l) => a + l.length + 1, 0);
  ta.focus(); ta.setSelectionRange(start, start + (lines[line - 1] || '').length);
  ta.scrollTop = Math.max(0, (line - 4) * 19);
}
function luDirty(){
  const x = JSON.stringify(LU.data) !== LU.orig, b = $('#lu-save'); if (!b) return;
  b.disabled = !x; b.textContent = x ? '💾 Save' : 'Saved'; $('#lu-revert').style.visibility = x ? 'visible' : 'hidden';
}
async function luSave(){
  if (!await needProject()) return;
  try {
    const r = await post('/api/lua/save', {name: LU.name, data: LU.data});
    const probs = r.problems || []; delete r.problems;
    LU.data = r; LU.orig = JSON.stringify(r); afterChange(); luDirty(); luMine(); luProbs(probs);
    toast('Saved ' + r.name + (probs.some(p => p.level === 'error') ? ' (it still has problems: see below the editor)' : ''), probs.some(p => p.level === 'error'));
  } catch (e){ toast(e.message, true); }
}
