// ---------- The person card: everything about one person, docked under the 3D view ----------
// (person.py reads and writes.) Tabs with icons: 💬 Talk (what they say now, their lines, + a line in plain
// terms), 🎒 Gear (what they wear, what they carry, as the items' own icons), 🪙 Trade (what they buy and sell,
// their services), 🧭 Travel (where they take travellers), 🧩 Quests (theirs, and a whole job in a few answers).
// A container gets the same icon grid. Right-click a person or a container for each of these.
const PCD = {kind: null, id: null, d: null, tab: 'talk', form: {kind: 'topic', when: {}}, job: null, sel: null, opts: null, spot: null};

(function(){
  const st = document.createElement('style');
  st.textContent = `#pc-dock{position:absolute;left:0;right:0;bottom:0;height:46%;z-index:40;background:var(--panel);border-top:2px solid var(--gold,#b8954a);
      display:flex;flex-direction:column;box-shadow:0 -6px 18px #0007}
    #pc-dock .pc-bar{display:flex;align-items:center;gap:8px;padding:4px 10px;border-bottom:1px solid var(--line);white-space:nowrap}
    #pc-dock .pc-grip{cursor:ns-resize;padding:0 6px;font-size:18px;line-height:12px;color:var(--muted)}
    #pc-dock .pc-sub{color:var(--muted);font-size:12px;overflow:hidden;text-overflow:ellipsis}
    #pc-dock .pc-tabs{display:flex;gap:2px;padding:3px 8px;border-bottom:1px solid var(--line)}
    #pc-dock .pc-tab{display:flex;flex-direction:column;align-items:center;width:66px;padding:3px 0 2px;border-radius:6px;color:var(--muted);cursor:pointer;font-size:11.5px;flex:none;border:1px solid transparent}
    #pc-dock .pc-tab .pc-e{font-size:18px;line-height:22px}
    #pc-dock .pc-tab:hover{color:var(--text)} #pc-dock .pc-tab.on{color:var(--gold2);border-color:var(--gold);background:var(--hover)}
    #pc-body{flex:1;overflow:auto;padding:8px 12px 12px}
    .pck .pc-row{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:3px 0}
    .pck .pc-row .inp{padding:3px 6px} .pck .pc-row select.inp{width:auto}
    .pck .pc-cols{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px}
    .pck .pc-k{font-size:11px;color:var(--faint);letter-spacing:.06em;text-transform:uppercase;margin:6px 0 3px}
    .pck .pc-says{font-family:var(--serif,inherit);font-style:italic;color:var(--text);margin:0 0 6px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
    .pck .pc-ln{display:flex;gap:8px;align-items:center;padding:3px 0;border-bottom:1px solid var(--line);font-size:12.5px}
    .pck .pc-ln .t{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .pck .pc-chip{font-size:11px;padding:0 7px;border:1px solid var(--line2);border-radius:9px;color:var(--muted);white-space:nowrap;cursor:pointer}
    .pck .pc-chip.on{border-color:var(--gold);color:var(--gold2)}
    .pck .pc-box{border:1px solid var(--line2);border-radius:8px;padding:8px 10px;background:var(--panel2,var(--panel))}
    .pck .pc-grid{display:grid;grid-template-columns:repeat(auto-fill,46px);gap:5px}
    .pck .pci{width:46px;height:46px;border:1px solid var(--line2);border-radius:6px;display:flex;align-items:center;justify-content:center;position:relative;background:#0003;cursor:pointer}
    .pck .pci img{width:32px;height:32px;image-rendering:auto}
    .pck .pci .pc-n{position:absolute;right:3px;bottom:0;font-size:11px;color:var(--text);text-shadow:0 0 3px #000}
    .pck .pci .pc-r{position:absolute;left:3px;top:1px;font-size:10px;color:var(--gold2)}
    .pck .pci.pc-empty{opacity:.45;cursor:default;font-size:10px;color:var(--muted)} .pck .pci.sel{outline:2px solid var(--gold)}
    .pck .pci.pc-add{border-style:dashed;color:var(--muted);font-size:20px}
    .pck .pc-tog{display:inline-flex;flex-direction:column;align-items:center;width:82px;padding:5px 0 3px;border:1px solid var(--line2);border-radius:7px;color:var(--muted);cursor:pointer;font-size:11.5px}
    .pck .pc-tog .e{font-size:18px} .pck .pc-tog.on{border-color:var(--gold);color:var(--gold2);background:var(--hover)}
    .pck .pc-figure{display:grid;grid-template-columns:repeat(3,46px);gap:5px;align-content:start}
    @container (max-width: 720px){ .pck .pc-cols{grid-template-columns:minmax(0,1fr)} }
    #pc-body{container-type:inline-size}`;
  document.head.appendChild(st);
})();

const PC_TABS = [['talk', '💬', 'Talk'], ['gear', '🎒', 'Gear'], ['trade', '🪙', 'Trade'], ['travel', '🧭', 'Travel'], ['quests', '🧩', 'Quests']];
// (only signs the Workshop's own icon set draws: icons.js EMO_ICON)
const PC_SVC_ICON = {'Weapons': '🗡', 'Armor': '🛡', 'Clothing': '👤', 'Books': '📚', 'Ingredients': '🌿', 'Lockpicks': '🔓', 'Probes': '🗝', 'Lights': '🕯',
  'Apparatus': '⚙', 'Repair items': '⚒', 'Miscellaneous': '📦', 'Potions': '🧪', 'Magic items': '✨', 'Sells spells': '🪄', 'Training': '🎓',
  'Spellmaking': '📜', 'Enchanting': '⭐', 'Repairs': '🔧'};
