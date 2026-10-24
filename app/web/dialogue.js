// ---------- Dialogue & quests ----------
// What characters say (greetings and topics), and quests with their journal stages.
// The game uses the first line, top to bottom, whose conditions all match.
const D = {mode: null, key: null, data: null, opts: null, list: [], kind: 'mine', q: '', mine: null, edit: null};
const D_ICON = {0: '💬', 1: '🔊', 2: '👋', 3: '🗝', 4: '📜'};
const D_KIND = {0: 'Topic', 1: 'Voice', 2: 'Greeting', 3: 'Persuasion', 4: 'Quest'};
const COND_KINDS = [
  ['journal', 'Quest stage'], ['item', 'Player has item'], ['dead', 'Number dead'], ['global', 'Global variable'],
  ['choice', 'Answer to a choice'], ['function', 'Other test'], ['local', "Speaker's script variable"],
  ['not_id', 'Speaker is not'], ['not_faction', 'Speaker not in faction'], ['not_class', 'Speaker class is not'],
  ['not_race', 'Speaker race is not'], ['not_cell', 'Not in place'], ['not_local', 'Speaker has no script variable']];
const COND_NAME_HINT = {journal: 'quest ID', item: 'item ID', dead: 'NPC or creature ID', global: 'global name', local: 'variable name',
  not_id: 'NPC ID', not_faction: 'faction', not_class: 'class', not_race: 'race', not_cell: 'place name', not_local: 'variable name'};

async function dOpts(){ if (!D.opts) D.opts = await api('/api/dlg/options'); return D.opts; }

async function renderDialog(){
  const side = $('#dside');
  if (!side.dataset.ready){
    side.dataset.ready = '1';
    side.innerHTML = `<div class="actions" style="margin-top:0"><button class="btn sm primary" id="d-newquest">+ New quest</button><button class="btn sm" id="d-newtopic">+ New topic</button></div>
      <h3>Characters</h3>
      <div class="dd"><input class="inp" id="d-npc" placeholder="Open anyone… (e.g. Caius Cosades)" autocomplete="off"><div class="ddlist" id="d-npc-l"></div></div>
      <div id="d-mychars"></div>
      <h3>Topics, greetings &amp; quests</h3>
      <input class="inp" id="d-q" placeholder="Find…" autocomplete="off">
      <div class="dfilters">${[['mine', 'My mod'], ['4', 'Quests'], ['0', 'Topics'], ['2', 'Greetings'], ['all', 'All']].map(([k, t]) => `<button data-dk="${k}" class="${D.kind === k ? 'on' : ''}">${t}</button>`).join('')}</div>
      <div id="d-list" class="dlist"></div>`;
    ddSearch('d-npc', 'NPC_,CREA', r => dOpen('npc', r.id));
    let t; $('#d-q').oninput = () => { clearTimeout(t); t = setTimeout(() => { D.q = $('#d-q').value; dList(); }, 200); };
    side.querySelectorAll('[data-dk]').forEach(b => b.onclick = () => { D.kind = b.dataset.dk; side.querySelectorAll('[data-dk]').forEach(x => x.classList.toggle('on', x === b)); dList(); });
    $('#d-newquest').onclick = dNewQuest;
    $('#d-newtopic').onclick = dNewTopic;
    side.addEventListener('click', e => {
      const r = e.target.closest('[data-dopen]'); if (r) dOpen(r.dataset.dmode, r.dataset.dopen);
    });
  }
  await dMine(); dList();
  if (!D.mode) dWelcome();
  qtPanel();
}

async function dMine(){
  try { D.mine = await api('/api/dlg/mine'); } catch (e){ D.mine = {characters: [], topics: []}; }
  const box = $('#d-mychars');
  box.innerHTML = D.mine.characters.length
    ? D.mine.characters.map(c => `<div class="drow ${D.mode === 'npc' && D.key && D.key.toLowerCase() === c.id.toLowerCase() ? 'on' : ''}" data-dopen="${esc(c.id)}" data-dmode="npc"><span>👤 ${esc(c.name || c.id)}</span><small>${esc(c.id)}</small></div>`).join('')
    : `<div class="msg" style="padding:4px 2px">People you create (Create → NPC) show up here.</div>`;
}

const D_PAGE = 300;
async function dList(more){
  const box = $('#d-list'); if (!box) return;
  D.listMax = more ? (D.listMax || D_PAGE) + D_PAGE : D_PAGE;     // ("Show more" adds another page)
  let rows;
  if (D.kind === 'mine' && !D.q) rows = (D.mine || {}).topics || [];
  else {
    const p = {q: D.q, limit: D.listMax + 1}; if (D.kind === 'mine') p.mine = '1'; else if (D.kind !== 'all') p.kind = D.kind;
    try { rows = await api('/api/dlg/index?' + new URLSearchParams(p)); } catch (e){ rows = []; }
  }
  box.innerHTML = rows.slice(0, D.listMax).map(r => `<div class="drow ${D.key === r.key && D.mode !== 'npc' ? 'on' : ''}" data-dopen="${esc(r.key)}" data-dmode="${r.type === 4 ? 'quest' : 'topic'}">
      <span>${D_ICON[r.type] || '💬'} ${esc(r.id)}</span><small>${r.mine_lines ? `<b class="mine">✎ ${r.mine_lines}</b> · ` : ''}${fmtN(r.lines)}</small></div>`).join('')
    + (rows.length > D.listMax ? `<button class="btn sm" id="d-more" style="margin:8px 0;width:100%">Show ${D_PAGE} more</button>` : '')
    || `<div class="msg" style="padding:6px 2px">${D.kind === 'mine' && !D.q ? 'Nothing in your mod yet. Make a quest, a topic, or open a character and give them something to say.' : 'Nothing matches.'}</div>`;
  const m = $('#d-more'); if (m) m.onclick = () => { const top = box.scrollTop; dList(true).then(() => { box.scrollTop = top; }); };
}

