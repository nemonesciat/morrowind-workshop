// ---------- The conversation builder (convbuild.py) ----------
// One character, one topic: what they say (versions, the first that fits is said), the answers the
// player can give, and what each answer leads to. Saved, it becomes the topic's own lines.
// (A tab of the character view in Dialogue, beside the map and the tester in convo.js.)
const CB = {topic: null, tree: null, list: null, dirty: false, reg: [], for: null};
const CB_ACTS = {journal: ['📜 Set a quest stage', 'quest ID', 'stage'], give: ['🎁 Give the player', 'item ID', 'how many'],
  take: ['✋ Take from the player', 'item ID', 'how many'], topic: ['💬 Add a topic', 'topic', null], disp: ['♥ Change disposition', null, '+/−'],
  bye: ['👋 End the conversation', null, null]};

(function cbStyle(){
  const st = document.createElement('style');
  st.textContent = `
.cbpick{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:10px 0}
.cbpick button{background:none;border:1px solid var(--line2);border-radius:14px;color:var(--muted);padding:3px 11px;font:inherit;font-size:12.5px;cursor:pointer}
.cbpick button.on{border-color:var(--gold);color:var(--gold2);background:var(--panel2)}
.cbpick button small{color:var(--faint)}
.cbtree{overflow:auto;max-height:calc(100vh - 300px);min-height:300px;border:1px solid var(--line);border-radius:10px;background:var(--deep)}
.cbinner{padding:16px 16px 40px;width:max-content;min-width:100%}
.cbgroup{display:flex;flex-direction:column;gap:12px}
.cbrow{display:flex;align-items:flex-start}
.cbcard{width:380px;flex:none;border:1px solid var(--line2);border-radius:10px;background:var(--panel);padding:9px 11px}
.cbcard.game{border-style:dashed}
.cbcard .cbh{display:flex;justify-content:space-between;align-items:center;gap:6px;font-size:11.5px;color:var(--gold);text-transform:uppercase;letter-spacing:.06em;margin-bottom:5px}
.cbcard .cbh .msg{text-transform:none;letter-spacing:0;display:flex;gap:3px;align-items:center}
.cbcard textarea{width:100%;min-height:62px;resize:vertical;font-size:13.5px;line-height:1.45}
.cbcard .cbsec{margin-top:6px;font-size:12px}
.cbcard .cbsec > summary{cursor:pointer;color:var(--muted)}
.cbline{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr) 54px 60px 24px;gap:4px;margin-top:4px;align-items:center}
.cbline.act{grid-template-columns:minmax(0,1.4fr) minmax(0,1.2fr) 64px 24px}
.cbline .inp{padding:3px 5px;font-size:12px;min-width:0}
.cbline button{padding:0 5px}
.cbtools{display:flex;gap:4px;flex-wrap:wrap;margin-top:7px;align-items:center}
.cbtools .btn{font-size:11.5px;padding:2px 8px}
.cbans{display:flex;flex-direction:column;gap:14px;padding-left:34px;position:relative;margin-top:16px}
.cbarow{display:flex;align-items:flex-start;position:relative}
.cbarow::before{content:"";position:absolute;left:-34px;top:15px;width:34px;border-top:2px solid var(--goldline)}
.cbarow::after{content:"";position:absolute;left:-34px;top:-14px;bottom:0;border-left:2px solid var(--goldline)}
.cbarow:first-child::after{top:-16px}
.cbarow:last-child::after{bottom:auto;height:30px}
.cbarow:first-child:last-child::after{height:32px}
.cbtools select.inp{width:auto !important;flex:0 0 auto;max-width:170px}
.cbpill{width:210px;flex:none;margin-right:30px;position:relative}
.cbpill::after{content:"";position:absolute;right:-30px;top:15px;width:30px;border-top:2px dashed var(--line2)}
.cbpill .inp{width:100%;border-color:var(--blue);color:var(--blue);font-size:13px;padding:5px 26px 5px 9px;border-radius:16px}
.cbpill .x{position:absolute;right:7px;top:5px;background:none;border:0;color:var(--faint);cursor:pointer}
.cbpill .n{font-size:10.5px;color:var(--faint);margin:2px 0 0 10px}
.cbempty{border:1px dashed var(--line2);border-radius:10px;padding:10px;color:var(--faint);font-size:12.5px;width:380px}
.cbnotes{margin:6px 0;color:var(--amber);font-size:12.5px}
.cbbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:8px 0}`;
  document.head.appendChild(st);
})();

