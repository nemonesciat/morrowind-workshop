// ---------- Quest testing in the running game (through the live link) ----------
// While the game runs from "Play here": set quest stages, change global variables, give or
// take items, add topics, and jump to the people a quest involves. The game reports quest
// stages, globals and item counts back, so dialogue conditions show whether they hold right now.
const QT = {data: null, loaded: 0, npc: null, item: null, asked: new Set(), sig: ''};
const QT_ITEM_TYPES = 'MISC,WEAP,ARMO,CLOT,BOOK,ALCH,INGR,LIGH,APPA,LOCK,PROB,REPA';

async function qtCmd(verb, args, okText){
  try { await post('/api/test/cmd', {verb, args}); if (okText) toast(okText); return true; }
  catch (e){ toast(e.message, true); return false; }
}
async function qtGoto(npcId){
  try { const r = await post('/api/test/goto', {npc: npcId}); toast(`Taking you to ${npcId} (${r.place})…`); }
  catch (e){ toast(e.message, true); }
}

// ----- is a condition true in the game right now? true / false / null (can't tell)
function qtCompare(a, op, b){
  switch (op){
    case '=': return Math.abs(a - b) < 1e-4; case '!=': return Math.abs(a - b) >= 1e-4;
    case '>': return a > b; case '>=': return a >= b; case '<': return a < b; case '<=': return a <= b;
  }
  return null;
}
function qtCond(kind, name, op, value){
  const G = LINK.game; if (!LINK.connected || !G) return null;
  const k = (name || '').toLowerCase();
  if (kind === 'journal'){ const q = G.quests[k]; return qtCompare(q ? q.stage : 0, op, value); }
  if (kind === 'global'){ if (!(k in G.globals) || G.globals[k] == null) return null; return qtCompare(G.globals[k], op, value); }
  if (kind === 'item'){ if (!(k in G.items) || G.items[k] == null) return null; return qtCompare(G.items[k], op, value); }
  return null;
}
// condition chips get their attributes from lineHtml (data-ck); colour them
function qtMark(){
  document.querySelectorAll('#dmain [data-qgo]').forEach(b => b.style.display = LINK.connected ? '' : 'none');
  const chips = document.querySelectorAll('#dmain .dchip[data-ck]');
  const want = {globals: [], items: []};
  chips.forEach(ch => {
    const [kind, name, op, value] = JSON.parse(ch.dataset.ck);
    const v = qtCond(kind, name, op, +value);
    ch.classList.toggle('ok', v === true); ch.classList.toggle('no', v === false);
    ch.title = !LINK.connected ? '' : v === true ? 'True in your game right now' : v === false ? 'Not true in your game right now'
      : 'Waiting for the game to report this';
    // ask the game to report on what these lines check
    const key = kind + '|' + name.toLowerCase();
    if (LINK.connected && v === null && (kind === 'global' || kind === 'item') && !QT.asked.has(key)){
      QT.asked.add(key); (kind === 'global' ? want.globals : want.items).push(name);
    }
  });
  if (want.globals.length || want.items.length) post('/api/test/watch', want).catch(() => {});
}

// ----- the quest page: where the game is, and a button per stage
function qtQuestBar(){
  const bar = $('#q-test'); if (!bar || D.mode !== 'quest' || !D.data) return;
  const q = D.data;
  if (!LINK.connected){
    bar.innerHTML = `<div class="qtbar off">🎮 <b>Test it in game:</b> press <b>Play here</b> on the World map. While the game runs you can set this quest's stage from here and see which lines would be said.</div>`;
    bar.dataset.html = '';
    document.querySelectorAll('#q-stages [data-qset]').forEach(b => b.remove());
    document.querySelectorAll('#q-stages .qnow').forEach(r => r.classList.remove('qnow'));
    return;
  }
  const g =(LINK.game.quests || {})[q.id.toLowerCase()];
  const inGame = QT.questInGame !== false || !!g;      // (the game reporting it is proof enough)
  const where = !g ? 'not started' : `stage <b>${g.stage}</b>${g.finished ? ' · finished' : ''}`;
  const html = `<div class="qtbar">🎮 <b>In your game:</b> ${where}
    ${inGame ? `<span class="qtbtns"><button class="btn sm" id="qt-reset" title="Back to stage 0 and not finished. Journal entries already written stay in the journal.">Reset</button>
      ${g && !g.finished ? '<button class="btn sm" id="qt-fin">Mark finished</button>' : ''}</span>`
      : `<div class="msg" style="color:var(--amber)">This quest is new since the game started, so the game doesn't know it yet. Quit the game and press Play here again to test it.</div>`}</div>`;
  if (bar.dataset.html !== html){
    bar.innerHTML = html; bar.dataset.html = html;
    const r = $('#qt-reset'); if (r) r.onclick = () => qtCmd('reset', [q.id], 'Quest reset in game.');
    const f = $('#qt-fin'); if (f) f.onclick = () => qtCmd('finish', [q.id, 1], 'Marked finished in game.');
  }
  // per-stage buttons
  document.querySelectorAll('#q-stages [data-qs]').forEach(row => {
    const s = D.qstages[+row.dataset.qs]; if (!s) return;
    row.classList.toggle('qnow', !!g && g.stage === s.index);
    let b = row.querySelector('[data-qset]');
    if (!inGame){ if (b) b.remove(); return; }
    if (!b){
      b = document.createElement('button'); b.className = 'btn sm'; b.dataset.qset = '1';
      b.textContent = '▶ Set in game'; b.title = 'Jump the quest to this stage in your game and write its journal entry';
      b.onclick = () => qtCmd('journal', [q.id, D.qstages[+row.dataset.qs].index], `Quest set to stage ${D.qstages[+row.dataset.qs].index} in game.`);
      row.querySelector('.qside').prepend(b);
    }
  });
}