const PC_SLOTS = [['head', 'Head'], ['amulet', 'Neck'], ['shirt', 'Shirt'], ['weapon', 'Weapon'], ['chest', 'Chest'], ['shield', 'Shield'], ['hands', 'Hands'], ['legs', 'Legs'], ['ring', 'Ring'], ['feet', 'Feet'], ['robe', 'Robe'], ['belt', 'Belt']];
const PC_JOBS = [['fetch', '📦', 'Fetch'], ['deliver', '📜', 'Deliver'], ['find', '🔍', 'Find'], ['hunt', '🗡', 'Hunt'], ['meet', '👥', 'Meet']];
const PC_ITEM_TYPES = 'MISC,WEAP,ARMO,CLOT,BOOK,ALCH,INGR,APPA,LOCK,PROB,REPA,LIGH';

function pcIcon(it, extra){
  const fb = {WEAP: '🗡', ARMO: '🛡', CLOT: '👤', BOOK: '📚', ALCH: '🧪', INGR: '🌿', APPA: '⚙', LIGH: '🕯', LOCK: '🔓', PROB: '🗝', REPA: '⚒'}[it.type] || '📦';
  return `<span class="pci ${extra || ''}" title="${esc(it.name || it.id)}${it.count > 1 ? ' ×' + it.count : ''}${it.restock ? ' · restocks' : ''}">
    <img src="/api/person/icon?id=${encodeURIComponent(it.id)}" alt="" onerror="this.replaceWith(document.createTextNode('${fb}'))">
    ${it.count > 1 ? `<span class="pc-n">${it.count}</span>` : ''}${it.restock ? '<span class="pc-r">↻</span>' : ''}</span>`;
}

// ----- opening
async function pcOpen(id, tab, more){
  if (typeof needProject === 'function' && !await needProject()) return;
  if (typeof SCN !== 'undefined' && SCN.ed && SCN.ed.dock){ if (typeof scnLeave === 'function' && !scnLeave()) return; }
  if (typeof QM !== 'undefined' && QM.dock && typeof qmClose === 'function') qmClose();
  if (typeof pageOn === 'function' && !pageOn('world')) showView('world');
  if (PCD.id !== id || PCD.kind !== 'npc'){ PCD.form = {kind: 'topic', when: {}}; PCD.job = null; PCD.sel = null; }
  PCD.kind = 'npc'; PCD.id = id; PCD.tab = tab || PCD.tab || 'talk';
  Object.assign(PCD, more || {});
  if (!PCD.opts){ try { PCD.opts = await api('/api/npc/options'); } catch (e){ PCD.opts = {services: []}; } }
  pcDock();
  await pcLoad();
}
async function pcOpenCont(id){
  if (typeof needProject === 'function' && !await needProject()) return;
  if (typeof QM !== 'undefined' && QM.dock && typeof qmClose === 'function') qmClose();
  PCD.kind = 'cont'; PCD.id = id; PCD.sel = null;
  pcDock();
  await pcLoad();
}
async function pcLoad(){
  const body = $('#pc-body'); if (body) body.innerHTML = '<div class="msg" style="padding:12px"><span class="spin"></span>Reading…</div>';
  try { PCD.d = await api(PCD.kind === 'cont' ? '/api/person/contents?id=' + encodeURIComponent(PCD.id) : '/api/person?id=' + encodeURIComponent(PCD.id)); }
  catch (e){ if (body) body.innerHTML = `<div class="msg err" style="padding:12px">${esc(e.message)}</div>`; return; }
  pcRender();
}
function pcDock(){
  const wrap = document.querySelector('#world .mapwrap'); if (!wrap) return;
  let d = $('#pc-dock');
  if (!d){
    d = document.createElement('div'); d.id = 'pc-dock';
    d.innerHTML = `<div class="pc-bar"><span class="pc-grip" title="Drag to make it taller or shorter">⋯</span><b id="pc-title"></b><span class="pc-sub" id="pc-sub"></span>
      <span style="flex:1"></span><span id="pc-more"></span><button class="btn sm" id="pc-close" title="Close">✕</button></div>
      <div class="pc-tabs" id="pc-tabs"></div><div id="pc-body"></div>`;
    wrap.appendChild(d);
    const grip = d.querySelector('.pc-grip');
    grip.onpointerdown = ev => {
      ev.preventDefault(); const r0 = wrap.getBoundingClientRect();
      const mv = e2 => { const h = Math.max(160, Math.min(r0.height - 80, r0.bottom - e2.clientY)); d.style.height = h + 'px'; try { localStorage.setItem('ws-pch', String(h)); } catch (e){} };
      const up = () => { window.removeEventListener('pointermove', mv); window.removeEventListener('pointerup', up); if (typeof v3Resize === 'function') v3Resize(); };
      window.addEventListener('pointermove', mv); window.addEventListener('pointerup', up);
    };
    try { const h = +localStorage.getItem('ws-pch'); if (h) d.style.height = h + 'px'; } catch (e){}
    d.querySelector('#pc-close').onclick = () => pcClose();
  }
  d.style.display = '';
}
function pcClose(){ const d = $('#pc-dock'); if (d) d.style.display = 'none'; PCD.kind = null; PCD.job = null; }

