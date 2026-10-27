// ---------- Scripts ----------
// Write and fix MWScript with colours, line numbers, a checker that explains mistakes in plain
// words as you type, and a searchable list of every command with examples.
const SC = {id: null, data: null, text: '', orig: '', info: null, check: null, refQ: '', refCat: null, refPick: null, newOpen: false};
const SC_KW = new Set(['begin', 'end', 'short', 'long', 'float', 'set', 'to', 'if', 'elseif', 'else', 'endif', 'while', 'endwhile', 'return']);

async function scInfo(refresh){ if (!SC.info || refresh) SC.info = await api('/api/script/info'); return SC.info; }

async function renderScripts(){
  const side = $('#sside');
  if (!side.dataset.ready){
    side.dataset.ready = '1';
    side.innerHTML = `<div class="actions" style="margin-top:0"><button class="btn sm primary" id="s-new">+ New script</button></div>
      <h3>Open a script</h3>
      <div class="dd"><input class="inp" id="s-find" placeholder="Find a script… (e.g. LocalState)" autocomplete="off"><div class="ddlist" id="s-find-l"></div></div>
      <h3>In my mod</h3><div id="s-mine"></div>
      <h3>Lua scripts (OpenMW)</h3><div id="s-lua"></div>
      <h3>Shared numbers and rules</h3><div class="drow" data-srules="global"><span>🌐 Global variables</span></div><div class="drow" data-srules="gmst"><span>⚙ Game settings</span></div>`;
    side.querySelectorAll('[data-srules]').forEach(r => r.onclick = () => ruShow(r.dataset.srules));
    ddSearch('s-find', 'SCPT', r => sOpen(r.id));
    $('#s-new').onclick = () => sNew();
    side.addEventListener('click', e => { const r = e.target.closest('[data-sopen]'); if (r) sOpen(r.dataset.sopen); });
  }
  await scInfo(true); sMine(); luMine();
  if (LU.name && LU.data){ luRender(); return; }
  if (!SC.id && !SC.newOpen) sWelcome();
}
function sMine(){
  const mine = (SC.info && SC.info.mine) || [];
  $('#s-mine').innerHTML = mine.length
    ? mine.map(s => `<div class="drow ${SC.id && SC.id.toLowerCase() === s.id.toLowerCase() ? 'on' : ''}" data-sopen="${esc(s.id)}"><span>📝 ${esc(s.id)}</span><small>${s.created ? 'new' : 'changed'}</small></div>`).join('')
    : '<div class="msg" style="padding:4px 2px">Scripts you write or change show up here.</div>';
}
function sWelcome(){
  $('#smain').innerHTML = `<div class="wrap" style="max-width:820px"><h1>Scripts</h1>
    <p class="msg" style="font-size:14px;line-height:1.7">Scripts make things happen: a door that opens only after a quest stage, a note that starts a quest when picked up.
    The editor checks what you type and explains mistakes in plain words; the list beside it has every command, with an example.</p>
    <div class="cgrid">
      <div class="ccard" data-sw="new"><div style="font-size:26px">➕</div><b>Write a new script</b><div class="msg">Start from a ready-made example: a door that stays barred, an item that moves a quest on, a timer…</div></div>
      <div class="ccard" data-sw="find"><div style="font-size:26px">🔎</div><b>Look at existing scripts</b><div class="msg">See how the base game does things, or change one for your mod (the original stays safe).</div></div>
      <div class="ccard" data-sw="ai"><div style="font-size:26px">✦</div><b>Ask the assistant</b><div class="msg">"Write a script for a lever that opens the gate when the player has the key." Then check it here.</div></div>
    </div>
    <div class="card msg" style="line-height:1.7"><b style="color:var(--text)">Three kinds of scripts</b><br>
      <b>On an object or character</b>: runs while they're nearby.<br>
      <b>Global</b>: runs everywhere, once started with <code>StartScript</code>.<br>
      <b>Start script</b>: a global one that runs from the start of the game.</div></div>`;
  $('#smain').querySelectorAll('[data-sw]').forEach(c => c.onclick = () => {
    if (c.dataset.sw === 'new') sNew(); else if (c.dataset.sw === 'find') $('#s-find').focus();
    else { AI.open = true; $('#aipanel').classList.add('open'); aiStatus().then(renderAI); }
  });
}