function dWelcome(){
  $('#dmain').innerHTML = `<div class="wrap" style="max-width:820px"><h1>Dialogue &amp; quests</h1>
    <p class="msg" style="font-size:14px;line-height:1.7">This is where your characters get their words and your mod gets its quests.</p>
    <div class="cgrid">
      <div class="ccard" data-dw="npc"><div style="font-size:26px">👤</div><b>Give a character lines</b><div class="msg">Open a character on the left and add a greeting or topics. Lines can depend on quest stages, items and more.</div></div>
      <div class="ccard" data-dw="quest"><div style="font-size:26px">📜</div><b>Make a quest</b><div class="msg">A title and numbered journal stages (10, 20 … 100). Characters' lines move it on.</div></div>
      <div class="ccard" data-dw="ai"><div style="font-size:26px">✦</div><b>Ask the assistant</b><div class="msg">"Make a short quest for Fenas: she lost a ring in the cave nearby." It writes the quest and the lines.</div></div>
    </div>
    <div class="card msg" style="line-height:1.7"><b style="color:var(--text)">How Morrowind picks a line</b><br>
      When you click a topic, the game goes down that topic's lines from the top and says the <b>first</b> one whose conditions all fit
      (who is speaking, quest stages, items…). That's why lines for a particular character go at the top, and why you can move lines up and down here.</div></div>`;
  $('#dmain').querySelectorAll('[data-dw]').forEach(c => c.onclick = () => {
    if (c.dataset.dw === 'npc') $('#d-npc').focus();
    else if (c.dataset.dw === 'quest') dNewQuest();
    else { AI.open = true; $('#aipanel').classList.add('open'); aiStatus().then(renderAI); }
  });
}

async function dOpen(mode, key){
  D.mode = mode; D.key = key; D.edit = null;
  $('#dmain').innerHTML = '<div class="msg" style="padding:30px"><span class="spin"></span>Loading…</div>';
  try {
    await dOpts();
    if (mode === 'npc') D.data = await api('/api/dlg/character?id=' + encodeURIComponent(key));
    else if (mode === 'quest') D.data = await api('/api/dlg/quest?key=' + encodeURIComponent(key));
    else D.data = await api('/api/dlg/topic?key=' + encodeURIComponent(key));
  } catch (e){ $('#dmain').innerHTML = `<div class="msg err" style="padding:30px">${esc(e.message)}</div>`; return; }
  dMine(); dList();
  dRender();
  if (mode === 'quest' && LINK.connected){ QT.questInGame = undefined; qtRefresh(true); }
}
async function dReload(){ if (D.mode) await dOpen(D.mode, D.key); await afterChange(); }

function dRender(){
  if (D.mode === 'npc') dRenderNpc();
  else if (D.mode === 'quest') dRenderQuest();
  else dRenderTopic();
  qtQuestBar(); qtMark();
}

// ----- one line, as shown in a list
function condText(c){
  const op = {'=': '=', '!=': '≠', '>': '>', '>=': '≥', '<': '<', '<=': '≤'}[c.op] || c.op;
  if (c.kind === 'function'){
    if (D.opts && c.func === D.opts.choice) return `answer ${c.value}`;
    return `${D.opts ? D.opts.functions[c.func] || 'test ' + c.func : 'test ' + c.func} ${op} ${c.value}`;
  }
  const label = {journal: 'quest', item: 'has', dead: 'dead', global: '', local: 'var', not_id: 'not', not_faction: 'not in',
                 not_class: 'class not', not_race: 'race not', not_cell: 'not in', not_local: 'no var'}[c.kind] || c.kind;
  return `${label} ${c.name} ${['not_id', 'not_faction', 'not_class', 'not_race', 'not_cell', 'not_local'].includes(c.kind) ? '' : op + ' ' + c.value}`.trim();
}
function lineHtml(l, n, showSpeaker){
  const who = [l.actor, l.race, l.cls, l.faction && l.faction !== 'FFFF' ? l.faction : '', l.cell].filter(Boolean);
  const chips = [];
  if (showSpeaker) chips.push(`<span class="dchip who">${who.length ? '🗣 ' + esc(who.join(' · ')) : 'anyone'}</span>`);
  if (l.disp) chips.push(`<span class="dchip">disposition ≥ ${l.disp}</span>`);
  if (l.sex >= 0) chips.push(`<span class="dchip">${l.sex ? 'female' : 'male'} speaker</span>`);
  for (const c of l.conds){
    // conditions the running game can answer get coloured while testing (questtest.js)
    const ck = ['journal', 'global', 'item'].includes(c.kind) ? ` data-ck="${esc(JSON.stringify([c.kind, c.name, c.op, c.value]))}"` : '';
    chips.push(`<span class="dchip ${c.kind === 'journal' ? 'q' : ''}"${ck}>${esc(condText(c))}</span>`);
  }
  return `<div class="dline ${l.mine ? 'mine' : ''}" data-ln="${n}">
    <div class="dtext">${esc(l.text) || '<i class="msg">(no text)</i>'}</div>
    ${chips.length ? `<div class="dchips">${chips.join('')}</div>` : ''}
    ${l.result ? `<pre class="dres">${esc(l.result)}</pre>` : ''}
    <div class="dbtns">${l.mine
      ? `<button class="btn sm" data-la="edit" title="Change this line">✎ Edit</button><button class="btn sm" data-la="up" title="Move up: checked earlier">↑</button><button class="btn sm" data-la="down" title="Move down: checked later">↓</button><button class="btn sm danger" data-la="del" title="Remove">✕</button>`
      : `<span class="msg">${esc(l.src)}</span><button class="btn sm" data-la="edit" title="Make your own version of this line in your mod">✎ Change</button>`}</div></div>`;
}
function bindLines(box, lines, topicKey){
  box.querySelectorAll('[data-la]').forEach(b => b.onclick = async () => {
    const n = +b.closest('[data-ln]').dataset.ln, l = lines[n], tk = typeof topicKey === 'function' ? topicKey(l) : topicKey;
    const a = b.dataset.la;
    if (a === 'edit') return dEditLine(tk, l);
    if (!await needProject()) return;
    try {
      if (a === 'del'){ if (!confirm('Remove this line?')) return; await post('/api/dlg/line/delete', {topic: tk, inam: l.inam}); toast('Line removed'); }
      else await post('/api/dlg/line/move', {topic: tk, inam: l.inam, step: a === 'up' ? -1 : 1});
      await dReload();
    } catch (e){ toast(e.message, true); }
  });
}