// ----- the sidebar panel
function qtPanelHtml(){
  return `<div class="qtpanel" id="d-test"><h3 style="margin-top:0">🎮 Testing in game</h3>
    <div class="msg" style="margin-bottom:6px">Changes happen in your running game right away.</div>
    <label class="dlabel">Go to someone</label>
    <div class="qtrow"><div class="dd" style="flex:1"><input class="inp" id="qt-npc" placeholder="Character…" autocomplete="off"><div class="ddlist" id="qt-npc-l"></div></div><button class="btn sm" id="qt-go">Go</button></div>
    <label class="dlabel">Give or take an item</label>
    <div class="dd" style="margin-bottom:6px"><input class="inp" id="qt-item" placeholder="Item… (e.g. gold)" autocomplete="off"><div class="ddlist" id="qt-item-l"></div></div>
    <div class="qtrow"><span class="msg">How many</span><input class="inp" id="qt-n" type="number" value="1" min="1" style="width:64px"><button class="btn sm" id="qt-give">Give</button><button class="btn sm" id="qt-take">Take</button></div>
    <label class="dlabel">Learn a topic</label>
    <div class="qtrow"><input class="inp" id="qt-topic" placeholder="e.g. lost ring" style="flex:1"><button class="btn sm" id="qt-addtopic">Add</button></div>
    <label class="dlabel">Variables &amp; items in your game</label>
    <div id="qt-vals"><div class="msg">Loading…</div></div></div>`;
}
function qtPanel(){
  const side = $('#dside'); if (!side) return;
  let box = $('#d-test');
  if (!LINK.connected){ if (box) box.remove(); return; }
  if (!box){
    side.insertAdjacentHTML('afterbegin', qtPanelHtml());
    ddSearch('qt-npc', 'NPC_,CREA', r => { QT.npc = r.id; });
    ddSearch('qt-item', QT_ITEM_TYPES, r => { QT.item = r.id; });
    $('#qt-npc').addEventListener('input', () => { QT.npc = null; });
    $('#qt-item').addEventListener('input', () => { QT.item = null; });
    $('#qt-go').onclick = () => { const id = QT.npc || $('#qt-npc').value.trim(); if (id) qtGoto(id); };
    const itemCmd = verb => {
      const id = QT.item || $('#qt-item').value.trim(), n = Math.max(1, +$('#qt-n').value || 1);
      if (id) qtCmd(verb, [id, n], `${verb === 'give' ? 'Gave' : 'Took'} ${n} × ${$('#qt-item').value.trim() || id}.`).then(() => qtRefresh(true));
    };
    $('#qt-give').onclick = () => itemCmd('give');
    $('#qt-take').onclick = () => itemCmd('take');
    $('#qt-addtopic').onclick = () => { const t = $('#qt-topic').value.trim(); if (t) qtCmd('topic', [t], `The player now knows "${t}".`); };
    QT.loaded = 0;
  }
  qtVals();
}
async function qtRefresh(force){
  if (!force && Date.now() - QT.loaded < 4000) return;
  QT.loaded = Date.now();
  try { QT.data = await api('/api/test' + (D.mode === 'quest' && D.key ? '?quest=' + encodeURIComponent(D.key) : '')); } catch (e){ return; }
  QT.questInGame = QT.data.quest_in_game;
  QT.sig = '';
  qtVals();
  qtQuestBar();
}
function qtFmt(v){ return v == null ? '?' : Math.abs(v - Math.round(v)) < 1e-4 ? String(Math.round(v)) : v.toFixed(2); }
function qtVals(){
  const box = $('#qt-vals'); if (!box || !QT.data) return;
  const G = LINK.game || {globals: {}, items: {}, quests: {}};
  const sig = JSON.stringify([G, QT.data.globals.length, QT.data.items.length, QT.data.quests.length]);
  if (sig === QT.sig && box.dataset.done) return;
  QT.sig = sig; box.dataset.done = '1';
  if (box.contains(document.activeElement)) return;          // don't redraw under someone typing a value
  const rows = [];
  for (const q of QT.data.quests){
    const g = G.quests[q.id.toLowerCase()];
    rows.push(`<div class="qtv"><span title="Quest">📜 ${esc(q.id)}</span><b>${g ? g.stage + (g.finished ? ' ✓' : '') : '—'}</b></div>`);
  }
  for (const v of QT.data.globals){
    const cur = G.globals[v.name.toLowerCase()];
    rows.push(`<div class="qtv"><span title="Global variable${v.missing ? ' (not in the game data)' : ''}">${v.mine ? '★ ' : ''}${esc(v.name)}</span>
      <input class="inp" data-qtg="${esc(v.name)}" value="${esc(qtFmt(cur))}" title="Type a new value and press Enter"></div>`);
  }
  for (const it of QT.data.items){
    const n = G.items[it.id.toLowerCase()];
    rows.push(`<div class="qtv"><span title="Item the player carries">🎒 ${esc(it.id)}</span><b>${n == null ? '?' : n}</b></div>`);
  }
  box.innerHTML = rows.join('') || '<div class="msg">Your mod has no quests or global variables yet.</div>';
  box.querySelectorAll('[data-qtg]').forEach(inp => inp.onkeydown = e => {
    if (e.key !== 'Enter') return;
    const val = +inp.value; if (!isFinite(val)) return toast('Type a number.', true);
    qtCmd('global', [inp.dataset.qtg, val], `${inp.dataset.qtg} set to ${val} in game.`); inp.blur();
  });
}

// called every second by the live-link poll
function qtTick(){
  if (!pageOn('dialog')) return;
  qtPanel();
  if (LINK.connected) qtRefresh(false);
  qtQuestBar();
  qtMark();
}