// ----- making a new script from an example
async function sNew(){
  if (SC.id && SC.text !== SC.orig && !confirm('Leave the changes to ' + SC.id + ' unsaved?')) return;
  showView('scripts'); await scInfo();
  SC.id = null; SC.newOpen = true;
  const prefix = (S.summary && S.summary.project ? S.summary.project.name : 'mod').replace(/[^A-Za-z0-9]/g, '').slice(0, 8) || 'mod';
  $('#smain').innerHTML = `<div class="wrap" style="max-width:900px"><h1>New script</h1>
    <div class="frow"><label>ID</label><div><input class="inp" id="sn-id" value="${esc(prefix)}_" maxlength="31" style="max-width:320px">
      <div class="hint">Players never see it. Letters, numbers and _ only, e.g. ${esc(prefix)}_GateLever.</div></div></div>
    <h3>Start from</h3>
    <div class="cgrid">${SC.info.templates.map((t, n) => `<button class="ccard ${n === 0 ? 'on' : ''}" data-tpl="${n}"><b>${esc(t.name)}</b><span class="msg">${esc(t.desc)}</span></button>`).join('')}</div>
    <div class="actions"><button class="btn primary" id="sn-go">Create script</button><span class="msg" id="sn-msg"></span></div></div>`;
  let pick = 0;
  $('#smain').querySelectorAll('[data-tpl]').forEach(b => b.onclick = () => { pick = +b.dataset.tpl; $('#smain').querySelectorAll('[data-tpl]').forEach(x => x.classList.toggle('on', x === b)); });
  $('#sn-id').focus();
  $('#sn-go').onclick = async () => {
    if (!await needProject()) return;
    const id = $('#sn-id').value.trim();
    try {
      await post('/api/script/save', {id, text: SC.info.templates[pick].text.replace(/\{id\}/g, id), create: true});
      SC.newOpen = false; toast('Created script ' + id); await scInfo(true); sOpen(id); afterChange();
    } catch (e){ $('#sn-msg').className = 'msg err'; $('#sn-msg').textContent = e.message; }
  };
}

// ----- the editor
async function sOpen(id){
  if (SC.id && SC.text !== SC.orig && SC.id.toLowerCase() !== id.toLowerCase() && !confirm('Leave the changes to ' + SC.id + ' unsaved?')) return;
  LU.name = null; LU.data = null;                 // (leaving a Lua script for an MWScript one)
  showView('scripts');
  $('#smain').innerHTML = '<div class="msg" style="padding:30px"><span class="spin"></span>Loading…</div>';
  try { await scInfo(); SC.data = await api('/api/script?id=' + encodeURIComponent(id)); }
  catch (e){ $('#smain').innerHTML = `<div class="msg err" style="padding:30px">${esc(e.message)}</div>`; return; }
  SC.newOpen = false; SC.id = SC.data.id; SC.text = SC.orig = SC.data.text.replace(/\r\n?/g, '\n'); SC.check = SC.data.check;
  sMine(); sRender();
}
function sRender(){
  const d = SC.data;
  $('#smain').innerHTML = `<div class="swrap">
    <div class="chead"><div><h1 style="margin:0">📝 ${esc(d.id)}</h1><div class="msg">${d.mine ? (d.created ? 'Made in your mod' : 'Changed in your mod') : 'From ' + esc(d.src) + '. Saving puts your changed version in your mod.'}</div></div>
      <div class="chbtns"><button class="btn sm" id="s-revert" style="visibility:hidden">↺ Undo edits</button><button class="btn primary" id="s-save" disabled>Saved</button></div></div>
    <div class="sgrid">
      <div class="scol">
        <div class="seditor" id="s-ed"><div class="sgut" id="s-gut"></div><div class="sarea"><pre class="shl" id="s-hl" aria-hidden="true"></pre><textarea id="s-ta" spellcheck="false" autocapitalize="off" autocomplete="off"></textarea></div></div>
        <div class="sprob" id="s-prob"></div>
        <div class="card sused"><h3 style="margin-top:0">Who runs it</h3><div id="s-used"></div>
          <div class="crow" style="margin-top:8px;align-items:flex-end">
            <div class="dd" style="flex:1"><input class="inp" id="s-attach" placeholder="Put it on an object or character… (search)" autocomplete="off"><div class="ddlist" id="s-attach-l"></div></div>
            <button class="btn sm" id="s-start" title="A global script that runs from the moment the game starts">▶ Run from game start</button></div></div>
      </div>
      <div class="sref card" id="s-ref"></div>
    </div></div>`;
  const ta = $('#s-ta');
  ta.value = SC.text;
  ta.oninput = () => { SC.text = ta.value; sPaint(); sDirty(); sCheckSoon(); };
  ta.onscroll = () => { $('#s-hl').scrollTop = ta.scrollTop; $('#s-hl').scrollLeft = ta.scrollLeft; $('#s-gut').scrollTop = ta.scrollTop; };
  ta.onkeydown = e => {
    if (e.key === 'Tab'){ e.preventDefault(); sInsert('\t'); }
    else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's'){ e.preventDefault(); sSave(); }
    else if (e.key === 'Enter'){
      // keep the indentation of the line above
      e.preventDefault();
      const s = ta.selectionStart, line = ta.value.slice(0, s).split('\n').pop(), ind = line.match(/^\s*/)[0];
      const more = /^\s*(if|elseif|else|while)\b/i.test(line) ? '\t' : '';
      sInsert('\n' + ind + more);
    }
  };
  $('#s-save').onclick = sSave;
  $('#s-revert').onclick = () => { SC.text = SC.orig; ta.value = SC.text; sPaint(); sDirty(); sCheckSoon(); };
  $('#s-start').onclick = () => sAttach('*start*');
  ddSearch('s-attach', 'ACTI,DOOR,CONT,MISC,BOOK,WEAP,ARMO,CLOT,NPC_,CREA,LIGH,ALCH,INGR,APPA,LOCK,PROB,REPA', r => { $('#s-attach').value = ''; sAttach(r.id); });
  sPaint(); sProblems(); sUsed(); sRef(); sDirty();
}
function sDirty(){
  const dirty = SC.text !== SC.orig, b = $('#s-save');
  if (b){ b.disabled = !dirty; b.textContent = dirty ? '💾 Save' : 'Saved'; }
  const r = $('#s-revert'); if (r) r.style.visibility = dirty ? 'visible' : 'hidden';
}
function sInsert(txt){
  const ta = $('#s-ta'), s = ta.selectionStart, e = ta.selectionEnd;
  ta.setRangeText(txt, s, e, 'end'); ta.focus();
  SC.text = ta.value; sPaint(); sDirty(); sCheckSoon();
}