// ----- a character
function dRenderNpc(){
  const c = D.data;
  const all = [];
  let h = `<div class="dhead"><div><div class="dt-type">${c.type === 'CREA' ? 'Creature' : 'Character'}</div><h2>${esc(c.name || c.id)}</h2>
    <div class="msg">${esc([c.race, c.cls, c.faction].filter(Boolean).join(' · '))} · <span class="lnk" data-drec="${c.i}">record</span> · ID ${esc(c.id)}</div></div>
    <div class="actions" style="margin:0"><button class="btn primary" id="d-addgreet">+ Greeting</button><button class="btn" id="d-addtopic">+ Topic line</button><button class="btn" id="d-aiquest" title="Ask the assistant to write a quest for this character">✦ Quest idea…</button><button class="btn" data-qgo="${esc(c.id)}" style="display:none" title="Go to them in your running game">🎮 Go to</button></div></div>`;
  h += cvTabs();
  if (CV.tab !== 'lines'){
    $('#dmain').innerHTML = `<div class="dwrap cvwide">${h}<div id="cvbody"></div></div>`;
    dBindNpcHead(c); cvBindTabs(c); cvRender(c);
    return;
  }
  if (!c.topics.length) h += `<div class="card msg" style="margin-top:14px;line-height:1.7">${esc(c.name || c.id)} has no lines of their own yet, so they only say the generic things everyone of their race and class says (<span class="lnk" data-cvtab="test">see what they say</span>).<br>
      Start with a <b>greeting</b>: what they say when you talk to them. Then add <b>topics</b>, the words the player can click.</div>`;
  for (const t of c.topics){
    h += `<div class="tcard"><div class="thead"><span>${D_ICON[t.type]} <b>${esc(t.id)}</b> <span class="msg">${D_KIND[t.type]}</span></span>
      <span><span class="lnk" data-dopen2="${esc(t.key)}">whole ${t.type === 2 ? 'greeting' : 'topic'}</span> · <button class="btn sm" data-addto="${esc(t.key)}">+ Line</button></span></div>`;
    for (const l of t.lines){ l._topic = t.key; h += lineHtml(l, all.length, false); all.push(l); }
    h += `</div>`;
  }
  $('#dmain').innerHTML = `<div class="dwrap">${h}</div>`;
  bindLines($('#dmain'), all, l => l._topic);
  dBindNpcHead(c); cvBindTabs(c);
  $('#dmain').querySelectorAll('[data-addto]').forEach(b => b.onclick = () => dEditLine(b.dataset.addto, {actor: c.id, conds: []}, true));
  $('#dmain').querySelectorAll('[data-dopen2]').forEach(b => b.onclick = () => dOpen('topic', b.dataset.dopen2));
}
function dBindNpcHead(c){
  $('#d-addgreet').onclick = () => dEditLine('greeting 5', {actor: c.id, conds: []}, true);
  $('#d-addtopic').onclick = () => dPickTopic(c.id);
  $('#d-aiquest').onclick = () => {
    AI.open = true; $('#aipanel').classList.add('open');
    aiStatus().then(() => { renderAI(); const i = $('#ai-in'); if (i){ i.value = `Make a short quest for ${c.name || c.id} (${c.id}): `; i.focus(); } });
  };
  $('#dmain').querySelectorAll('[data-qgo]').forEach(b => b.onclick = () => qtGoto(b.dataset.qgo));
  const rec = $('#dmain [data-drec]'); if (rec) rec.onclick = () => { showView('browse'); openRecord(+rec.dataset.drec, true); };
}