function pcRender(){
  const d = PCD.d; if (!d) return;
  const cont = PCD.kind === 'cont';
  $('#pc-title').textContent = (cont ? '📦 ' : '🧍 ') + (d.name || d.id);
  $('#pc-sub').textContent = cont ? d.id : [d.race, d.cls, (d.places && d.places[0] && d.places[0].name) || ''].filter(Boolean).join(' · ');
  const copies = d.copies > 1 ? `<span class="pc-chip" style="cursor:default" title="Their ${cont ? 'contents' : 'lines, wares and services'} belong to every copy: changing them here changes all ${d.copies}">⚠ in ${d.copies} places</span>` : '';
  $('#pc-more').innerHTML = copies + (cont ? '' : `<button class="btn sm" id="pc-dlg" title="All their dialogue, on the Dialogue page">💬 Dialogue page</button>
    <button class="btn sm" id="pc-char" title="Every detail of them, on the character page">👤 Character page</button>`);
  const tabs = $('#pc-tabs');
  tabs.style.display = cont ? 'none' : '';
  tabs.innerHTML = PC_TABS.map(([k, e, t]) => `<div class="pc-tab ${PCD.tab === k ? 'on' : ''}" data-pctab="${k}"><span class="pc-e">${e}</span>${t}</div>`).join('');
  tabs.querySelectorAll('[data-pctab]').forEach(t => t.onclick = () => { PCD.tab = t.dataset.pctab; pcRender(); });
  if (!cont){
    $('#pc-dlg').onclick = () => { if (typeof openCharacterDialogue === 'function') openCharacterDialogue(d.id); };
    $('#pc-char').onclick = () => { if (typeof cOpen === 'function') cOpen(d.id); else if (typeof selAction === 'function') selAction('char'); };
  }
  const body = $('#pc-body');
  body.innerHTML = `<div class="pck">${cont ? pcGearPane(true) : {talk: pcTalkPane, gear: () => pcGearPane(false), trade: pcTradePane, travel: pcTravelPane, quests: pcQuestPane}[PCD.tab]()}</div>`;
  ({talk: pcTalkBind, gear: pcGearBind, trade: pcTradeBind, travel: pcTravelBind, quests: pcQuestBind})[cont ? 'gear' : PCD.tab](body);
}

