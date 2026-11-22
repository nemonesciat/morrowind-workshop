// ---------- Lua scripts (OpenMW): a list on the Scripts page, an editor that checks as you type ----------
const LU = {name: null, data: null, orig: null, list: null, checkT: 0};
const LU_ATTACH_TYPES = 'NPC_,CREA,ACTI,CONT,DOOR,STAT,LIGH,WEAP,ARMO,CLOT,MISC,BOOK,ALCH,INGR,APPA,LOCK,PROB,REPA';

async function luMine(){
  const box = $('#s-lua'); if (!box) return;
  if (!S.summary || !S.summary.project){ box.innerHTML = '<div class="msg" style="padding:4px 2px">Start a mod to write Lua scripts.</div>'; return; }
  try { LU.list = await api('/api/lua'); } catch (e){ box.innerHTML = `<div class="msg">${esc(e.message)}</div>`; return; }
  const esp = S.summary.project.plain_esp;        // (a .esp opened as the mod: OpenMW-only things stay out of the file)
  box.innerHTML = (esp ? `<div class="msg sev-warning" style="padding:4px 2px;line-height:1.5">Your mod is a plain <b>${esc(S.summary.project.plugin)}</b>: Lua scripts only work in an OpenMW .omwaddon. Any you write are kept in the project but not saved into the mod.</div>` : '') +
    (LU.list.scripts.length ? LU.list.scripts.map(s => `<div class="drow ${LU.name === s.name ? 'on' : ''}" data-luopen="${esc(s.name)}"><span>🌙 ${esc(s.name)}</span>
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
  if (!pageOn('scripts')) showView('scripts');
  SC.id = null;
  try { LU.data = await api('/api/lua/script?name=' + encodeURIComponent(name)); }
  catch (e){ return toast(e.message, true); }
  LU.name = LU.data.name;
  delete LU.data.problems;
  LU.orig = JSON.stringify(LU.data);
  LU.gameErr = [];
  luRender(); luMine();
  // (this script's Lua errors in the game's own log: shown with the checker's, and sent by Fix)
  try { const g = await api('/api/lua/gameerrors?name=' + encodeURIComponent(name)); if (LU.name === name){ LU.gameErr = g.errors || []; luProbs(LU.lastProbs || null); } } catch (e){}
}
function luRender(){
  const d = LU.data, kinds = LU.list ? LU.list.kinds : [];
  const kindInfo = kinds.find(k => k[0] === d.kind) || ['', '', ''];
  $('#smain').innerHTML = `<div class="wrap cwrap" style="max-width:1100px"><div class="chead"><div><h1 style="margin:0">🌙 ${esc(d.name)}${typeof guideLink === 'function' ? guideLink('coding-with-ai.md', 'Writing a Lua script', 'Writing Lua with AI') : ''}</h1>
      <div class="msg">Lua · goes into your mod as ${esc(d.path)}</div></div>
      <div class="chbtns"><button class="btn sm" id="lu-ren">Rename</button><button class="btn sm danger" id="lu-del">Remove</button>
        <button class="btn sm" id="lu-fix" title="Send what the checker and the game's log found in this script to the AI to put right">✦ Fix</button>
        <button class="btn sm" id="lu-ai" title="Describe what it should do: the AI writes the script (a model on this PC: Settings › AI). Nothing is saved until you press Save">✦ Write with AI</button>
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
  $('#lu-ai').onclick = () => luAI();
  $('#lu-fix').onclick = () => luAIFix();
  $('#lu-save').onclick = luSave;
  $('#lu-ren').onclick = async () => {
    const nn = await askText('New name for the script:', d.name); if (!nn || nn === d.name) return;
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
// ✦ Write with AI: a whole script from a description (POST /api/ai/lua, ai.Assistant.lua_script). A script with real
// code in it is sent along, to be changed as asked; the editor shows the result, unsaved (↺ Undo edits takes it back).
// (what to ask for, by the kind of script: a click puts one in the box to change)
const LU_AI_EX = {
  GLOBAL: ['When the player first enters "Balmora, Guild of Mages", give them 100 gold', 'Every day at 8 in the morning, show the player "The market is open"'],
  PLAYER: ['Show "Welcome back" each time a game is loaded', 'Every 10 seconds, restore 5 fatigue to the player'],
  NPC: ['When this person dies, tell the player "You hear a scream"', 'When the player comes near, show their name on screen'],
  CREATURE: ['When this creature dies, give the player 10 gold', 'When the player comes near, show "Something growls"'],
  CUSTOM: ['When the player uses this, take them to "Balmora, Guild of Mages"', 'When the player uses this, give them a "Bread"'],
  ACTIVATOR: ['When the player uses it, show "It hums"'],
  CONTAINER: ['When the player opens it, show "It smells of mould"'],
  DOOR: ['When the player opens it, show "It creaks"'],
  MENU: ['A settings page with an on/off switch for my mod'],
  LOAD: ['A new potion called "Ashland Tea" that restores 10 fatigue'],
};
// The request for ✦ Write with AI, in a window of its own (it was one line in a small box, a tester and the user
// 2026-11-22: vague and hard to write in): where the script runs and which model writes, room to write, examples
// for its kind, and the names put in quotes looked up in the game as they are typed. {brief, fresh} or null.
function luAskBrief(d){
  return new Promise(async resolve => {
    const kinds = LU.list ? LU.list.kinds : [];
    const kind = kinds.find(k => k[0] === d.kind) || [d.kind, d.kind, ''];
    const st = await aiStatus();
    const model = st && st.local_model;
    const hasCode = !!d.text.replace(/return\s*\{\s*engineHandlers\s*=\s*\{\s*\}\s*,?\s*\}/, '').trim();
    const ex = LU_AI_EX[d.kind] || LU_AI_EX.GLOBAL;
    const bg = document.createElement('div'); bg.className = 'modal-bg';
    bg.innerHTML = `<div class="modal" style="width:min(620px,94vw)"><h2>✦ Write with AI</h2>
      <div class="msg"><span title="${esc(kind[2])}">Runs on: <b>${esc(kind[1])}</b></span> · ${model
        ? `by <b>${esc(model)}</b> on this PC`
        : '<span style="color:var(--red)">no model on this PC chosen</span> <button class="btn sm" id="wa-set">Settings</button>'}</div>
      <label for="wa-text">What should it do?</label>
      <textarea class="inp" id="wa-text" rows="5" style="width:100%;resize:vertical" placeholder="${esc('e.g. ' + ex[0])}"
        title="Plain words. Put names of places, people and things in quotes: they are looked up in your game."></textarea>
      <div class="msg" id="wa-names" style="margin-top:4px;min-height:1.4em" title="Names in quotes, as your game has them">Put names in "quotes" to look them up.</div>
      <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:8px">${ex.map((x, n) => `<button class="btn sm" data-waex="${n}" title="Put it in the box">${esc(x)}</button>`).join('')}</div>
      ${hasCode ? `<div class="radios" style="margin-top:10px"><label><input type="radio" name="wa-how" value="change" checked> Change this script</label>
        <label><input type="radio" name="wa-how" value="fresh"> Start over</label></div>` : ''}
      <div class="foot"><button class="btn" id="wa-no">Cancel</button><button class="btn primary" id="wa-ok" ${model ? '' : 'disabled'} title="Ctrl+Enter">✦ Write</button></div></div>`;
    const ta = bg.querySelector('#wa-text'); ta.value = LU.aiBrief || '';
    const done = v => { clearTimeout(t); bg.remove(); resolve(v); };
    const go = () => { const v = ta.value.trim(); if (!v || !model) return; done({brief: v, fresh: !hasCode || (bg.querySelector('[name=wa-how]:checked') || {}).value === 'fresh'}); };
    // (the names in quotes, found or not: the same look-up the writer is given, ai.Assistant.names)
    let t = 0, asked = '';
    const names = async () => {
      const v = ta.value; if (v === asked) return; asked = v;
      const box = bg.querySelector('#wa-names');
      if (!/["“][^"”\n]{2,}["”]/.test(v)){ box.textContent = 'Put names in "quotes" to look them up.'; return; }
      try {
        const r = await post('/api/ai/names', {brief: v});
        if (asked !== v) return;
        box.innerHTML = r.ready ? r.names.map(n => `<div style="color:${n.found ? 'var(--green)' : 'var(--red)'}">${n.found ? '✓' : '✗'} "${esc(n.name)}": ${esc(n.what)}</div>`).join('')
          : 'The game is still being read: names are looked up once it is.';
      } catch (e){}
    };
    ta.oninput = () => { clearTimeout(t); t = setTimeout(names, 450); };
    bg.querySelectorAll('[data-waex]').forEach(b => b.onclick = () => { ta.value = ex[+b.dataset.waex]; ta.focus(); names(); });
    const s = bg.querySelector('#wa-set'); if (s) s.onclick = () => { done(null); showView('settings'); };
    bg.querySelector('#wa-no').onclick = () => done(null);
    bg.querySelector('#wa-ok').onclick = go;
    ta.onkeydown = e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)){ e.preventDefault(); go(); } else if (e.key === 'Escape'){ e.preventDefault(); done(null); } };
    bg.onclick = e => { if (e.target === bg) done(null); };
    document.body.appendChild(bg); ta.focus(); names();
  });
}
async function luAI(){
  const d = LU.data; if (!d) return;
  const ask = await luAskBrief(d);
  if (!ask) return;
  const brief = ask.brief;
  // (a script can't see a spell being cast: "when the player casts a spell, teleport…" is a magic effect of your own,
  // whose steps (Teleport, Summon, Lua of your own…) run as it lands. A tester's script for it teleported at the start)
  if (/\bcast(s|ing)?\b[\s\S]*\bspell|\bspell\b[\s\S]*\bcast/i.test(brief)
      && !confirm('Something that happens when a spell is cast is best made as a magic effect of your own: Create › New magic effect, '
        + 'with steps such as Teleport, Summon or Lua of your own, then a spell with that effect. A script can\'t easily tell when a spell is cast.\n\nWrite a script anyway?')) return;
  LU.aiBrief = brief;
  const b = $('#lu-ai'), old = b.innerHTML, box = $('#lu-probs');
  b.disabled = true; b.innerHTML = '<span class="spin"></span> Writing…';
  if (box) box.innerHTML = '<span class="msg">Writing… (a model on this PC can take a minute or two)</span>';
  try {
    const r = await post('/api/ai/lua', {kind: d.kind, brief, current: ask.fresh ? '' : d.text});
    if (!LU.data || LU.data !== d) return;
    d.text = r.code; luRender(); luDirty();
    toast(`Written by ${r.by}${r.tries > 1 ? ` (put right ${r.tries - 1} time${r.tries > 2 ? 's' : ''})` : ''}. Read it over, then Save.`, !!r.problems.length);
    // (a script on objects that asks the whole-game script for something: that one was written too, added on a yes)
    const c = r.companion;
    if (c && confirm(`This script asks a script that runs for the whole game to do ${c.events.join(', ')}. ${r.by} wrote that one too`
        + `${c.missing.length ? ` (it doesn't seem to do ${c.missing.join(', ')}: read it over)` : ''}. Add it to your mod as the Lua script "${d.name} world"?`)){
      try {
        const made = await post('/api/lua/new', {name: d.name + ' world', template: 'blank'});
        await post('/api/lua/save', {name: made.name, data: Object.assign({}, made, {kind: 'GLOBAL', attach: [], text: c.code})});
        afterChange(); luMine();
        toast(`Added "${made.name}", which runs for the whole game. Save this one too.`);
      } catch (e){ toast(e.message, true); }
    }
  } catch (e){ toast(e.message, true); luProbs(null); luCheck(); }
  finally { const b2 = $('#lu-ai'); if (b2){ b2.disabled = false; b2.innerHTML = old; } }
}
// ✦ Fix: what the checker found and the game's log says about this script, to the AI to put right (unsaved after)
async function luAIFix(){
  const d = LU.data; if (!d) return;
  const probs = (LU.lastProbs || []).filter(p => p.level === 'error' || p.api).map(p => `line ${p.line}: ${p.text}`);
  const game = (LU.gameErr || []).map(t => 'in the game: ' + t);
  if (!probs.length && !game.length){ toast('Nothing to fix: the checker finds nothing, and the game\'s log has no errors from this script.'); return; }
  LU.aiBrief = 'Put right these problems and keep what the script does: ' + probs.concat(game).join('; ');
  const b = $('#lu-fix'), old = b.innerHTML;
  b.disabled = true; b.innerHTML = '<span class="spin"></span> Fixing…';
  try {
    const r = await post('/api/ai/lua', {kind: d.kind, brief: LU.aiBrief, current: d.text});
    if (!LU.data || LU.data !== d) return;
    d.text = r.code; luRender(); luDirty();
    toast(`Put right by ${r.by}. Read it over, then Save, and try it in the game again.`, !!r.problems.length);
  } catch (e){ toast(e.message, true); }
  finally { const b2 = $('#lu-fix'); if (b2){ b2.disabled = false; b2.innerHTML = old; } }
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
  LU.lastProbs = list;
  const game = (LU.gameErr || []).map(t => `<div class="luprob error" title="From the game's openmw.log, the last time it ran this script">✖ In the game: ${esc(t)}</div>`).join('');
  box.innerHTML = game + (list.length ? list.map(p => `<div class="luprob ${p.level}" data-line="${p.line}"><b>Line ${p.line}</b> ${p.level === 'error' ? '✖' : '⚠'} ${esc(p.text)}</div>`).join('')
    : '<div class="luprob ok">✔ No problems found. (The checker looks at the shape of the script and OpenMW\'s rules; the game finds the rest when it runs.)</div>');
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