// choose (or create) the topic for a new line
async function dPickTopic(actor){
  const bg = document.createElement('div'); bg.className = 'modal-bg';
  bg.innerHTML = `<div class="modal"><h2>Which topic?</h2><div class="msg">The word the player clicks to hear this line. Pick one that exists, or type a new one.</div>
    <label>Topic</label><div class="dd"><input class="inp" id="pt-q" placeholder="e.g. lost ring, latest rumors, little advice" autocomplete="off"><div class="ddlist" id="pt-l"></div></div>
    <div class="msg" id="pt-note" style="margin-top:8px"></div>
    <div class="foot"><button class="btn" id="pt-cancel">Cancel</button><button class="btn primary" id="pt-ok">Next</button></div></div>`;
  document.body.appendChild(bg);
  const inp = $('#pt-q'), list = $('#pt-l'); let t, rows = [];
  inp.oninput = () => { clearTimeout(t); t = setTimeout(async () => {
    const q = inp.value.trim(); if (!q){ list.style.display = 'none'; return; }
    rows = await api('/api/dlg/index?' + new URLSearchParams({q, kind: 0}));
    list.innerHTML = rows.slice(0, 30).map((r, n) => `<div data-n="${n}">${esc(r.id)}<small>${fmtN(r.lines)} lines${r.mine ? ' · in your mod' : ''}</small></div>`).join('') || '<div class="msg">New topic</div>';
    list.style.display = 'block';
    list.querySelectorAll('[data-n]').forEach(d => d.onclick = () => { inp.value = rows[+d.dataset.n].id; list.style.display = 'none'; });
    const exact = rows.find(r => r.id.toLowerCase() === q.toLowerCase());
    $('#pt-note').textContent = exact ? '' : `"${q}" is new: it will be created in your mod.`;
  }, 150); };
  inp.focus();
  $('#pt-cancel').onclick = () => bg.remove();
  $('#pt-ok').onclick = async () => {
    const name = inp.value.trim(); if (!name) return;
    if (!await needProject()) return;
    let key = name.toLowerCase();
    const rs = await api('/api/dlg/index?' + new URLSearchParams({q: name}));
    if (!rs.find(r => r.key === key)){
      try { key = (await post('/api/dlg/topic/new', {name, kind: 0})).key; } catch (e){ return toast(e.message, true); }
    }
    bg.remove();
    dEditLine(key, {actor, conds: []}, true);
  };
}

// ----- a whole topic
function dRenderTopic(){
  const t = D.data;
  const f = (D.tfilter || '').toLowerCase();
  const lines = t.lines.filter(l => !f || (l.text + ' ' + l.actor + ' ' + l.result).toLowerCase().includes(f));
  let h = `<div class="dhead"><div><div class="dt-type">${D_KIND[t.type]}</div><h2>${D_ICON[t.type]} ${esc(t.id)}</h2>
    <div class="msg">${fmtN(t.lines.length)} lines · checked from the top: the first line whose conditions all fit is said.</div></div>
    <div class="actions" style="margin:0"><button class="btn primary" id="d-addline">+ Line at the top</button></div></div>
    ${t.lines.length > 12 ? `<input class="inp" id="d-tf" placeholder="Filter these lines (text, speaker…)" value="${esc(D.tfilter || '')}" style="margin:12px 0 4px">` : ''}`;
  if (D.lineMaxFor !== t.key){ D.lineMaxFor = t.key; D.lineMax = 250; }
  const shown = lines.slice(0, D.lineMax);
  h += shown.map(l => lineHtml(l, t.lines.indexOf(l), true)).join('');
  if (lines.length > shown.length) h += `<div class="msg" style="padding:10px">Showing ${fmtN(shown.length)} of ${fmtN(lines.length)} lines.
    <button class="btn sm" id="d-lmore">Show ${fmtN(Math.min(250, lines.length - shown.length))} more</button>
    <button class="btn sm" id="d-lall">Show all</button> (or use the filter to find a line)</div>`;
  $('#dmain').innerHTML = `<div class="dwrap">${h}</div>`;
  bindLines($('#dmain'), t.lines, t.key);
  $('#d-addline').onclick = () => dEditLine(t.key, {conds: []}, true);
  const keepScroll = more => { const sc = $('#dmain').scrollTop; D.lineMax = more; dRenderTopic(); qtMark(); $('#dmain').scrollTop = sc; };
  const lm = $('#d-lmore'); if (lm) lm.onclick = () => keepScroll(D.lineMax + 250);
  const la = $('#d-lall'); if (la) la.onclick = () => keepScroll(1e9);
  const tf = $('#d-tf'); if (tf){ tf.oninput = () => { D.tfilter = tf.value; const pos = tf.selectionStart; dRenderTopic(); const n = $('#d-tf'); n.focus(); n.setSelectionRange(pos, pos); }; }
}