// colours: keywords, commands, text in quotes, numbers, comments, variables
function sColour(line, locals){
  let out = '', i = 0;
  const n = line.length;
  while (i < n){
    const ch = line[i];
    if (ch === ';'){ out += `<span class="c-com">${esc(line.slice(i))}</span>`; break; }
    if (ch === '"'){ const j = line.indexOf('"', i + 1); const end = j < 0 ? n : j + 1; out += `<span class="c-str">${esc(line.slice(i, end))}</span>`; i = end; continue; }
    const m = line.slice(i).match(/^[A-Za-z_][\w'-]*/);
    if (m){
      const w = m[0], low = w.toLowerCase();
      const cls = SC_KW.has(low) ? 'c-kw' : locals.has(low) ? 'c-var' : SC.info && SC.info.reference.functions[low] ? 'c-fn' : '';
      out += cls ? `<span class="${cls}">${esc(w)}</span>` : esc(w);
      i += w.length; continue;
    }
    const num = line.slice(i).match(/^\d+(\.\d*)?|^\.\d+/);
    if (num && !/[\w]/.test(line[i - 1] || '')){ out += `<span class="c-num">${num[0]}</span>`; i += num[0].length; continue; }
    out += esc(ch); i++;
  }
  return out;
}
function sPaint(){
  const lines = SC.text.split('\n');
  const locals = new Set(((SC.check && SC.check.locals) || []).map(l => l[0].toLowerCase()));
  const bad = {};
  for (const m of (SC.check && SC.check.messages) || []) if (!bad[m.line] || m.sev === 'error') bad[m.line] = m.sev;
  $('#s-hl').innerHTML = lines.map((l, k) => `<div class="${bad[k + 1] ? 'l-' + bad[k + 1] : ''}">${sColour(l, locals) || ' '}</div>`).join('') + '<div> </div>';
  $('#s-gut').innerHTML = lines.map((_, k) => `<div class="${bad[k + 1] ? 'g-' + bad[k + 1] : ''}" data-gl="${k + 1}">${k + 1}</div>`).join('') + '<div> </div>';
  $('#s-gut').scrollTop = $('#s-ta').scrollTop; $('#s-hl').scrollTop = $('#s-ta').scrollTop;
}
let sCheckT = null, sCheckSeq = 0;
function sCheckSoon(){
  clearTimeout(sCheckT);
  sCheckT = setTimeout(async () => {
    const my = ++sCheckSeq;
    try { const r = await post('/api/script/check', {id: SC.id, text: SC.text}); if (my === sCheckSeq){ SC.check = r; sPaint(); sProblems(); } } catch (e){}
  }, 350);
}
function sProblems(){
  const box = $('#s-prob'); if (!box) return;
  const ms = (SC.check && SC.check.messages) || [];
  const errs = ms.filter(m => m.sev === 'error').length, warns = ms.filter(m => m.sev === 'warning').length;
  box.innerHTML = `<div class="sprobhead">${!ms.length ? '<span class="ok">✓ No problems found</span>' : `${errs ? `<span class="e">${errs} problem${errs > 1 ? 's' : ''}</span>` : ''} ${warns ? `<span class="w">${warns} thing${warns > 1 ? 's' : ''} to check</span>` : ''}`}
      <span class="msg">The game is the final judge: OpenMW reports script errors in its log when it starts.</span></div>` +
    ms.map(m => `<div class="sprobrow ${m.sev}" data-pl="${m.line}"><span class="ln">line ${m.line}</span><span>${m.sev === 'error' ? '✕' : m.sev === 'warning' ? '⚠' : 'ℹ'} ${esc(m.text)}</span></div>`).join('');
  box.querySelectorAll('[data-pl]').forEach(r => r.onclick = () => sGoLine(+r.dataset.pl));
}
function sGoLine(n){
  const ta = $('#s-ta'), lines = SC.text.split('\n');
  let pos = 0; for (let k = 0; k < n - 1 && k < lines.length; k++) pos += lines[k].length + 1;
  ta.focus(); ta.setSelectionRange(pos, pos + (lines[n - 1] || '').length);
  const lh = parseFloat(getComputedStyle(ta).lineHeight) || 19;
  ta.scrollTop = Math.max(0, (n - 4) * lh);
}
function sUsed(){
  const u = SC.data.used_by || [], box = $('#s-used');
  box.innerHTML = u.length ? u.map((x, n) => `<div class="drow"><span>${x.kind === 'NPC_' ? '👤' : x.kind === 'start' ? '▶' : x.kind === 'dialogue' ? '💬' : '◇'} ${esc(x.label)}${x.id && x.id !== x.label ? ` <small>${esc(x.id)}</small>` : ''}</span>
      <span>${x.kind === 'NPC_' ? `<button class="btn sm" data-uchar="${esc(x.id)}">Open</button>` : `<button class="btn sm" data-uopen="${x.i}">Open</button>`}${x.id || x.kind === 'start' ? `<button class="btn sm" data-udet="${n}" title="Take the script off">✕</button>` : ''}</span></div>`).join('')
    : '<div class="msg">Nothing runs it yet, so it does nothing. Put it on an object or character below, start it with <code>StartScript ' + esc(SC.id) + '</code>, or make it run from the start of the game.</div>';
  box.querySelectorAll('[data-uchar]').forEach(b => b.onclick = () => cOpen(b.dataset.uchar));
  box.querySelectorAll('[data-uopen]').forEach(b => b.onclick = () => openTool(+b.dataset.uopen));
  box.querySelectorAll('[data-udet]').forEach(b => b.onclick = () => { const x = u[+b.dataset.udet]; sAttach(x.kind === 'start' ? '*start*' : x.id, true); });
}
async function sAttach(target, detach){
  if (!await needProject()) return;
  // (a new script not saved yet has no name to put on anything: "There is no script called None", the crawl)
  if (!SC.id || SC.newOpen || SC.text !== SC.orig){ toast('Save the script first, then choose who runs it.'); return; }
  try {
    const r = await post('/api/script/attach', {id: SC.id, target, detach: !!detach});
    SC.data.used_by = r.used_by; sUsed(); afterChange();
    toast(detach ? 'Taken off' : target === '*start*' ? 'It now runs from the start of the game.' : 'Put the script on ' + target + '.');
  } catch (e){ toast(e.message, true); }
}
async function sSave(){
  if (SC.text === SC.orig || !await needProject()) return;
  if (SC.check && SC.check.errors && !confirm(`The checker found ${SC.check.errors} problem(s). The game may refuse to run this script. Save anyway?`)) return;
  const b = $('#s-save'); b.disabled = true; b.innerHTML = '<span class="spin"></span>Saving…';
  try {
    const r = await post('/api/script/save', {id: SC.id, text: SC.text});
    SC.data = r; SC.text = SC.orig = r.text.replace(/\r\n?/g, '\n'); SC.check = r.check;
    toast('Saved ' + r.id + '. Scripts apply when the game next starts.');
    await scInfo(true); sMine(); sRender(); afterChange();
  } catch (e){ toast(e.message, true); sDirty(); }
}

// ----- the command list
function sRef(){
  const box = $('#s-ref'), R = SC.info.reference, q = SC.refQ.toLowerCase().trim();
  let list;
  if (q) list = Object.values(R.functions).filter(f => f.name.toLowerCase().includes(q) || f.desc.toLowerCase().includes(q)).slice(0, 80);
  const pick = SC.refPick && R.functions[SC.refPick];
  const argNames = {i: 'ID', q: 'quest', S: 'script', c: 'place', f: 'faction', p: 'spell', s: 'text', n: 'number', x: 'X/Y/Z', '*': '…'};
  const sig = f => { const [a, o] = f.args.split('|'); return [...(a || '')].map(c => argNames[c]).concat([...(o || '')].map(c => '[' + argNames[c] + ']')).join(' '); };
  box.innerHTML = `<h3 style="margin-top:0">Commands</h3>
    <input class="inp" id="s-rq" placeholder="Search… (e.g. journal, item, door)" value="${esc(SC.refQ)}">
    ${pick ? `<div class="sfn"><b>${esc(pick.name)}</b> <span class="msg">${esc(sig(pick))}</span>${pick.value ? ' <span class="dchip">gives a value</span>' : ''}
      <div class="msg" style="margin:4px 0">${esc(pick.desc || 'No description yet.')}</div>
      <div class="msg">${pick.ref ? `Works on the object running the script, or on another with <code>id->${esc(pick.name)}</code>.` : ''}</div>
      <button class="btn sm primary" id="s-ins">Insert at cursor</button></div>` : ''}
    <div class="sreflist">${q ? list.map(f => `<div class="sfrow" data-fn="${esc(f.name.toLowerCase())}"><b>${esc(f.name)}</b><small>${esc(f.desc.split('.')[0])}</small></div>`).join('') || '<div class="msg">Nothing matches.</div>'
      : Object.entries(R.cats).map(([cat, names]) => `<details ${SC.refCat === cat ? 'open' : ''} data-cat="${esc(cat)}"><summary>${esc(cat)} <small>${names.length}</small></summary>
        ${names.map(nm => `<div class="sfrow" data-fn="${esc(nm.toLowerCase())}"><b>${esc(nm)}</b>${R.functions[nm.toLowerCase()].desc ? `<small>${esc(R.functions[nm.toLowerCase()].desc.split('.')[0])}</small>` : ''}</div>`).join('')}</details>`).join('')}</div>
    <h3>Insert an ID</h3>
    <div class="dd"><input class="inp" id="s-insid" placeholder="Search anything… (item, NPC, quest)" autocomplete="off"><div class="ddlist" id="s-insid-l"></div></div>
    <div class="msg" style="margin-top:6px">Puts the ID in quotes at the cursor.</div>`;
  const rq = $('#s-rq');
  rq.oninput = () => { SC.refQ = rq.value; const p = rq.selectionStart; sRef(); const n = $('#s-rq'); n.focus(); n.setSelectionRange(p, p); };
  box.querySelectorAll('details[data-cat]').forEach(d => d.ontoggle = () => { if (d.open) SC.refCat = d.dataset.cat; });
  box.querySelectorAll('[data-fn]').forEach(r => r.onclick = () => { SC.refPick = r.dataset.fn; sRef(); });
  const ins = $('#s-ins');
  if (ins) ins.onclick = () => {
    const ex = (pick.desc.match(/:\s*(.+)$/) || [])[1];
    sInsert(ex && ex.toLowerCase().includes(pick.name.toLowerCase()) ? ex.trim() : pick.name + ' ');
  };
  ddSearch('s-insid', 'NPC_,CREA,WEAP,ARMO,CLOT,MISC,BOOK,ALCH,INGR,CONT,DOOR,ACTI,LIGH,SPEL,DIAL,GLOB,FACT,SCPT', r => { $('#s-insid').value = ''; sInsert('"' + r.id + '"'); });
}
