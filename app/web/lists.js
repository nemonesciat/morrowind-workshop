// ---------- Leveled lists: random loot and random creature spawns ----------
const LV = {id: null, data: null, orig: null, plevel: 10, newOpen: false};
const LV_ITEM_TYPES = 'WEAP,ARMO,CLOT,MISC,BOOK,ALCH,INGR,APPA,LOCK,PROB,REPA,LIGH,LEVI';
const LV_CREA_TYPES = 'CREA,LEVC,NPC_';

function renderLists(){
  document.querySelector('nav [data-view="createv"]').classList.add('on');
  const side = $('#lside');
  if (!side.dataset.ready){
    side.dataset.ready = '1';
    side.innerHTML = `<div class="actions" style="margin-top:0"><button class="btn sm primary" id="lv-new">+ New list</button><button class="btn sm" id="lv-back">← Create</button></div>
      <h3>Open a list</h3>
      <div class="dd"><input class="inp" id="lv-find" placeholder="Find a list… (e.g. random_gold)" autocomplete="off"><div class="ddlist" id="lv-find-l"></div></div>
      <div class="msg" style="margin-top:14px;line-height:1.6">A list gives something different each time, matched to the player's level: the loot in a chest,
        or the creature at a spawn point. Put it in a container or someone's belongings like any item, or a creature list on the World map.</div>`;
    ddSearch('lv-find', 'LEVI,LEVC', r => lvOpen(r.id));
    $('#lv-new').onclick = lvNew;
    $('#lv-back').onclick = () => showView('createv');
  }
  if (!LV.id && !LV.opening) lvNewForm();
}
function lvNew(){
  LV.newOpen = true; LV.id = null; LV.data = null;
  if (!pageOn('lists')) showView('lists'); else lvNewForm();
}
function lvNewForm(){
  LV.newOpen = true;
  const prefix = (S.summary && S.summary.project ? S.summary.project.name : 'mod').replace(/[^A-Za-z0-9]/g, '').slice(0, 8).toLowerCase() || 'mod';
  $('#lmain').innerHTML = `<div class="wrap" style="max-width:760px"><h1>New leveled list</h1>
    <p class="msg">A list the game rolls on, different each time and matched to the player's level: what a chest holds, what a bandit carries, which creature appears. Start empty, or copy one of the game's (random_gold, random_weapon…) and change it.</p>
    <div class="frow"><label>Kind</label><div class="radios"><label><input type="radio" name="lv-kind" value="items" checked>Random loot (items, gold, other loot lists)</label>
      <label><input type="radio" name="lv-kind" value="creatures">Random creatures (for spawn points and summons)</label></div>
      <label>ID</label><div><input class="inp" id="lv-id" value="${esc(prefix)}_lev_" maxlength="31" style="max-width:320px"><div class="hint">Say what it is for: ${esc(prefix)}_lev_bandit_loot, ${esc(prefix)}_lev_cave_beasts.</div></div>
      <label>Start from</label><div class="dd"><input class="inp" id="lv-from" placeholder="Empty, or copy an existing list… (search, e.g. random gold, bandit)" autocomplete="off"><div class="ddlist" id="lv-from-l"></div></div></div>
    <div class="actions"><button class="btn primary" id="lv-go">Create list</button><span class="msg" id="lv-msg"></span></div>
    <div class="cwhat" id="lv-what"><b>Create list</b> makes an empty list in your mod and opens it, so you can add entries and set the odds. One Undo takes it back.</div></div>`;
  let from = null;
  const what = () => { $('#lv-what').innerHTML = `<b>Create list</b> makes ${from && $('#lv-from').value.trim() ? 'a copy of ' + esc(from) : 'an empty list'} in your mod as <b>${esc($('#lv-id').value.trim() || '…')}</b> and opens it, so you can ${from ? 'change its entries' : 'add entries'} and set the odds. One Undo takes it back.`; };
  $('#lv-id').oninput = what; $('#lv-from').oninput = () => { if (!$('#lv-from').value.trim()) from = null; what(); };
  ddSearch('lv-from', 'LEVI,LEVC', r => { from = r.id; document.querySelector(`[name=lv-kind][value=${r.type === 'LEVC' ? 'creatures' : 'items'}]`).checked = true; if ($('#lv-id').value.trim() === prefix + '_lev_') $('#lv-id').value = (prefix + '_' + r.id.replace(/^(random_|ex_|in_|l_)/i, '')).slice(0, 31); what(); });
  $('#lv-go').onclick = async () => {
    if (!await needProject()) return;
    const id = $('#lv-id').value.trim(), kind = document.querySelector('[name=lv-kind]:checked').value;
    try {
      let data = {kind, chance_none: 0, all_levels: true, entries: []};
      if (from && $('#lv-from').value.trim()){ const src = await api('/api/lev?id=' + encodeURIComponent(from)); data = Object.assign(src, {kind: src.kind}); }
      await post('/api/lev/save', {id, data, create: true});
      LV.newOpen = false; toast('Created ' + id); afterChange(); lvOpen(id);
    } catch (e){ $('#lv-msg').className = 'msg err'; $('#lv-msg').textContent = e.message; }
  };
}
async function lvOpen(id){
  if (LV.data && JSON.stringify(LV.data) !== LV.orig && !confirm('Leave the changes to ' + LV.id + ' unsaved?')) return;
  LV.opening = true;
  if (!pageOn('lists')) showView('lists');
  LV.opening = false;
  $('#lmain').innerHTML = '<div class="msg" style="padding:30px"><span class="spin"></span>Loading…</div>';
  try { LV.data = await api('/api/lev?id=' + encodeURIComponent(id)); }
  catch (e){ $('#lmain').innerHTML = `<div class="msg err" style="padding:30px">${esc(e.message)}</div>`; return; }
  LV.id = LV.data.id; LV.orig = JSON.stringify(LV.data); LV.newOpen = false;
  lvRender();
}
// who could come out of the list at a player level: [{entry, chance}] (chance in %)
function lvOdds(d, plevel){
  const ok = d.entries.filter(e => e.level <= plevel);
  let pool = ok;
  if (!d.all_levels && ok.length){ const top = Math.max(...ok.map(e => e.level)); pool = ok.filter(e => e.level === top); }
  const live = 100 - d.chance_none;
  return {none: pool.length ? d.chance_none : 100, rows: pool.map(e => ({e, chance: live / pool.length}))};
}
function lvRender(){
  const d = LV.data, items = d.kind === 'items';
  const sorted = d.entries.map((e, n) => [e, n]).sort((a, b) => a[0].level - b[0].level);
  const odds = lvOdds(d, LV.plevel);
  const sum = {};
  odds.rows.forEach(r => { const k = r.e.id.toLowerCase(); sum[k] = (sum[k] || 0) + r.chance; });
  $('#lmain').innerHTML = `<div class="wrap cwrap">
    <div class="chead"><div><h1 style="margin:0">🎲 ${esc(d.id)}</h1><div class="msg">${items ? 'Random loot' : 'Random creatures'} · ${d.mine ? (d.created ? 'made in your mod' : 'changed in your mod') : 'from ' + esc(d.src) + '. Saving puts your version in your mod.'}</div></div>
      <div class="chbtns"><button class="btn sm" id="lv-copy">⧉ Make a copy</button><button class="btn sm" id="lv-revert" style="visibility:hidden">↺ Undo edits</button><button class="btn primary" id="lv-save" disabled>Saved</button></div></div>
    <div class="cgrid2">
      <div class="card"><h3 style="margin-top:0">Entries <span class="msg">${d.entries.length}</span></h3>
        <table class="t lvtable"><tr><th style="width:90px" title="The player level from which it can appear">From level</th><th>${items ? 'Item' : 'Creature'}</th><th></th></tr>
        ${sorted.map(([e, n]) => `<tr class="${e.missing ? 'bad' : ''}"><td><input class="inp num" type="number" min="1" max="100" data-lvl="${n}" value="${e.level}" style="width:70px"></td>
          <td><span class="lvname">${thumbImg(e.id, e.type, 48, 'sm')}<span>${esc(e.name || e.id)}<small>${esc(e.name ? e.id : '')}${e.type === 'LEVI' || e.type === 'LEVC' ? ' · another list' : ''}${e.missing ? ' · not found' : ''}</small></span></span></td>
          <td><button class="btn sm danger" data-lvdel="${n}">✕</button></td></tr>`).join('') || '<tr><td colspan="3" class="msg">Empty: add something below.</td></tr>'}</table>
        <div class="crow" style="margin-top:8px;align-items:flex-end">
          ${cField('From level', `<input class="inp num" type="number" min="1" max="100" id="lv-addlvl" value="${Math.max(1, ...d.entries.map(e => e.level), 1)}" style="width:70px">`)}
          <div class="dd" style="flex:1;margin-bottom:10px"><input class="inp" id="lv-add" placeholder="+ Add ${items ? 'an item or another loot list' : 'a creature or another creature list'}… (search)" autocomplete="off"><div class="ddlist" id="lv-add-l"></div></div></div></div>
      <div>
        <div class="card"><h3 style="margin-top:0">How it rolls</h3>
          <label class="msg" style="display:block">Chance of nothing: <b id="lv-cnv">${d.chance_none}%</b><input type="range" id="lv-cn" min="0" max="100" value="${d.chance_none}" style="width:100%"></label>
          <label class="msg plrow" title="Off: only the highest-level entries the player has reached can appear, so low-level things stop appearing as they level up."><input type="checkbox" id="lv-all" ${d.all_levels ? 'checked' : ''}> Pick from all levels up to the player's (not just the highest)</label>
          ${items ? `<label class="msg plrow" title="When a chest or character holds several of this list (e.g. 5 ×), each one is rolled separately instead of 5 of the same."><input type="checkbox" id="lv-each" ${d.each ? 'checked' : ''}> Roll separately for each when there are several</label>` : ''}</div>
        <div class="card"><h3 style="margin-top:0">At player level <b id="lv-plv">${LV.plevel}</b></h3>
          <input type="range" id="lv-pl" min="1" max="60" value="${LV.plevel}" style="width:100%">
          <table class="t">${Object.entries(sum).map(([k, ch]) => { const e = d.entries.find(x => x.id.toLowerCase() === k); return `<tr><td>${esc(e.name || e.id)}</td><td class="num">${ch.toFixed(ch < 10 ? 1 : 0)}%</td></tr>`; }).join('')}
            <tr><td class="msg">Nothing</td><td class="num msg">${odds.none.toFixed(0)}%</td></tr></table>
          <div class="msg" style="font-size:11.5px;margin-top:4px">Lists inside the list roll again on their own.</div></div>
        <div class="card"><h3 style="margin-top:0">Used by</h3><div id="lv-used">${d.used_by.length ? d.used_by.map(u => `<div class="drow"><span>${u.kind === 'place' ? '📍' : u.kind === 'NPC_' ? '👤' : u.kind === 'CONT' ? '🧰' : '🎲'} ${esc(u.label)}</span>${u.kind === 'place' ? `<button class="btn sm" data-lvplace="${esc(u.key)}">Show</button>` : `<button class="btn sm" data-lvopen="${u.i}" data-lvk="${u.kind}" data-lvid="${esc(u.id)}">Open</button>`}</div>`).join('')
            : `<div class="msg">Nothing uses it yet. Add it to a container (Create → Container) or a character's inventory${items ? '' : ', or place it on the World map as a spawn point'}.</div>`}</div></div>
      </div></div></div>`;
  const dirty = () => { const x = JSON.stringify(LV.data) !== LV.orig; const b = $('#lv-save'); b.disabled = !x; b.textContent = x ? '💾 Save' : 'Saved'; $('#lv-revert').style.visibility = x ? 'visible' : 'hidden'; };
  dirty();
  $('#lmain').querySelectorAll('[data-lvl]').forEach(i => i.onchange = () => { d.entries[+i.dataset.lvl].level = Math.max(1, +i.value || 1); lvRender(); });
  $('#lmain').querySelectorAll('[data-lvdel]').forEach(b => b.onclick = () => { d.entries.splice(+b.dataset.lvdel, 1); lvRender(); });
  $('#lv-cn').oninput = e => { d.chance_none = +e.target.value; $('#lv-cnv').textContent = e.target.value + '%'; };
  $('#lv-cn').onchange = lvRender;
  $('#lv-all').onchange = e => { d.all_levels = e.target.checked; lvRender(); };
  const each = $('#lv-each'); if (each) each.onchange = e => { d.each = e.target.checked; lvRender(); };
  $('#lv-pl').oninput = e => { LV.plevel = +e.target.value; $('#lv-plv').textContent = LV.plevel; };
  $('#lv-pl').onchange = e => { LV.plevel = +e.target.value; lvRender(); };
  ddSearch('lv-add', items ? LV_ITEM_TYPES : LV_CREA_TYPES, r => {
    if (r.id.toLowerCase() === d.id.toLowerCase()) return toast("A list can't contain itself.", true);
    d.entries.push({id: r.id, name: r.name, type: r.type, level: Math.max(1, +$('#lv-addlvl').value || 1)}); lvRender();
  }, true);
  $('#lv-save').onclick = lvSave;
  $('#lv-revert').onclick = () => { LV.data = JSON.parse(LV.orig); lvRender(); };
  $('#lv-copy').onclick = async () => {
    if (!await needProject()) return;
    const id = await askText('ID for the copy:', (d.id + '_copy').slice(0, 31)); if (!id) return;
    try { await post('/api/lev/save', {id, data: d, create: true}); toast('Made a copy: ' + id); afterChange(); LV.orig = JSON.stringify(LV.data); lvOpen(id); } catch (e){ toast(e.message, true); }
  };
  $('#lmain').querySelectorAll('[data-lvplace]').forEach(b => b.onclick = () => { showView('world'); worldOpen(b.dataset.lvplace); });
  $('#lmain').querySelectorAll('[data-lvopen]').forEach(b => b.onclick = () => {
    const k = b.dataset.lvk;
    openTool(+b.dataset.lvopen, k, b.dataset.lvid);      // (an item in the item editor, a person in Characters, a list here)
  });
  v3ThumbScan($('#lmain'));
}
async function lvSave(){
  if (!await needProject()) return;
  const b = $('#lv-save'); b.disabled = true; b.innerHTML = '<span class="spin"></span>Saving…';
  try {
    const r = await post('/api/lev/save', {id: LV.id, data: LV.data});
    LV.data = r; LV.orig = JSON.stringify(r); toast('Saved ' + r.id); afterChange(); lvRender();
  } catch (e){ toast(e.message, true); b.disabled = false; b.textContent = '💾 Save'; }
}