// ----- a quest
function dRenderQuest(){
  const q = D.data;
  D.qstages = D.qstages && D.qstagesFor === q.key ? D.qstages : q.stages.map(s => ({...s}));
  D.qstagesFor = q.key;
  const qtabs = `<div class="cvtabs">${[['stages', '📜 Stages'], ['flow', '🗺 Flow: who moves it on']].map(([k, t]) => `<button data-qtab="${k}" class="${CV.qtab === k ? 'on' : ''}">${t}</button>`).join('')}</div>`;
  if (CV.qtab === 'flow'){
    $('#dmain').innerHTML = `<div class="dwrap cvwide"><div class="dhead"><div><div class="dt-type">Quest</div><h2>📜 ${esc(q.title || q.id)}</h2><div class="msg">Quest ID <b>${esc(q.id)}</b></div></div></div>
      ${qtabs}<div id="q-test"></div><div id="q-flow"></div></div>`;
    $('#dmain').querySelectorAll('[data-qtab]').forEach(b => b.onclick = () => { CV.qtab = b.dataset.qtab; dRenderQuest(); qtQuestBar(); qtMark(); });
    cvQuestFlow(q);
    return;
  }
  let h = `<div class="dhead"><div><div class="dt-type">Quest</div><h2>📜 ${esc(q.title || q.id)}</h2><div class="msg">Quest ID <b>${esc(q.id)}</b> (used in conditions and scripts; players never see it)</div></div>
    <div class="actions" style="margin:0"><button class="btn primary" id="q-save">Save quest</button></div></div>
    ${qtabs}<div id="q-test"></div>
    <label class="dlabel">Title, as shown in the journal</label><div class="ai-row"><input class="inp" id="q-title" value="${esc(q.title)}"><button class="btn sm" data-ai="title" title="Suggest with AI">✦</button></div>
    <label class="dlabel">Stages <span class="msg">(the journal entries, by number; the game shows them as the player reaches them)</span></label>
    <div id="q-stages"></div>
    <div class="actions"><button class="btn sm" id="q-add">+ Add stage</button></div>`;
  h += `<h3 class="dsec">How the quest moves on</h3><div class="msg" style="margin-bottom:6px">Lines that start, check or advance this quest.</div>`;
  h += (q.used || []).map(u => `<div class="dline ${u.mine ? 'mine' : ''}"><div class="dtext">${esc(u.text)}</div><div class="dchips">
      <span class="dchip who">${u.actor ? '🗣 ' + esc(u.actor) : 'anyone'}</span><span class="dchip">${esc(u.topic)}</span>${u.sets ? '<span class="dchip q">moves it on</span>' : ''}${u.checks ? '<span class="dchip">checks it</span>' : ''}</div>
      <div class="dbtns">${u.actor ? `<button class="btn sm" data-qnpc="${esc(u.actor)}">Open ${esc(u.actor)}</button><button class="btn sm" data-qgo="${esc(u.actor)}" style="display:none" title="Go to them in your running game">🎮 Go to</button>` : ''}<button class="btn sm" data-qtopic="${esc(u.tkey)}">Open topic</button></div></div>`).join('')
    || `<div class="card msg">Nothing uses this quest yet. Open the character who gives it and add a greeting with the result <code>Journal "${esc(q.id)}" ${q.stages[0] ? q.stages[0].index : 10}</code>. The line editor's "Then do" buttons write that for you.</div>`;
  $('#dmain').innerHTML = `<div class="dwrap">${h}</div>`;
  const drawStages = () => {
    $('#q-stages').innerHTML = D.qstages.map((s, n) => `<div class="qstage" data-qs="${n}"><input class="inp" type="number" value="${s.index}" data-qf="index" title="Stage number">
      <textarea class="inp" data-qf="text" placeholder="What the player writes in their journal, e.g. 'Fenas asked me to find her ring.'">${esc(s.text)}</textarea>
      <div class="qside"><label title="The quest is complete at this stage"><input type="checkbox" data-qf="finished" ${s.finished ? 'checked' : ''}> Finished</label>
      <button class="btn sm" data-ai="stage" title="Suggest with AI">✦</button><button class="btn sm danger" data-qdel title="Remove stage">✕</button></div></div>`).join('')
      || '<div class="msg">No stages yet.</div>';
    $('#q-stages').querySelectorAll('[data-qf]').forEach(el => el.oninput = el.onchange = () => {
      const s = D.qstages[+el.closest('[data-qs]').dataset.qs], f = el.dataset.qf;
      s[f] = f === 'finished' ? el.checked : f === 'index' ? +el.value : el.value;
    });
    $('#q-stages').querySelectorAll('[data-qdel]').forEach(b => b.onclick = () => { D.qstages.splice(+b.closest('[data-qs]').dataset.qs, 1); drawStages(); });
    $('#q-stages').querySelectorAll('[data-ai="stage"]').forEach(b => b.onclick = () => {
      const n = +b.closest('[data-qs]').dataset.qs, ta = b.closest('[data-qs]').querySelector('textarea');
      aiDraft({kind: 'journal', quest: q.key, current: ta.value}, b, v => { ta.value = v; D.qstages[n].text = v; });
    });
  };
  drawStages();
  $('#q-add').onclick = () => { const last = D.qstages.length ? Math.max(...D.qstages.map(s => s.index)) : 0; D.qstages.push({index: last + 10, text: '', finished: false}); drawStages(); };
  $('#dmain [data-ai="title"]').onclick = e => aiDraft({kind: 'title', quest: q.key, current: $('#q-title').value}, e.target, v => $('#q-title').value = v);
  $('#q-save').onclick = async () => {
    if (!await needProject()) return;
    try {
      D.data = await post('/api/dlg/quest/save', {id: q.id, title: $('#q-title').value, stages: D.qstages});
      D.qstages = null; toast('Quest saved'); await dReload();
    } catch (e){ toast(e.message, true); }
  };
  $('#dmain').querySelectorAll('[data-qtab]').forEach(b => b.onclick = () => { CV.qtab = b.dataset.qtab; dRenderQuest(); qtQuestBar(); qtMark(); });
  $('#dmain').querySelectorAll('[data-qnpc]').forEach(b => b.onclick = () => dOpen('npc', b.dataset.qnpc));
  $('#dmain').querySelectorAll('[data-qgo]').forEach(b => b.onclick = () => qtGoto(b.dataset.qgo));
  $('#dmain').querySelectorAll('[data-qtopic]').forEach(b => b.onclick = () => dOpen('topic', b.dataset.qtopic));
}