// ----- 💬 Talk: what they say now, their lines, + a line
function pcTalkPane(){
  const d = PCD.d, f = PCD.form, w = f.when || {};
  const groups = [['greeting', '👋', 'Greetings'], ['topic', '💬', 'Topics'], ['rumour', '👥', 'Rumours']];
  const list = groups.map(([k, e, t]) => { const ls = d.lines.filter(l => l.kind === k); return ls.length ? `<div class="pc-k">${t}</div>` + ls.map(l =>
    `<div class="pc-ln" title="${esc(l.text)}"><span>${e}</span><span class="pc-t">${k === 'topic' ? `<b>${esc(l.topic)}:</b> ` : ''}${esc(l.text)}</span>${l.when ? `<span class="pc-chip" style="cursor:default">${esc(l.when)}</span>` : ''}
      ${l.mine ? `<button class="btn sm" data-pcunsay="${esc(l.tkey)}|${esc(l.inam)}" title="Take this line out">✕</button>` : ''}</div>`).join('') : ''; }).join('')
    || '<div class="msg">No lines of their own yet: the game\'s general ones apply.</div>';
  const ans = f.answers;
  return `${d.says ? `<p class="pc-says" title="What they greet the player with now">“${esc(d.says)}”</p>` : ''}
  <div class="pc-cols"><div>${list}</div>
  <div class="pc-box"><div class="pc-row"><b>Say something</b><span style="flex:1"></span>
      ${[['greeting', '👋 Greeting'], ['topic', '💬 Topic'], ['rumour', '👥 Rumour']].map(([k, t]) => `<button class="btn sm ${f.kind === k ? 'primary' : ''}" data-pckind="${k}">${t}</button>`).join('')}</div>
    ${f.kind === 'topic' ? `<div class="pc-row"><input class="inp" id="pcf-topic" value="${esc(f.topic || '')}" placeholder="the topic the player asks about" list="pcf-dl-topics" style="flex:1">
      <datalist id="pcf-dl-topics">${[...new Set(d.lines.filter(l => l.kind === 'topic').map(l => l.topic))].map(t => `<option value="${esc(t)}">`).join('')}</datalist></div>` : ''}
    <div class="pc-row"><textarea class="inp" id="pcf-text" rows="2" placeholder="What they say" style="flex:1">${esc(f.text || '')}</textarea></div>
    <div class="pc-row"><span class="msg">When:</span>
      <span class="pc-chip ${!w.once && !w.quest && !w.carries && w.from_hour == null ? 'on' : ''}" data-pcwhen="always">always</span>
      <span class="pc-chip ${w.once ? 'on' : ''}" data-pcwhen="once" title="Said once, then never again">once</span>
      <span class="pc-chip ${w.quest ? 'on' : ''}" data-pcwhen="quest" title="Only at a quest's stage">${w.quest ? '📜 ' + esc(w.questTitle || w.quest) : 'a quest stage…'}</span>
      <span class="pc-chip ${w.carries ? 'on' : ''}" data-pcwhen="carries" title="Only if the player carries something">${w.carries ? '🎒 ' + esc(w.carries) : 'player carries…'}</span>
      <span class="pc-chip ${w.from_hour != null ? 'on' : ''}" data-pcwhen="hours" title="Only between two hours">${w.from_hour != null ? `🕘 ${w.from_hour}–${w.to_hour}` : 'by hour…'}</span></div>
    ${w.quest ? `<div class="pc-row"><span class="msg">${esc(w.questTitle || w.quest)}</span><select class="inp" id="pcf-op"><option value=">=" ${w.op !== '<' && w.op !== '=' ? 'selected' : ''}>at or after</option><option value="=" ${w.op === '=' ? 'selected' : ''}>exactly at</option><option value="<" ${w.op === '<' ? 'selected' : ''}>before</option></select>
      <select class="inp" id="pcf-stage">${(w.stages || []).map(s => `<option value="${s.index}" ${+w.stage === s.index ? 'selected' : ''}>stage ${s.index}${s.text ? ': ' + esc(s.text.slice(0, 30)) : ''}</option>`).join('')}</select></div>` : ''}
    ${w.carriesEdit ? `<div class="pc-row dd"><input class="inp" id="pcf-carries" placeholder="Search an item" autocomplete="off" style="flex:1"><div class="ddlist" id="pcf-carries-l"></div></div>` : ''}
    ${w.from_hour != null ? `<div class="pc-row"><span class="msg">from</span><input class="inp" id="pcf-from" value="${w.from_hour}" style="width:44px"><span class="msg">to</span><input class="inp" id="pcf-to" value="${w.to_hour}" style="width:44px"><span class="msg">o'clock</span></div>` : ''}
    <div class="pc-row"><label title="The player picks one of two answers, and they reply to each"><input type="checkbox" id="pcf-two" ${ans ? 'checked' : ''}> Two answers</label></div>
    ${ans ? ans.map((a, n) => `<div class="pc-row"><span class="msg">${n + 1}.</span><input class="inp" data-pcans="${n}:label" value="${esc(a.label || '')}" placeholder="${n ? 'No thanks' : 'Tell me more'}" style="width:110px">
      <input class="inp" data-pcans="${n}:text" value="${esc(a.text || '')}" placeholder="They reply" style="flex:1;min-width:120px">
      <select class="inp" data-pcans="${n}:then"><option value="">then nothing</option><option value="bye" ${a.then === 'bye' ? 'selected' : ''}>then goodbye</option>
        <option value="give" ${a.then === 'give' ? 'selected' : ''}>then give…</option></select>
      ${a.then === 'give' ? `<input class="inp" data-pcans="${n}:give" value="${esc(a.give || '')}" placeholder="item ID (gold_001)" style="width:120px">` : ''}</div>`).join('') : ''}
    <div class="pc-row"><span style="flex:1" class="msg" id="pcf-msg"></span><button class="btn primary sm" id="pcf-ok">Add the line</button></div></div></div>`;
}
function pcTalkRead(){
  const b = $('#pc-body'), v = id => { const el = b.querySelector('#' + id); return el ? el.value : undefined; };
  const f = PCD.form, w = f.when = f.when || {};
  if (v('pcf-topic') !== undefined) f.topic = v('pcf-topic');
  if (v('pcf-text') !== undefined) f.text = v('pcf-text');
  if (v('pcf-op') !== undefined) w.op = v('pcf-op');
  if (v('pcf-stage') !== undefined) w.stage = v('pcf-stage');
  if (v('pcf-from') !== undefined){ w.from_hour = +v('pcf-from'); w.to_hour = +v('pcf-to'); }
  b.querySelectorAll('[data-pcans]').forEach(el => { const [n, k] = el.dataset.pcans.split(':'); f.answers[+n][k] = el.value; });
  return f;
}
function pcTalkBind(b){
  b.querySelectorAll('[data-pcunsay]').forEach(x => x.onclick = async () => {
    const [topic, inam] = x.dataset.pcunsay.split('|');
    try { await post('/api/person/unsay', {topic, inam}); afterChange(); toast('Line taken out: Undo puts it back.'); await pcLoad(); } catch (e){ toast(e.message, true); }
  });
  b.querySelectorAll('[data-pckind]').forEach(x => x.onclick = () => { pcTalkRead(); PCD.form.kind = x.dataset.pckind; pcRender(); });
  b.querySelectorAll('[data-pcwhen]').forEach(x => x.onclick = () => {
    pcTalkRead(); const w = PCD.form.when, k = x.dataset.pcwhen;
    if (k === 'always'){ PCD.form.when = {}; return pcRender(); }
    if (k === 'once'){ w.once = !w.once; return pcRender(); }
    if (k === 'hours'){ if (w.from_hour != null){ delete w.from_hour; delete w.to_hour; } else { w.from_hour = 20; w.to_hour = 24; } return pcRender(); }
    if (k === 'carries'){ if (w.carries || w.carriesEdit){ delete w.carries; delete w.carriesEdit; } else w.carriesEdit = true; return pcRender(); }
    if (k === 'quest'){
      if (w.quest){ delete w.quest; return pcRender(); }
      if (typeof qmPicker === 'function') qmPicker(x, async key => {
        try { const q = await api('/api/dlg/quest?' + new URLSearchParams({key})); Object.assign(w, {quest: q.id, questTitle: q.title || q.id, stages: q.stages, stage: (q.stages[0] || {}).index, op: '>='}); } catch (e){ toast(e.message, true); }
        pcRender();
      }, 'Only at a stage of which quest?');
    }
  });
  if (b.querySelector('#pcf-carries') && typeof ddSearch === 'function') ddSearch('pcf-carries', PC_ITEM_TYPES, r => { pcTalkRead(); PCD.form.when.carries = r.id; delete PCD.form.when.carriesEdit; pcRender(); });
  const two = b.querySelector('#pcf-two');
  if (two) two.onchange = () => { pcTalkRead(); PCD.form.answers = two.checked ? [{label: '', text: ''}, {label: '', text: '', then: 'bye'}] : null; pcRender(); };
  b.querySelectorAll('select[data-pcans]').forEach(s => s.onchange = () => { pcTalkRead(); pcRender(); });
  const ok = b.querySelector('#pcf-ok');
  if (ok) ok.onclick = async () => {
    const f = pcTalkRead(), msg = b.querySelector('#pcf-msg'), w = f.when || {};
    const body = {who: PCD.d.id, kind: f.kind, topic: f.topic, text: f.text,
      when: {once: !!w.once, quest: w.quest, op: w.op, stage: w.stage, carries: w.carries, from_hour: w.from_hour, to_hour: w.to_hour},
      answers: (f.answers || []).map(a => ({label: a.label, text: a.text, bye: a.then === 'bye', give: a.then === 'give' ? a.give : ''}))};
    ok.disabled = true;
    try { await post('/api/person/say', body); afterChange(); toast('Line added: Undo takes it back.'); PCD.form = {kind: f.kind, topic: f.topic, when: {}}; await pcLoad(); }
    catch (e){ msg.className = 'msg err'; msg.textContent = e.message; ok.disabled = false; }
  };
}

// ----- 🎒 Gear: what they wear (a figure), what they carry (icons); a container's contents the same way
function pcGearPane(cont){
  const d = PCD.d, items = d.items || [];
  const worn = {};
  if (!cont) for (const it of items){ const s = it.slot === 'shoulder' ? 'chest' : it.slot === 'skirt' ? 'legs' : it.slot; if (s && !worn[s]) worn[s] = it; }
  const sel = PCD.sel != null ? items[PCD.sel] : null;
  const trader = !cont && d.services;
  const grid = `<div class="pc-row" style="margin-bottom:5px"><b>${cont ? 'Holds' : 'Carries'}</b><span class="msg">${items.length ? items.reduce((a, x) => a + x.count, 0) + ' things' : ''}</span><span style="flex:1"></span>
      <div class="dd"><input class="inp" id="pc-add" placeholder="+ Add an item" autocomplete="off" style="width:190px"><div class="ddlist" id="pc-add-l"></div></div></div>
    <div class="pc-grid">${items.map((it, n) => pcIcon(it, PCD.sel === n ? 'sel' : '').replace('<span class="pci', `<span data-pcit="${n}" class="pci`)).join('')}</div>
    ${sel ? `<div class="pc-row pc-box" style="margin-top:8px"><b>${esc(sel.name || sel.id)}</b><span class="msg">${esc(sel.id)}</span><span style="flex:1"></span>
      <button class="btn sm" data-pcn="-1">−</button><input class="inp" id="pc-count" value="${sel.count}" style="width:52px;text-align:center"><button class="btn sm" data-pcn="1">+</button>
      ${cont || trader ? `<label title="Comes back after it is ${cont ? 'taken' : 'sold'}"><input type="checkbox" id="pc-restock" ${sel.restock ? 'checked' : ''}> ↻ restocks</label>` : ''}
      <button class="btn sm" id="pc-itrm" title="Take it out">✕ Remove</button></div>` : ''}`;
  if (cont) return grid;
  return `<div class="pc-cols" style="grid-template-columns:auto minmax(0,1fr)"><div><div class="pc-k" style="margin-top:0">Wears</div>
      <div class="pc-figure">${PC_SLOTS.map(([s, e]) => worn[s] ? pcIcon(worn[s]).replace('<span class="pci', `<span data-pcit="${items.indexOf(worn[s])}" class="pci`) : `<span class="pci pc-empty" title="${s}">${e}</span>`).join('')}</div>
      <div class="msg" style="max-width:150px;margin-top:4px" title="They wear the best clothes and armour they carry, and use the best weapon">the best of what they carry</div></div>
    <div>${grid}</div></div>`;
}
async function pcSaveItems(items){
  try {
    if (PCD.kind === 'cont') PCD.d = await post('/api/person/contents/save', {id: PCD.d.id, items});
    else PCD.d = await post('/api/person/save', {id: PCD.d.id, change: {items}});
    afterChange(); pcRender();
  } catch (e){ toast(e.message, true); }
}
function pcGearBind(b){
  const items = PCD.d.items || [];
  const plain = () => items.map(x => ({id: x.id, count: x.count, restock: !!x.restock}));
  b.querySelectorAll('[data-pcit]').forEach(x => x.onclick = () => { PCD.sel = PCD.sel === +x.dataset.pcit ? null : +x.dataset.pcit; pcRender(); });
  if (typeof ddSearch === 'function') ddSearch('pc-add', PC_ITEM_TYPES, r => {
    const l = plain(), ex = l.find(x => x.id.toLowerCase() === r.id.toLowerCase());
    if (ex) ex.count++; else l.push({id: r.id, count: /^gold_/i.test(r.id) ? 50 : 1});
    PCD.sel = null; pcSaveItems(l);
  });
  const sel = PCD.sel;
  if (sel == null || !items[sel]) return;
  const setCount = n => { const l = plain(); l[sel].count = Math.max(1, n); pcSaveItems(l); };
  b.querySelectorAll('[data-pcn]').forEach(x => x.onclick = () => setCount(items[sel].count + +x.dataset.pcn));
  const c = b.querySelector('#pc-count'); if (c) c.onchange = () => setCount(+c.value || 1);
  const rs = b.querySelector('#pc-restock'); if (rs) rs.onchange = () => { const l = plain(); l[sel].restock = rs.checked; pcSaveItems(l); };
  b.querySelector('#pc-itrm').onclick = () => { const l = plain(); l.splice(sel, 1); PCD.sel = null; pcSaveItems(l); };
}

// ----- 🪙 Trade: what they buy and sell, their services, their gold
function pcTradePane(){
  const d = PCD.d, svc = (PCD.opts && PCD.opts.services) || [];
  const goods = svc.filter(([n]) => !['Sells spells', 'Training', 'Spellmaking', 'Enchanting', 'Repairs'].includes(n));
  const others = svc.filter(x => !goods.includes(x));
  const tog = ([n, bit]) => `<span class="pc-tog ${d.services & bit ? 'on' : ''} ${d.auto ? '' : ''}" data-pcsvc="${bit}" title="${esc(n)}"><span class="pc-e">${PC_SVC_ICON[n] || '•'}</span>${esc(n.replace('Miscellaneous', 'Misc').replace('Repair items', 'Repair tools'))}</span>`;
  return `${d.auto ? `<div class="pc-row pc-box" style="margin-bottom:8px"><span>🎓 Their class (${esc(d.cls)}) decides what they trade and teach.</span><span style="flex:1"></span>
      <button class="btn sm" id="pc-own" title="Their stats are then kept as they are now, and the services ticked here are theirs">Choose them myself</button></div>` : ''}
    <div class="pc-k">Buys and sells</div><div class="pc-row" style="${d.auto ? 'opacity:.5;pointer-events:none' : ''}">${goods.map(tog).join('')}</div>
    <div class="pc-k">Services</div><div class="pc-row" style="${d.auto ? 'opacity:.5;pointer-events:none' : ''}">${others.map(tog).join('')}</div>
    <div class="pc-row" style="margin-top:8px"><span class="msg">🪙 Barter gold</span><input class="inp" id="pc-gold" value="${d.gold || 0}" style="width:80px">
      <span style="flex:1"></span><button class="btn sm" data-pctab2="gear" title="What they sell: what they carry">🎒 Their wares</button></div>`;
}
function pcTradeBind(b){
  const save = async change => { try { PCD.d = await post('/api/person/save', {id: PCD.d.id, change}); afterChange(); pcRender(); } catch (e){ toast(e.message, true); } };
  const own = b.querySelector('#pc-own'); if (own) own.onclick = () => save({auto: false});
  b.querySelectorAll('[data-pcsvc]').forEach(x => x.onclick = () => save({services: PCD.d.services ^ +x.dataset.pcsvc}));
  const g = b.querySelector('#pc-gold'); if (g) g.onchange = () => save({gold: Math.max(0, +g.value || 0)});
  b.querySelectorAll('[data-pctab2]').forEach(x => x.onclick = () => { PCD.tab = x.dataset.pctab2; pcRender(); });
}

// ----- 🧭 Travel: where they take travellers (right-click a spot on the map to add one)
function pcTravelPane(){
  const d = PCD.d;
  return `<div class="pc-k" style="margin-top:0">Takes travellers to</div>
    ${d.travel.map((t, n) => `<div class="pc-ln"><span>📍</span><span class="pc-t">${esc(t.cell || 'Outdoors')} <small class="msg">${t.p.slice(0, 2).map(v => Math.round(v)).join(', ')}</small></span>
      <button class="btn sm" data-pctgo="${n}" title="Go there">Go</button><button class="btn sm" data-pctrm="${n}" title="Take it out">✕</button></div>`).join('')
      || '<div class="msg">Nowhere yet.</div>'}
    <div class="pc-row" style="margin-top:8px"><span class="msg">Add one: right-click a spot on the map › 🧭 Travel from ${esc(d.name)} to here.</span></div>`;
}
function pcTravelBind(b){
  b.querySelectorAll('[data-pctrm]').forEach(x => x.onclick = async () => {
    const l = PCD.d.travel.slice(); l.splice(+x.dataset.pctrm, 1);
    try { PCD.d = await post('/api/person/save', {id: PCD.d.id, change: {travel: l}}); afterChange(); pcRender(); } catch (e){ toast(e.message, true); }
  });
  b.querySelectorAll('[data-pctgo]').forEach(x => x.onclick = async () => {
    const t = PCD.d.travel[+x.dataset.pctgo];
    const key = t.cell ? t.cell.toLowerCase() : (typeof cellKeyAt === 'function' ? cellKeyAt(t.p[0], t.p[1]) : null);
    if (key && key !== W.key && typeof worldOpen === 'function') await worldOpen(key);
    if (typeof V3 !== 'undefined' && V3.on && typeof v3Focus === 'function'){ v3Focus({k: null, p: t.p}); if (typeof v3Loop === 'function') v3Loop(); }
  });
}
async function pcTravelHere(spot){
  const d = PCD.d; if (!d) return;
  const interior = W.info && W.info.interior ? (W.info.name || W.info.id) : '';
  const l = d.travel.concat([{p: [spot[0], spot[1], spot[2] || 0, 0, 0, 0], cell: interior}]);
  try { PCD.d = await post('/api/person/save', {id: d.id, change: {travel: l}}); afterChange(); PCD.tab = 'travel'; pcDock(); pcRender(); toast('Destination added: Undo takes it back.'); }
  catch (e){ toast(e.message, true); }
}

// ----- 🧩 Quests: theirs, and a whole job from them in a few answers
function pcQuestPane(){
  const d = PCD.d, j = PCD.job;
  const list = d.quests.map(q => `<div class="pc-ln"><span>🧩</span><span class="pc-t">${esc(q.title)}</span><button class="btn sm" data-pcq="${esc(q.key)}" title="Open it in the quest maker">Open</button></div>`).join('')
    || '<div class="msg">None yet.</div>';
  const who = (id, lbl) => `<div class="pc-row"><span class="msg" style="min-width:60px">${lbl}</span><input class="inp" id="pcj-${id}" value="${esc((j || {})[id] || '')}" list="pcj-dl-people" placeholder="right-click them, or type" style="width:200px"></div>`;
  const item = (lbl) => `<div class="pc-row"><span class="msg" style="min-width:60px">${lbl}</span><div class="dd"><input class="inp" id="pcj-item" value="${esc((j || {}).item || '')}" placeholder="Search an item" autocomplete="off" style="width:200px"><div class="ddlist" id="pcj-item-l"></div></div>
      ${j && j.kind === 'fetch' ? `<span class="msg">×</span><input class="inp" id="pcj-count" value="${j.count || 1}" style="width:44px">` : ''}</div>`;
  const form = !j ? '' : `<div class="pc-box" style="margin-top:8px">
    <div class="pc-row"><b>${PC_JOBS.find(x => x[0] === j.kind)[1]} ${PC_JOBS.find(x => x[0] === j.kind)[2]}</b><input class="inp" id="pcj-title" value="${esc(j.title || '')}" placeholder="Its title in the journal" style="flex:1"></div>
    ${['fetch', 'deliver', 'find'].includes(j.kind) ? item(j.kind === 'deliver' ? 'Takes' : 'Wants') : ''}
    ${j.kind === 'deliver' ? who('to', 'To') : j.kind === 'meet' ? who('to', 'Meet') : j.kind === 'hunt' ? who('target', 'Hunt') : ''}
    ${j.kind === 'find' ? `<div class="pc-row"><span class="msg" style="min-width:60px">Lies</span><span class="msg">${j.spot ? `📍 ${Math.round(j.spot.pos[0])}, ${Math.round(j.spot.pos[1])}` : '📍 right-click the ground where it lies › 🧩 It lies here'}</span></div>` : ''}
    <div class="pc-row"><span class="msg" style="min-width:60px">Reward</span><input class="inp" id="pcj-reward" value="${esc(j.reward || 'gold_001')}" style="width:120px"><span class="msg">×</span><input class="inp" id="pcj-rn" value="${j.reward_count || 25}" style="width:52px"></div>
    <div class="pc-row"><span class="msg" style="min-width:60px">They say</span><input class="inp" id="pcj-ask" value="${esc(j.ask || '')}" placeholder="(written for you if left empty)" style="flex:1"></div>
    <div class="pc-row"><span style="flex:1" class="msg" id="pcj-msg"></span><button class="btn sm" id="pcj-no">Cancel</button><button class="btn primary sm" id="pcj-ok">Write the quest</button></div>
    <datalist id="pcj-dl-people">${(PCD.near || []).map(p => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('')}</datalist></div>`;
  return `<div class="pc-cols"><div><div class="pc-k" style="margin-top:0">Their quests</div>${list}</div>
    <div><div class="pc-k" style="margin-top:0">A job from them</div><div class="pc-row">${PC_JOBS.map(([k, e, t]) => `<span class="pc-tog ${j && j.kind === k ? 'on' : ''}" data-pcjob="${k}"><span class="pc-e">${e}</span>${t}</span>`).join('')}</div>${form}</div></div>`;
}
function pcJobRead(){
  const b = $('#pc-body'), v = id => { const el = b.querySelector('#pcj-' + id); return el ? el.value.trim() : undefined; };
  const j = PCD.job; if (!j) return j;
  for (const k of ['title', 'item', 'to', 'target', 'reward', 'ask']) if (v(k) !== undefined) j[k] = v(k);
  if (v('count') !== undefined) j.count = +v('count') || 1;
  if (v('rn') !== undefined) j.reward_count = +v('rn') || 1;
  return j;
}
function pcQuestBind(b){
  b.querySelectorAll('[data-pcq]').forEach(x => x.onclick = () => { if (typeof qmOpen === 'function') qmOpen(x.dataset.pcq); });
  b.querySelectorAll('[data-pcjob]').forEach(x => x.onclick = () => { pcJobRead(); PCD.job = Object.assign(PCD.job || {}, {kind: x.dataset.pcjob}); pcRender(); if (!PCD.near) pcNear(); });
  if (!PCD.job) return;
  if (typeof ddSearch === 'function' && b.querySelector('#pcj-item')) ddSearch('pcj-item', PC_ITEM_TYPES, r => { pcJobRead(); PCD.job.item = r.id; pcRender(); });
  b.querySelector('#pcj-no').onclick = () => { PCD.job = null; pcRender(); };
  b.querySelector('#pcj-ok').onclick = async () => {
    const j = pcJobRead(), msg = b.querySelector('#pcj-msg'), ok = b.querySelector('#pcj-ok');
    ok.disabled = true;
    try {
      const r = await post('/api/person/job', Object.assign({giver: PCD.d.id}, j));
      afterChange(); toast('Quest written: Undo takes it back.'); PCD.job = null;
      if (typeof qmOpen === 'function') qmOpen(r.key);
    } catch (e){ msg.className = 'msg err'; msg.textContent = e.message; ok.disabled = false; }
  };
}
async function pcNear(){
  if (!W.key) return;
  try { PCD.near = (await api('/api/scenes/actors?cell=' + encodeURIComponent(W.key.startsWith('#') ? JSON.stringify(W.key.slice(1).split(',').map(Number)) : W.key))).actors || []; } catch (e){ PCD.near = []; }
  if (PCD.tab === 'quests') pcRender();
}

// ----- the right-click menu
function pcMenu(e, hit, at){
  if (typeof W === 'undefined' || !W.key || !(S.summary && S.summary.project)) return [];
  const r = hit && hit[1], out = [];
  const spot = at || (r && r.p) || null;
  if (r && r.type === 'NPC_'){
    const nm = r.name || r.id, open = (tab, more) => () => pcOpen(r.id, tab, more);
    out.push({label: `💬 Say something…`, act: open('talk')}, {label: `👤 About ${nm}`, act: open(PCD.tab || 'talk')},
      {label: '🎒 Gear and wares', act: open('gear')}, {label: '🪙 Trade and services', act: open('trade')}, {label: '🧭 Travel', act: open('travel')},
      {label: `🧩 A job from ${nm}…`, act: open('quests')});
    // (a job being written: this person is who it goes to, or who to hunt)
    if (PCD.kind === 'npc' && PCD.job && r.id.toLowerCase() !== String(PCD.id).toLowerCase()){
      const k = PCD.job.kind;
      if (k === 'deliver' || k === 'meet') out.push({label: `🧩 Job: ${k === 'deliver' ? 'deliver to' : 'meet'} ${nm}`, act: () => { pcJobRead(); PCD.job.to = r.id; pcDock(); pcRender(); }});
      if (k === 'hunt') out.push({label: `🧩 Job: hunt ${nm}`, act: () => { pcJobRead(); PCD.job.target = r.id; pcDock(); pcRender(); }});
    }
  } else if (r && r.type === 'CREA' && PCD.kind === 'npc' && PCD.job && PCD.job.kind === 'hunt'){
    out.push({label: `🧩 Job: hunt ${r.name || r.id}`, act: () => { pcJobRead(); PCD.job.target = r.id; pcDock(); pcRender(); }});
  } else if (r && r.type === 'CONT'){
    out.push({label: '📦 Contents', act: () => pcOpenCont(r.id)});
  }
  if (spot && !r && PCD.kind === 'npc' && PCD.d){
    out.push({label: `🧭 Travel from ${PCD.d.name} to here`, act: () => pcTravelHere(spot)});
    if (PCD.job && PCD.job.kind === 'find'){
      const ck = typeof cellKeyAt === 'function' && W.key.startsWith('#') ? cellKeyAt(spot[0], spot[1]) : W.key;
      out.push({label: '🧩 Job: it lies here', act: () => { pcJobRead(); PCD.job.spot = {cell: ck, pos: spot.slice(0, 3)}; pcDock(); pcRender(); }});
    }
  }
  return out;
}
(function pcMenuOn(){ if (typeof CF_MENU_MORE !== 'undefined') CF_MENU_MORE.push(pcMenu); else setTimeout(pcMenuOn, 200); })();