async function cbOpen(c){
  const box = $('#cvbody');
  box.innerHTML = '<div class="msg" style="padding:20px"><span class="spin"></span>Reading their conversations…</div>';
  try { CB.list = await api('/api/convo/build/list?' + new URLSearchParams({id: c.id})); }
  catch (e){ box.innerHTML = `<div class="msg err">${esc(e.message)}</div>`; return; }
  if (CB.for !== c.id){ CB.for = c.id; CB.topic = null; CB.tree = null; CB.dirty = false; }
  if (!CB.topic && CB.list.length) CB.topic = (CB.list.find(x => x.choices) || CB.list[0]).topic;
  if (CB.topic && !CB.tree) return cbLoad(c, CB.topic);
  cbDraw(c);
}
async function cbLoad(c, topic){
  CB.topic = topic; CB.tree = null; CB.dirty = false;
  cbDraw(c);
  try { CB.tree = await api('/api/convo/build?' + new URLSearchParams({id: c.id, topic})); }
  catch (e){ toast(e.message, true); return; }
  if (CV.tab === 'build') cbDraw(c);
}
function cbDraw(c){
  const box = $('#cvbody'); if (!box) return;
  const kindName = t => t === 2 ? '👋' : t === 3 ? '🗝' : '💬';
  const known = CB.list.some(x => x.topic === CB.topic);
  let h = `<div class="msg" style="margin-top:6px;line-height:1.6">Write what ${esc(c.name || c.id)} says in a topic as a tree: what they say (more than one version: the first that fits is said), the answers the player can pick, and what each answer leads to.
      Saving turns it into the topic's lines, numbered and ordered the way the game needs.</div>
    <div class="cbpick">${CB.list.map(x => `<button data-cbt="${esc(x.topic)}" class="${x.topic === CB.topic ? 'on' : ''}">${kindName(x.type)} ${esc(x.id)} <small>${x.lines}${x.choices ? ' · branches' : ''}</small></button>`).join('')}
      ${CB.topic && !known ? `<button class="on">${CB.topic.startsWith('greeting') ? '👋' : '💬'} ${esc(CB.tree ? CB.tree.id : CB.topic)} <small>new</small></button>` : ''}
      <button id="cb-new" title="A topic (or greeting) they have nothing of their own in yet">+ New conversation…</button></div>`;
  if (!CB.topic){
    h += `<div class="card msg" style="line-height:1.7">${esc(c.name || c.id)} has no lines of their own yet. Start with <b>+ New conversation…</b>: pick the topic the player clicks (or their greeting), then write what they say.</div>`;
  } else if (!CB.tree){
    h += '<div class="msg" style="padding:14px"><span class="spin"></span>Reading…</div>';
  } else {
    CB.reg = [];
    h += `<div class="cbbar"><button class="btn primary" id="cb-save" ${CB.dirty ? '' : 'disabled'}>${CB.dirty ? 'Save conversation' : 'Saved'}</button>
        <button class="btn" id="cb-try" title="Save, then talk to them in the tester">▶ Try it</button>
        <span class="msg">${CB.tree.type === 2 ? 'Greeting: said when the player starts talking to them' : `Topic “${esc(CB.tree.id)}”: said when the player clicks it`} · versions are checked top to bottom</span></div>
      ${CB.tree.notes.length ? `<div class="cbnotes">⚠ ${CB.tree.notes.map(esc).join('<br>⚠ ')}</div>` : ''}
      <div class="cbtree"><div class="cbinner">${cbGroup(CB.tree.say)}</div></div>`;
  }
  box.innerHTML = h;
  box.querySelectorAll('[data-cbt]').forEach(b => b.onclick = () => {
    if (CB.dirty && !confirm('Leave this conversation without saving it?')) return;
    cbLoad(c, b.dataset.cbt);
  });
  $('#cb-new').onclick = () => cbNew(c);
  if (!CB.tree) return;
  $('#cb-save').onclick = () => cbSave(c);
  $('#cb-try').onclick = async () => {
    if (CB.dirty && !await cbSave(c)) return;
    CV.tab = 'test'; CV.log = []; CV.last = null; CV.autoTopic = CB.topic; dRenderNpc();
  };
  cbBind(c, box);
}
// a group of versions (what they say), each with its answers to the right
function cbGroup(vers){
  const gid = CB.reg.push({list: vers}) - 1;
  if (!vers.length) return `<div class="cbempty">Nothing yet. <button class="btn sm" data-cbaddv="${gid}">+ What they say</button></div>`;
  return `<div class="cbgroup">${vers.map((v, i) => cbVersion(v, i, gid)).join('')}
    <div><button class="btn sm" data-cbaddv="${gid}" title="Another version, checked after the ones above: give the ones above conditions, so this one is said when they don't fit">+ Another version</button></div></div>`;
}
function cbVersion(v, i, gid){
  const vid = CB.reg.push({v, gid, i}) - 1;
  const list = CB.reg[gid].list;
  const head = i === 0 ? (list.length > 1 ? 'They say, if this fits' : 'They say') : (v.conds.length || v.disp ? 'Otherwise, if this fits' : 'Otherwise they say');
  const fns = D.opts ? D.opts.functions : [];
  const conds = v.conds.map((cd, n) => `<div class="cbline" data-cbc="${vid}|${n}">
      <select class="inp" data-cf="kind">${COND_KINDS.filter(([k]) => k !== 'choice').map(([k, t]) => `<option value="${k}" ${cd.kind === k ? 'selected' : ''}>${t}</option>`).join('')}</select>
      ${cd.kind === 'function' ? `<select class="inp" data-cf="func">${fns.map((f, fi) => `<option value="${fi}" ${cd.func === fi ? 'selected' : ''}>${esc(f)}</option>`).join('')}</select>`
        : `<input class="inp" data-cf="name" value="${esc(cd.name || '')}" placeholder="${COND_NAME_HINT[cd.kind] || ''}" ${cd.kind === 'journal' ? 'list="dl-quests"' : ''}>`}
      ${cd.kind.startsWith('not_') ? '<span></span><span></span>' : `<select class="inp" data-cf="op">${['=', '!=', '>', '>=', '<', '<='].map(x => `<option ${cd.op === x ? 'selected' : ''}>${x}</option>`).join('')}</select><input class="inp" data-cf="value" type="number" step="any" value="${cd.value ?? 0}">`}
      <button class="btn sm danger" data-cbcdel title="Remove">✕</button></div>`).join('');
  const acts = v.actions.map((a, n) => { const A = CB_ACTS[a.kind] || [a.kind]; return `<div class="cbline act" data-cba="${vid}|${n}"><span>${A[0]}</span>
      ${A[1] ? `<input class="inp" data-af="id" value="${esc(a.id || '')}" placeholder="${A[1]}" ${a.kind === 'journal' ? 'list="dl-quests"' : ''}>` : '<span></span>'}
      ${A[2] ? `<input class="inp" type="number" data-af="n" value="${a.n ?? ''}" placeholder="${A[2]}">` : '<span></span>'}
      <button class="btn sm danger" data-cbadel title="Remove">✕</button></div>`; }).join('');
  const ans = v.answers.map((a, n) => `<div class="cbarow"><div class="cbpill"><input class="inp" data-cbal="${vid}|${n}" value="${esc(a.label || '')}" placeholder="What the player answers">
      <button class="x" data-cbadx="${vid}|${n}" title="Remove this answer and what follows it">✕</button>
      <div class="n">${a.n ? `answer ${a.n}` : 'new answer'}${a.shared ? ' · its number is shared with another question' : ''}</div></div>${cbGroup(a.say)}</div>`).join('');
  return `<div class="cbrow"><div class="cbcard ${v.inam && !v.mine ? 'game' : ''}">
      <div class="cbh"><span>${head}</span><span class="msg">${v.inam ? (v.mine ? 'yours' : esc(v.src)) : 'new'}
        <button class="btn sm" data-cbmv="${vid}|-1" title="Check it earlier" ${i === 0 ? 'disabled' : ''}>↑</button><button class="btn sm" data-cbmv="${vid}|1" title="Check it later" ${i === list.length - 1 ? 'disabled' : ''}>↓</button>
        <button class="btn sm danger" data-cbvdel="${vid}" title="Remove this version">✕</button></span></div>
      <textarea class="inp" data-cbtext="${vid}" placeholder="What they say. %PCName, %PCRace and %PCClass work too.">${esc(v.text || '')}</textarea>
      ${v.conds.length ? `<div class="cbsec"><span class="msg">Only when:</span>${conds}</div>` : ''}
      ${v.disp ? `<div class="cbsec msg">and they like the player at least <input class="inp" type="number" data-cbdisp="${vid}" value="${v.disp}" style="width:60px;padding:2px 5px"> <span class="lnk" data-cbdispx="${vid}">remove</span></div>` : ''}
      ${v.actions.length ? `<div class="cbsec"><span class="msg">Then:</span>${acts}</div>` : ''}
      ${v.script ? `<details class="cbsec" open><summary>More script</summary><textarea class="inp code" data-cbscript="${vid}" style="min-height:44px;font-size:12px;width:100%">${esc(v.script)}</textarea></details>` : ''}
      <div class="cbtools"><button class="btn sm" data-cbaddc="${vid}">+ Only when…</button>
        <select class="inp" data-cbadda="${vid}" style="width:auto;font-size:11.5px;padding:2px 6px"><option value="">+ Then…</option>${Object.entries(CB_ACTS).map(([k, A]) => `<option value="${k}">${A[0]}</option>`).join('')}<option value="script">⌨ Script of your own</option>${v.disp ? '' : '<option value="disp_need">♥ Only if they like the player enough</option>'}</select>
        <button class="btn sm" data-cbaddans="${vid}" title="Let the player answer; each answer leads on">+ Answer</button>
        <button class="btn sm" data-cbai="${vid}" title="Suggest the words with AI">✦</button></div>
    </div>${v.answers.length ? `<div class="cbans">${ans}</div>` : ''}</div>`;
}
function cbNewVersion(){ return {inam: null, text: '', conds: [], disp: 0, actions: [], script: '', answers: [], mine: true, keep: {}}; }
function cbBind(c, box){
  const dirty = () => { if (!CB.dirty){ CB.dirty = true; const b = $('#cb-save'); if (b){ b.disabled = false; b.textContent = 'Save conversation'; } } };
  const redraw = () => {
    dirty();
    const sc = box.querySelector('.cbtree'), l = sc ? sc.scrollLeft : 0, t = sc ? sc.scrollTop : 0;
    cbDraw(c);
    const n = box.querySelector('.cbtree'); if (n){ n.scrollLeft = l; n.scrollTop = t; }
  };
  const vOf = s => CB.reg[+s].v;
  box.querySelectorAll('[data-cbtext]').forEach(t => t.oninput = () => { vOf(t.dataset.cbtext).text = t.value; dirty(); });
  box.querySelectorAll('[data-cbscript]').forEach(t => t.oninput = () => { vOf(t.dataset.cbscript).script = t.value; dirty(); });
  box.querySelectorAll('[data-cbdisp]').forEach(t => t.oninput = () => { vOf(t.dataset.cbdisp).disp = +t.value || 0; dirty(); });
  box.querySelectorAll('[data-cbdispx]').forEach(t => t.onclick = () => { vOf(t.dataset.cbdispx).disp = 0; redraw(); });
  box.querySelectorAll('[data-cbal]').forEach(t => t.oninput = () => { const [vid, n] = t.dataset.cbal.split('|'); vOf(vid).answers[+n].label = t.value; dirty(); });
  box.querySelectorAll('[data-cbaddv]').forEach(b => b.onclick = () => { CB.reg[+b.dataset.cbaddv].list.push(cbNewVersion()); redraw(); });
  box.querySelectorAll('[data-cbvdel]').forEach(b => b.onclick = () => {
    const r = CB.reg[+b.dataset.cbvdel], list = CB.reg[r.gid].list;
    const game = r.v.inam && !r.v.mine;
    if ((r.v.answers.length || game) && !confirm(game ? 'This line is the game\'s own: your mod will take it out of the game. Remove it?' : 'Remove this version and the answers after it?')) return;
    list.splice(r.i, 1); redraw();
  });
  box.querySelectorAll('[data-cbmv]').forEach(b => b.onclick = () => {
    const [vid, s] = b.dataset.cbmv.split('|'), r = CB.reg[+vid], list = CB.reg[r.gid].list, j = r.i + +s;
    if (j < 0 || j >= list.length) return;
    [list[r.i], list[j]] = [list[j], list[r.i]]; redraw();
  });
  box.querySelectorAll('[data-cbaddans]').forEach(b => b.onclick = () => { vOf(b.dataset.cbaddans).answers.push({label: '', n: null, say: [cbNewVersion()]}); redraw(); });
  box.querySelectorAll('[data-cbadx]').forEach(b => b.onclick = () => {
    const [vid, n] = b.dataset.cbadx.split('|'), a = vOf(vid).answers[+n];
    if (a.say.some(x => x.text || x.answers.length) && !confirm('Remove this answer and everything after it?')) return;
    vOf(vid).answers.splice(+n, 1); redraw();
  });
  box.querySelectorAll('[data-cbaddc]').forEach(b => b.onclick = () => {
    const v = vOf(b.dataset.cbaddc);
    if (v.conds.length >= 5) return toast('A line can have at most 6 conditions, and an answer uses one of them.', true);
    const myQuest = D.mine && D.mine.topics.find(t => t.type === 4);
    v.conds.push({kind: 'journal', name: myQuest ? myQuest.id : '', op: '>=', value: 10}); redraw();
  });
  box.querySelectorAll('[data-cbadda]').forEach(s => s.onchange = () => {
    const v = vOf(s.dataset.cbadda), k = s.value; if (!k) return;
    if (k === 'script') v.script = v.script || '; your script here';
    else if (k === 'disp_need') v.disp = 50;
    else v.actions.push({kind: k, id: k === 'journal' ? ((v.conds.find(x => x.kind === 'journal') || {}).name || '') : '', n: k === 'disp' ? 5 : k === 'journal' ? 10 : 1});
    redraw();
  });
  box.querySelectorAll('[data-cbc]').forEach(row => {
    const [vid, n] = row.dataset.cbc.split('|'), cd = vOf(vid).conds[+n];
    row.querySelectorAll('[data-cf]').forEach(el => el.oninput = el.onchange = () => {
      const f = el.dataset.cf;
      cd[f] = f === 'func' || f === 'value' ? +el.value : el.value; dirty();
      if (f === 'kind'){ if (cd.kind === 'function' && cd.func == null) cd.func = 0; redraw(); }
    });
    row.querySelector('[data-cbcdel]').onclick = () => { vOf(vid).conds.splice(+n, 1); redraw(); };
  });
  box.querySelectorAll('[data-cba]').forEach(row => {
    const [vid, n] = row.dataset.cba.split('|'), a = vOf(vid).actions[+n];
    row.querySelectorAll('[data-af]').forEach(el => el.oninput = () => { a[el.dataset.af] = el.dataset.af === 'n' ? +el.value : el.value; dirty(); });
    row.querySelector('[data-cbadel]').onclick = () => { vOf(vid).actions.splice(+n, 1); redraw(); };
  });
  box.querySelectorAll('[data-cbai]').forEach(b => b.onclick = () => {
    const v = vOf(b.dataset.cbai), ta = box.querySelector(`[data-cbtext="${b.dataset.cbai}"]`);
    const jq = v.conds.find(x => x.kind === 'journal');
    aiDraft({kind: CB.topic.startsWith('greeting') ? 'greeting' : 'topic', topic: CB.topic, npc: c.id, quest: jq ? jq.name : '', current: ta.value},
            b, t => { ta.value = t; v.text = t; dirty(); });
  });
  // quest IDs for the "quest stage" boxes
  if (!$('#dl-quests')){
    const dl = document.createElement('datalist'); dl.id = 'dl-quests'; document.body.appendChild(dl);
    api('/api/dlg/index?' + new URLSearchParams({kind: 4})).then(rs => { dl.innerHTML = rs.map(r => `<option value="${esc(r.id)}">`).join(''); }).catch(() => {});
  }
}
async function cbSave(c){
  if (!await needProject()) return false;
  const btn = $('#cb-save'); if (btn){ btn.disabled = true; btn.innerHTML = '<span class="spin"></span>Saving…'; }
  try {
    CB.tree = await post('/api/convo/build/save', {id: c.id, topic: CB.topic, tree: CB.tree});
    CB.dirty = false;
    CB.list = await api('/api/convo/build/list?' + new URLSearchParams({id: c.id}));
    toast('Conversation saved');
    cbDraw(c); afterChange();
    return true;
  } catch (e){ toast(e.message, true); if (btn){ btn.disabled = false; btn.textContent = 'Save conversation'; } return false; }
}
// a new conversation: a topic (one that exists, or a new word) or their greeting
function cbNew(c){
  if (CB.dirty && !confirm('Leave this conversation without saving it?')) return;
  const bg = document.createElement('div'); bg.className = 'modal-bg';
  bg.innerHTML = `<div class="modal"><h2>New conversation</h2>
    <label style="display:block"><input type="radio" name="cbk" value="greet" checked> When they greet the player</label>
    <label style="display:block;margin-top:6px"><input type="radio" name="cbk" value="topic"> When the player clicks a topic</label>
    <div class="dd" style="margin-top:6px"><input class="inp" id="cbn-q" placeholder="e.g. lost ring, little secret, my trade" autocomplete="off" disabled><div class="ddlist" id="cbn-l"></div></div>
    <div class="msg" id="cbn-note" style="margin-top:8px">Their own greeting goes before the ones everyone of their kind has, so it's what they say first.</div>
    <div class="foot"><button class="btn" id="cbn-no">Cancel</button><button class="btn primary" id="cbn-ok">Start writing</button></div></div>`;
  document.body.appendChild(bg);
  const inp = $('#cbn-q'), list = $('#cbn-l'); let t, rows = [];
  bg.querySelectorAll('[name=cbk]').forEach(r => r.onchange = () => {
    const topic = bg.querySelector('[name=cbk]:checked').value === 'topic'; inp.disabled = !topic;
    $('#cbn-note').textContent = topic ? 'The word the player clicks: any topic, or a new one. Mention it in a line (or add it with "+ Then…") so the player learns it.'
      : 'Their own greeting goes before the ones everyone of their kind has, so it\'s what they say first.';
    if (topic) inp.focus();
  });
  inp.oninput = () => { clearTimeout(t); t = setTimeout(async () => {
    const q = inp.value.trim(); if (!q){ list.style.display = 'none'; return; }
    rows = await api('/api/dlg/index?' + new URLSearchParams({q, kind: 0}));
    list.innerHTML = rows.slice(0, 30).map((r, n) => `<div data-n="${n}">${esc(r.id)}<small>${fmtN(r.lines)} lines</small></div>`).join('') || '<div class="msg">New topic</div>';
    list.style.display = 'block';
    list.querySelectorAll('[data-n]').forEach(d => d.onclick = () => { inp.value = rows[+d.dataset.n].id; list.style.display = 'none'; });
  }, 150); };
  $('#cbn-no').onclick = () => bg.remove();
  $('#cbn-ok').onclick = async () => {
    if (!await needProject()) return;
    let key = 'greeting 5';
    if (bg.querySelector('[name=cbk]:checked').value === 'topic'){
      const name = inp.value.trim(); if (!name) return toast('Which topic?', true);
      key = name.toLowerCase();
      const rs = await api('/api/dlg/index?' + new URLSearchParams({q: name}));
      if (!rs.find(r => r.key === key)){
        try { key = (await post('/api/dlg/topic/new', {name, kind: 0})).key; } catch (e){ return toast(e.message, true); }
      }
    }
    bg.remove();
    await cbLoad(c, key);
    if (CB.tree && !CB.tree.say.length){ CB.tree.say.push(cbNewVersion()); CB.dirty = true; cbDraw(c); }
  };
}