function dAsk(title, fields, onOk){
  const bg = document.createElement('div'); bg.className = 'modal-bg';
  bg.innerHTML = `<div class="modal"><h2>${title}</h2>${fields.map(f => `<label>${f.label}</label><input class="inp" id="ask-${f.id}" placeholder="${esc(f.ph || '')}" value="${esc(f.value || '')}">${f.hint ? `<div class="msg" style="margin-top:4px">${f.hint}</div>` : ''}`).join('')}
    <div class="foot"><button class="btn" id="ask-no">Cancel</button><button class="btn primary" id="ask-ok">Create</button></div></div>`;
  document.body.appendChild(bg);
  $('#ask-' + fields[0].id).focus();
  $('#ask-no').onclick = () => bg.remove();
  $('#ask-ok').onclick = async () => { const vals = {}; for (const f of fields) vals[f.id] = $('#ask-' + f.id).value.trim(); if (await onOk(vals) !== false) bg.remove(); };
}
async function dNewQuest(){
  if (!await needProject()) return;
  const prefix = (S.summary.project.name || 'mod').replace(/[^A-Za-z0-9]/g, '').slice(0, 8);
  dAsk('New quest', [{id: 'title', label: 'Title (shown in the journal)', ph: 'The Lost Ring'},
                     {id: 'qid', label: 'Quest ID', ph: prefix + '_LostRing', hint: 'Used in scripts and conditions. Letters, numbers and _ only; keep it unique to your mod.'}], async v => {
    const id = v.qid || (prefix + '_' + v.title.replace(/[^A-Za-z0-9]/g, '')).slice(0, 31);
    if (!v.title) { toast('Give the quest a title.', true); return false; }
    try {
      const q = await post('/api/dlg/quest/save', {id, title: v.title, stages: [{index: 10, text: '', finished: false}]});
      toast('Quest created'); D.qstages = null; await dOpen('quest', q.key); afterChange();
    } catch (e){ toast(e.message, true); return false; }
  });
  const t = $('#ask-title'), i = $('#ask-qid');
  t.oninput = () => { if (!i.dataset.edited) i.value = (prefix + '_' + t.value.replace(/[^A-Za-z0-9]/g, '')).slice(0, 31); };
  i.oninput = () => { i.dataset.edited = '1'; };
}
async function dNewTopic(){
  if (!await needProject()) return;
  dAsk('New topic', [{id: 'name', label: 'Topic', ph: 'lost ring', hint: 'The word the player clicks in conversation. Mentioning it in any line makes it appear for the player.'}], async v => {
    try { const r = await post('/api/dlg/topic/new', {name: v.name, kind: 0}); toast('Topic created'); await dOpen('topic', r.key); afterChange(); }
    catch (e){ toast(e.message, true); return false; }
  });
}

// ----- AI suggestions for a piece of text
async function aiDraft(req, btn, use){
  const st = await aiStatus();
  if (!st || !st.configured){ toast('Connect the assistant first (✦ Assistant, top right).', true); AI.open = true; $('#aipanel').classList.add('open'); renderAI(); return; }
  if (req.kind !== 'journal' && req.kind !== 'title'){
    const brief = await askText('What should the line say or do? (optional, e.g. "asks the player to find her ring in the cave")', req.brief || '');
    if (brief === null) return;
    req.brief = brief;
  }
  const old = btn.innerHTML; btn.disabled = true; btn.innerHTML = '<span class="spin"></span>';
  try {
    const r = await post('/api/ai/draft', req);
    dChoose(r.options, use, btn);
  } catch (e){ toast(e.message, true); }
  finally { btn.disabled = false; btn.innerHTML = old; }
}
function dChoose(options, use, near){
  document.querySelectorAll('.dsugg').forEach(x => x.remove());
  const box = document.createElement('div'); box.className = 'dsugg';
  box.innerHTML = `<div class="msg" style="margin-bottom:4px">Pick one (you can still edit it):</div>` + options.map((o, n) => `<div class="dsopt" data-o="${n}">${esc(o)}</div>`).join('') + `<button class="btn sm" data-o="x">Close</button>`;
  near.closest('.qstage, .ai-row, .lefield, .modal, .dwrap').appendChild(box);
  box.querySelectorAll('[data-o]').forEach(d => d.onclick = () => { if (d.dataset.o !== 'x') use(options[+d.dataset.o]); box.remove(); });
}

// ----- editing one line
async function dEditLine(topicKey, line, isNew){
  if (!await needProject()) return;
  const o = await dOpts();
  const L = JSON.parse(JSON.stringify(line));
  L.conds = (L.conds || []).map(c => c.kind === 'function' && c.func === o.choice ? {...c, kind: 'choice'} : c);
  const bg = document.createElement('div'); bg.className = 'modal-bg';
  const sel = (id, list, v, empty) => `<select class="inp" id="${id}">${empty ? `<option value="">${empty}</option>` : ''}${list.map(x => `<option ${String(x).toLowerCase() === String(v || '').toLowerCase() ? 'selected' : ''}>${esc(x)}</option>`).join('')}</select>`;
  bg.innerHTML = `<div class="modal lemodal"><h2>${isNew ? 'New line' : 'Edit line'} <span class="msg">in ${esc(topicKey)}</span></h2>
    ${!isNew && !line.mine ? `<div class="msg" style="color:var(--amber)">This line comes from ${esc(line.src)}. Saving makes your own version of it in your mod.</div>` : ''}
    <label>Who says it</label>
    <div class="two" style="margin-top:0"><div class="dd"><input class="inp" id="le-actor" placeholder="A specific character (NPC ID), or leave empty for anyone" value="${esc(L.actor || '')}" autocomplete="off"><div class="ddlist" id="le-actor-l"></div></div>
      <details ${L.race || L.cls || L.faction || L.cell || L.disp || L.sex >= 0 ? 'open' : ''}><summary class="msg" style="cursor:pointer;padding-top:6px">Only certain people…</summary>
        <div class="lgrid"><span>Race</span>${sel('le-race', o.races, L.race, 'any')}<span>Class</span>${sel('le-cls', o.classes, L.cls, 'any')}
        <span>Faction</span>${sel('le-faction', o.factions, L.faction, 'any')}<span>Place</span><input class="inp" id="le-cell" value="${esc(L.cell || '')}" placeholder="any">
        <span>Sex</span><select class="inp" id="le-sex"><option value="-1">any</option><option value="0" ${L.sex === 0 ? 'selected' : ''}>male</option><option value="1" ${L.sex === 1 ? 'selected' : ''}>female</option></select>
        <span>Disposition ≥</span><input class="inp" id="le-disp" type="number" value="${L.disp || 0}"></div></details></div>
    <label>They say</label>
    <div class="lefield"><textarea class="inp" id="le-text" placeholder="What they say. You can use %PCName, %PCRace, %PCClass.">${esc(L.text || '')}</textarea>
      <div class="actions" style="margin-top:4px"><button class="btn sm" id="le-ai">✦ Suggest with AI</button><span class="msg" id="le-count"></span></div></div>
    <label>Only when <span class="msg">(all of these must be true; leave empty for always)</span></label>
    <div id="le-conds"></div><button class="btn sm" id="le-addc">+ Condition</button>
    <label>Then do <span class="msg">(result script: runs after the line is said)</span></label>
    <div class="dquick"><select class="inp" id="le-act"><option value="">Add an action…</option><option value="journal">Set a quest stage</option><option value="give">Give the player an item</option>
      <option value="take">Take an item from the player</option><option value="gold">Give gold</option><option value="topic">Add a topic for the player</option>
      <option value="choice">Offer a choice</option><option value="disp">Change disposition</option><option value="bye">End the conversation</option></select>
      <input class="inp" id="le-a1" style="display:none"><input class="inp" id="le-a2" type="number" style="display:none;max-width:90px"><button class="btn sm" id="le-aadd" style="display:none">Add</button></div>
    <textarea class="inp code" id="le-res" style="min-height:70px" placeholder="e.g. Journal &quot;MyMod_LostRing&quot; 10">${esc(L.result || '')}</textarea>
    <label class="msg" id="le-choicewrap" style="display:none;margin-top:6px"><input type="checkbox" id="le-mkans" checked> Also add an answer line for each choice (above this line)</label>
    <div class="foot"><button class="btn" id="le-cancel">Cancel</button><button class="btn primary" id="le-save">Save line</button></div></div>`;
  document.body.appendChild(bg);
  ddSearch('le-actor', 'NPC_,CREA', r => { $('#le-actor').value = r.id; });
  const qids = (await api('/api/dlg/index?' + new URLSearchParams({kind: 4}))).map(r => r.id);
  if (!$('#dl-quests')){ const dl = document.createElement('datalist'); dl.id = 'dl-quests'; document.body.appendChild(dl); }
  $('#dl-quests').innerHTML = qids.map(q => `<option value="${esc(q)}">`).join('');
  const drawConds = () => {
    $('#le-conds').innerHTML = L.conds.map((c, n) => `<div class="lcond" data-c="${n}">
      <select class="inp" data-cf="kind">${COND_KINDS.map(([k, t]) => `<option value="${k}" ${c.kind === k ? 'selected' : ''}>${t}</option>`).join('')}</select>
      ${c.kind === 'function' ? `<select class="inp" data-cf="func">${o.functions.map((f, i) => `<option value="${i}" ${c.func === i ? 'selected' : ''}>${esc(f)}</option>`).join('')}</select>`
        : c.kind === 'choice' ? '<span class="msg" style="align-self:center">number</span>'
        : `<input class="inp" data-cf="name" value="${esc(c.name || '')}" placeholder="${COND_NAME_HINT[c.kind] || ''}" ${c.kind === 'journal' ? 'list="dl-quests"' : ''}>`}
      ${c.kind.startsWith('not_') ? '<span></span><span></span>' : `<select class="inp" data-cf="op">${o.ops.map(x => `<option ${c.op === x ? 'selected' : ''}>${x}</option>`).join('')}</select><input class="inp" data-cf="value" type="number" step="any" value="${c.value ?? 0}">`}
      <button class="btn sm danger" data-cdel>✕</button></div>`).join('');
    $('#le-conds').querySelectorAll('[data-cf]').forEach(el => el.onchange = el.oninput = () => {
      const c = L.conds[+el.closest('[data-c]').dataset.c], f = el.dataset.cf;
      c[f] = f === 'func' ? +el.value : f === 'value' ? +el.value : el.value;
      if (f === 'kind'){ if (c.kind === 'function' && c.func == null) c.func = 0; drawConds(); }
    });
    $('#le-conds').querySelectorAll('[data-cdel]').forEach(b => b.onclick = () => { L.conds.splice(+b.closest('[data-c]').dataset.c, 1); drawConds(); });
  };
  drawConds();
  $('#le-addc').onclick = () => {
    if (L.conds.length >= 6) return toast('A line can have at most 6 conditions.', true);
    const myQuest = D.mine && D.mine.topics.find(t => t.type === 4);
    L.conds.push({kind: 'journal', name: D.mode === 'quest' && D.data ? D.data.id : myQuest ? myQuest.id : '', op: '<', value: 10});
    drawConds();
  };
  const text = $('#le-text'), count = () => { const n = text.value.length; $('#le-count').textContent = n > 900 ? `${n}/1023 characters` : ''; };
  text.oninput = count; count();
  $('#le-ai').onclick = e => {
    const jq = L.conds.find(c => c.kind === 'journal');
    aiDraft({kind: topicKey.startsWith('greeting') ? 'greeting' : 'topic', topic: topicKey, npc: $('#le-actor').value.trim(),
             quest: jq ? jq.name : (D.mode === 'quest' ? D.key : ''), current: text.value}, e.target, v => { text.value = v; count(); });
  };
  // quick actions for the result script
  const act = $('#le-act'), a1 = $('#le-a1'), a2 = $('#le-a2'), aadd = $('#le-aadd'), res = $('#le-res');
  const ACT = {journal: ['quest ID', 'stage', true], give: ['item ID', 'how many', true], take: ['item ID', 'how many', true], gold: [null, 'amount', true],
               topic: ['topic', null, true], choice: ['answers, separated by |  (e.g. Yes, I will | Not now)', null, true], disp: [null, 'change (+/-)', true], bye: [null, null, false]};
  act.onchange = () => {
    const a = ACT[act.value];
    a1.style.display = a && a[0] ? '' : 'none'; a1.placeholder = a && a[0] || ''; a1.value = act.value === 'journal' ? ((L.conds.find(c => c.kind === 'journal') || {}).name || (D.mode === 'quest' ? D.data.id : '')) : '';
    if (act.value === 'journal') a1.setAttribute('list', 'dl-quests'); else a1.removeAttribute('list');
    a2.style.display = a && a[1] ? '' : 'none'; a2.placeholder = a && a[1] || ''; a2.value = act.value === 'give' || act.value === 'take' ? 1 : '';
    aadd.style.display = a ? '' : 'none';
    if (act.value === 'bye') aadd.onclick();
  };
  aadd.onclick = () => {
    const v1 = a1.value.trim(), v2 = a2.value.trim();
    const line = {journal: `Journal "${v1}" ${v2 || 10}`, give: `Player->AddItem "${v1}" ${v2 || 1}`, take: `Player->RemoveItem "${v1}" ${v2 || 1}`,
                  gold: `Player->AddItem "gold_001" ${v2 || 10}`, topic: `AddTopic "${v1}"`, disp: `ModDisposition ${v2 || 10}`, bye: 'Goodbye',
                  choice: 'Choice ' + v1.split('|').map(s => s.trim()).filter(Boolean).map((s, n) => `"${s.replace(/"/g, "'")}" ${n + 1}`).join(' ')}[act.value];
    if (!line) return;
    res.value = (res.value.trim() ? res.value.trimEnd() + '\n' : '') + line;
    act.value = ''; act.onchange(); res.oninput();
  };
  res.oninput = () => { $('#le-choicewrap').style.display = isNew && /^\s*choice\s/im.test(res.value) ? '' : 'none'; };
  res.oninput();
  $('#le-cancel').onclick = () => bg.remove();
  $('#le-save').onclick = async () => {
    const btn = $('#le-save'); if (btn.disabled) return;
    const makeAnswers = isNew && $('#le-mkans').checked;
    btn.disabled = true; btn.innerHTML = '<span class="spin"></span>Saving…';
    const out = {...L, actor: $('#le-actor').value.trim(), race: $('#le-race').value, cls: $('#le-cls').value, faction: $('#le-faction').value,
                 cell: $('#le-cell').value.trim(), sex: +$('#le-sex').value, disp: +$('#le-disp').value || 0, text: text.value, result: res.value};
    out.conds = L.conds.map(c => c.kind === 'choice' ? {kind: 'function', func: o.choice, op: c.op || '=', value: c.value} : c);
    try {
      const r = await post('/api/dlg/line/save', {topic: topicKey, line: out, where: isNew ? {top: true} : null});
      // answers to a new choice: one line each, placed above the line that asks
      const m = makeAnswers && /^\s*choice\s+(.+)$/im.exec(res.value);
      if (m){
        const answers = [...m[1].matchAll(/"([^"]*)"\s+(\d+)/g)];
        for (const [, label, num] of answers.reverse())
          await post('/api/dlg/line/save', {topic: topicKey, line: {actor: out.actor, race: out.race, cls: out.cls, faction: out.faction, cell: out.cell, sex: out.sex,
            text: `(What they say when the player answers "${label}". Edit me.)`, conds: [...out.conds, {kind: 'function', func: o.choice, op: '=', value: +num}], result: ''}, where: {before: r.inam}});
      }
      bg.remove(); toast('Line saved'); await dReload();
    } catch (e){ toast(e.message, true); btn.disabled = false; btn.textContent = 'Save line'; }
  };
  text.focus();
}

// open a character's dialogue from elsewhere (World map, Create)
function openCharacterDialogue(id){ showView('dialog'); dOpen('npc', id); }
