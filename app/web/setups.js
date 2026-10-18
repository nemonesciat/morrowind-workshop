// Who Play here starts as (a new character, or one of yours from their latest save), and the Test
// setups window: what you get on top when the game starts, put together by searching for items,
// spells, quests and variables (no IDs to remember).

// ---------------------------------------------------------------- playing as one of your characters
async function qsPlayAs(){
  qolCss(); qsCss();
  let r;
  try { r = await api('/api/saves'); } catch (e){ return toast(e.message, true); }
  const bg = document.createElement('div'); bg.className = 'modal-bg';
  const close = () => bg.remove();
  bg.onclick = e => { if (e.target === bg) close(); };
  const when = t => new Date(t * 1000).toLocaleString([], {dateStyle: 'medium', timeStyle: 'short'});
  const card = c => `<div class="qs-char ${c.folder === r.play_as ? 'on' : ''}" data-f="${esc(c.folder)}">
      <img src="/api/saves/picture?folder=${encodeURIComponent(c.folder)}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">
      <div><b>${esc(c.name)}</b>${c.name.toLowerCase() !== c.folder.toLowerCase() ? ` <span class="msg">(${esc(c.folder)})</span>` : ''}${c.quick ? ' <span class="msg">· a quick start from the Workshop</span>' : ''}
        <div class="msg">Level ${c.level}${c.class ? ' ' + esc(c.class) : ''} · in ${esc(c.cell || 'the wilds')}</div>
        <div class="msg">${esc(c.desc)} · saved ${esc(when(c.time))} · ${c.saves} save${c.saves === 1 ? '' : 's'}</div>
        ${c.missing.length ? `<div class="msg" style="color:var(--amber)">Needs ${c.missing.length} mod${c.missing.length === 1 ? '' : 's'} that aren't in your load order: ${esc(c.missing.slice(0, 4).join(', '))}${c.missing.length > 4 ? '…' : ''}. The game asks before loading it.</div>` : ''}</div></div>`;
  bg.innerHTML = `<div class="modal qs-modal" style="width:min(680px,96vw);max-height:92vh;overflow:auto"><h2>Play as</h2>
    <div class="msg">Who <b>Play here</b> starts as. One of your characters starts from their latest save and is moved to the spot you pick, with their own gear, spells and quests. Saving there makes a new save, as in any game.</div>
    <div class="qs-chars">
      <div class="qs-char ${!r.play_as ? 'on' : ''}" data-f=""><div class="qs-new">＋</div><div><b>A new character</b><div class="msg">As before: a fresh start, with nothing but the test setup.</div></div></div>
      ${r.characters.map(card).join('') || `<div class="msg" style="padding:10px">No saves found in ${esc(r.folder)}.</div>`}</div>
    <div class="foot"><button class="btn" id="qp-x">Close</button></div></div>`;
  document.body.appendChild(bg);
  bg.querySelector('#qp-x').onclick = close;
  bg.querySelectorAll('[data-f]').forEach(d => d.onclick = async () => {
    try {
      const x = await post('/api/saves/use', {folder: d.dataset.f});
      const c = r.characters.find(c => c.folder === x.play_as);
      QOL.playAs = c ? c.name : ''; qsPlayAsLabel();
      close(); toast(c ? `Play here now starts as ${c.name}, from their latest save.` : 'Play here now starts a new character.');
    } catch (e){ toast(e.message, true); }
  });
}
function qsPlayAsLabel(){ const b = $('#q-playas'); if (b) b.textContent = '👤 ' + (QOL.playAs || 'New character'); }
(async () => { try { const r = await api('/api/saves'); const c = r.characters.find(c => c.folder === r.play_as); QOL.playAs = c ? c.name : ''; qsPlayAsLabel(); } catch (e){} })();
const QS = {names: {}, stages: {}};

function qsCss(){
  if ($('#qs-css')) return;
  const c = document.createElement('style'); c.id = 'qs-css';
  c.textContent = `
  .qol-setups > div{min-width:0}
  .qs-chars{display:flex;flex-direction:column;gap:8px;margin-top:12px}
  .qs-char{display:flex;gap:12px;align-items:center;padding:8px;border:1px solid var(--line);border-radius:10px;cursor:pointer}
  .qs-char:hover{border-color:var(--line2);background:#ffffff06}
  .qs-char.on{border-color:var(--gold);background:#d9b26a12}
  .qs-char img,.qs-new{width:96px;height:60px;object-fit:cover;border-radius:6px;flex:none;background:#0004}
  .qs-new{display:flex;align-items:center;justify-content:center;font-size:26px;color:var(--faint)}
  .qs-modal{overflow-x:hidden!important}
  .qs-modal .inp{max-width:100%;box-sizing:border-box}
  .qs-side h4{font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--faint);margin:10px 0 4px;font-weight:600}
  .qs-side > div{padding:6px 8px;border-radius:7px;cursor:pointer;font-size:13px;display:flex;gap:6px;align-items:center}
  .qs-side > div.on{background:#ffffff12}
  .qs-side > div input{margin:0}
  .qs-chips{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0}
  .qs-chip{display:inline-flex;align-items:center;gap:6px;background:var(--panel2,var(--panel2-b));border:1px solid var(--line);border-radius:8px;padding:3px 4px 3px 9px;font-size:12.5px;max-width:100%}
  .qs-chip span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .qs-chip input.inp,.qs-chip select{width:76px;padding:2px 6px;font-size:12px;height:auto}
  .qs-chip select{width:auto;max-width:260px}
  .qs-chip button{background:none;border:0;color:var(--faint);cursor:pointer;font-size:11px;padding:0 4px}
  .qs-chip button:hover{color:#ff9c8a}
  .qs-sec{margin-top:12px}
  .qs-sec > b{font-size:12.5px;color:var(--muted)}
  .qs-sum{font-size:13px;line-height:1.7;margin-top:8px}
  .qs-sum li{margin-left:16px}`;
  document.head.appendChild(c);
}

async function qolSetups(){
  qolCss(); qsCss();
  const S_ = await qolLoadSetups();
  const ready = [], list = JSON.parse(JSON.stringify(S_.list || []));      // (no ready-made ones any more: "Play as" does better)
  Object.assign(QS.names, S_.names || {});
  for (const x of list){ x.god = !!x.god; x.level = x.level || 0; x.items = x.items || []; x.spells = x.spells || []; x.journal = x.journal || []; x.globals = x.globals || []; }
  let on = S_.on;
  // what's shown on the right: {kind: 'ready' | 'mine', n}
  let cur = list.findIndex(x => x.name === on) >= 0 ? {kind: 'mine', n: list.findIndex(x => x.name === on)}
          : list.length ? {kind: 'mine', n: 0} : {kind: 'ready', n: 0};
  const bg = document.createElement('div'); bg.className = 'modal-bg';
  document.body.appendChild(bg);
  const close = () => bg.remove();
  bg.onclick = e => { if (e.target === bg) close(); };
  const sel = () => cur.kind === 'ready' ? ready[cur.n] : list[cur.n];
  const nm = id => QS.names[String(id).toLowerCase()] || id;
  const blank = name => ({name, god: false, level: 0, items: [['gold_001', 500]], spells: [], journal: [], globals: [], commands: ''});

  const summary = x => `<ul class="qs-sum">
      ${x.god ? '<li>Invincible (god mode)</li>' : ''}${x.level ? `<li>Level ${x.level}</li>` : ''}
      ${x.items.length ? `<li>${x.items.map(([i, n]) => `${esc(nm(i))}${n > 1 ? ' ×' + n : ''}`).join(', ')}</li>` : ''}
      ${x.spells.length ? `<li>${x.spells.length} spells: ${x.spells.map(s => esc(nm(s))).join(', ')}</li>` : ''}
      ${x.journal_n ? `<li>Every quest's journal at its end (${x.journal_n} quests)</li>` : x.journal.length ? `<li>${x.journal.length} quest stage${x.journal.length > 1 ? 's' : ''}</li>` : ''}
      ${x.globals.length ? `<li>${x.globals.length} variable${x.globals.length > 1 ? 's' : ''} set</li>` : ''}</ul>`;

  const editor = x => `
    <label>Name</label><input class="inp" id="qs-name" value="${esc(x.name)}">
    <div style="display:flex;gap:18px;align-items:center;margin-top:10px;flex-wrap:wrap">
      <label class="msg" style="display:flex;gap:6px;align-items:center;margin:0"><input type="checkbox" id="qs-god" ${x.god ? 'checked' : ''}> Invincible (god mode)</label>
      <label class="msg" style="display:flex;gap:6px;align-items:center;margin:0">Level <input class="inp" id="qs-level" type="number" min="0" max="100" value="${x.level || ''}" placeholder="as is" style="width:80px"></label></div>
    <div class="qs-sec"><b>Items to carry</b>
      <div class="qs-chips">${x.items.map(([i, n], k) => `<span class="qs-chip"><span title="${esc(i)}">${esc(nm(i))}</span><input class="inp" type="number" min="1" value="${n}" data-icnt="${k}" title="How many"><button data-idel="${k}" title="Take it out">✕</button></span>`).join('')}</div>
      <div class="dd"><input class="inp" id="qs-iadd" placeholder="+ Add an item (search: gold, potion, a weapon…)" autocomplete="off"><div class="ddlist" id="qs-iadd-l"></div></div></div>
    <div class="qs-sec"><b>Spells to know</b>
      <div class="qs-chips">${x.spells.map((s, k) => `<span class="qs-chip"><span title="${esc(s)}">${esc(nm(s))}</span><button data-sdel="${k}" title="Take it out">✕</button></span>`).join('')}</div>
      <div class="dd"><input class="inp" id="qs-sadd" placeholder="+ Add a spell (search: mark, levitate, fire…)" autocomplete="off"><div class="ddlist" id="qs-sadd-l"></div></div></div>
    <div class="qs-sec"><b>Quests, at a stage</b> <span class="msg">(to test a quest from the middle)</span>
      <div class="qs-chips">${x.journal.map(([q, st], k) => `<span class="qs-chip"><span>${esc(q)}</span>${QS.stages[q.toLowerCase()]
        ? `<select data-jst="${k}">${QS.stages[q.toLowerCase()].map(s => `<option value="${s.index}" ${s.index === st ? 'selected' : ''}>${s.index}${s.finished ? ' (done)' : ''}: ${esc((s.text || '').slice(0, 60))}</option>`).join('')}</select>`
        : `<input class="inp" type="number" value="${st}" data-jst="${k}" title="Stage">`}<button data-jdel="${k}" title="Take it out">✕</button></span>`).join('')}</div>
      <div class="dd"><input class="inp" id="qs-qadd" placeholder="+ Add a quest (search its ID, e.g. fargoth)" autocomplete="off"><div class="ddlist" id="qs-qadd-l"></div></div></div>
    <div class="qs-sec"><b>Variables</b> <span class="msg">(global variables your scripts or quests check)</span>
      <div class="qs-chips">${x.globals.map(([g, v], k) => `<span class="qs-chip"><span>${esc(g)} =</span><input class="inp" type="number" step="any" value="${v}" data-gval="${k}"><button data-gdel="${k}" title="Take it out">✕</button></span>`).join('')}</div>
      <div class="dd"><input class="inp" id="qs-gadd" placeholder="+ Set a variable (search)" autocomplete="off"><div class="ddlist" id="qs-gadd-l"></div></div></div>
    <details class="qs-sec" ${x.commands ? 'open' : ''}><summary class="msg" style="cursor:pointer">Other console commands</summary>
      <textarea class="inp" id="qs-cmds" style="width:100%;box-sizing:border-box;min-height:60px;font-family:var(--mono);font-size:12px;margin-top:6px" placeholder="One per line, e.g. player->setstrength 100">${esc(x.commands || '')}</textarea></details>`;

  // what's typed in the boxes goes back into the setup before anything redraws
  const keep = () => {
    const x = cur.kind === 'mine' && list[cur.n]; if (!x) return;
    const v = id => { const e = bg.querySelector('#' + id); return e ? e.value : ''; };
    const was = x.name; x.name = v('qs-name').trim() || x.name; if (on === was) on = x.name;
    x.god = !!(bg.querySelector('#qs-god') || {}).checked; x.level = parseInt(v('qs-level')) || 0; x.commands = v('qs-cmds');
    bg.querySelectorAll('[data-icnt]').forEach(i => { x.items[+i.dataset.icnt][1] = Math.max(1, parseInt(i.value) || 1); });
    bg.querySelectorAll('[data-jst]').forEach(i => { x.journal[+i.dataset.jst][1] = parseInt(i.value) || 0; });
    bg.querySelectorAll('[data-gval]').forEach(i => { x.globals[+i.dataset.gval][1] = parseFloat(i.value) || 0; });
  };
  const loadStages = async q => {
    const k = q.toLowerCase(); if (QS.stages[k]) return;
    try { const d = await api('/api/dlg/quest?key=' + encodeURIComponent(k)); QS.stages[k] = d.stages; if (d.title) QS.names[k] = d.title; } catch (e){ QS.stages[k] = null; }
  };

  const draw = () => {
    const x = sel();
    bg.innerHTML = `<div class="modal qs-modal" style="width:min(860px,96vw);max-height:92vh;overflow:auto"><h2>Test setups</h2>
      <div class="msg">What you get on top when <b>Play here</b> starts the game, so you can try something without playing up to it. Pick one with the round button.</div>
      <div class="msg" style="margin-top:6px">Playing as: <b>${esc(QOL.playAs || 'a new character')}</b> <button class="btn sm" id="qs-as">👤 Change…</button></div>
      <div class="qol-setups" style="margin-top:12px"><div class="qs-side">
        <div data-pick="none" class="${!on ? 'on' : ''}"><input type="radio" name="qs-on" ${!on ? 'checked' : ''}> Nothing extra</div>
        <h4>Your setups</h4>
        ${list.map((s, n) => `<div data-m="${n}" class="${cur.kind === 'mine' && cur.n === n ? 'on' : ''}"><input type="radio" name="qs-on" ${s.name === on ? 'checked' : ''}> ${esc(s.name)}</div>`).join('') || '<div class="msg" style="cursor:default">None yet</div>'}
        <button class="btn sm" id="qs-new" style="margin-top:8px">+ New setup</button></div>
      <div>${!x ? '<div class="msg" style="padding:20px 0">No setups yet. <b>+ New setup</b> makes one: some gold and items, spells, a quest at the stage you want to test.</div>' : cur.kind === 'ready'
        ? `<div style="font-weight:600;font-size:15px">${esc(x.name)}</div><div class="msg">${esc(x.about || '')}</div>${summary(x)}
           <div class="actions" style="margin-top:10px"><button class="btn sm primary" id="qs-use">${x.name === on ? '✓ Used when playing' : 'Use this when playing'}</button>
             <button class="btn sm" id="qs-copy">Make a copy to change</button><button class="btn sm" id="qs-now" title="Give its items (and quest stages, if not too many) in the game that's running now">▶ Give it now in game</button></div>`
        : editor(x) + `<div class="actions" style="margin-top:12px"><button class="btn sm primary" id="qs-use">${x.name === on ? '✓ Used when playing' : 'Use this when playing'}</button>
             <button class="btn sm" id="qs-now">▶ Give it now in game</button><button class="btn sm" id="qs-copy">Duplicate</button><button class="btn sm danger" id="qs-del">Delete</button></div>`}
      </div></div>
      <div class="foot"><button class="btn" id="qs-x">Cancel</button><button class="btn primary" id="qs-save">Save</button></div></div>`;
    const $$ = s => bg.querySelector(s);
    $$('#qs-x').onclick = close; $$('#qs-save').onclick = save;
    $$('#qs-as').onclick = () => { keep(); qsPlayAs(); };
    $$('#qs-new').onclick = () => { keep(); list.push(blank('My setup ' + (list.length + 1))); cur = {kind: 'mine', n: list.length - 1}; draw(); };
    bg.querySelectorAll('[data-pick],[data-r],[data-m]').forEach(d => d.onclick = e => {
      keep();
      if (d.dataset.pick){ on = ''; draw(); return; }
      cur = d.dataset.r != null ? {kind: 'ready', n: +d.dataset.r} : {kind: 'mine', n: +d.dataset.m};
      if (e.target.matches('input[type=radio]')) on = sel().name;
      draw();
    });
    if (!x) return;
    $$('#qs-use').onclick = () => { keep(); on = x.name; draw(); };
    $$('#qs-copy').onclick = async () => {
      keep();
      let c = JSON.parse(JSON.stringify(x)); delete c.ready; delete c.about;
      if (cur.kind === 'ready' && c.journal_n){ toast('The copy has everything but the quest list (too long to change by hand).'); }
      delete c.journal_n; c.name = x.name + ' (copy)';
      list.push(c); cur = {kind: 'mine', n: list.length - 1}; draw();
    };
    $$('#qs-now').onclick = async () => {
      keep();
      try {
        const r = await post('/api/testsetups/give', cur.kind === 'ready' ? {name: x.name} : {setup: x});
        toast(`Sent ${r.sent} to the game.` + (r.skipped.length ? ` (${r.skipped.join('; ')} only come with a fresh start.)` : ''));
      } catch (e){ toast(e.message, true); }
    };
    if (cur.kind !== 'mine') return;
    $$('#qs-del').onclick = () => { if (!confirm(`Delete the test setup "${x.name}"?`)) return; if (x.name === on) on = ''; list.splice(cur.n, 1); cur = list.length ? {kind: 'mine', n: Math.max(0, cur.n - 1)} : {kind: 'ready', n: 0}; draw(); };
    const del = (attr, arr) => bg.querySelectorAll(`[${attr}]`).forEach(b => b.onclick = () => { keep(); arr.splice(+b.getAttribute(attr), 1); draw(); });
    del('data-idel', x.items); del('data-sdel', x.spells); del('data-jdel', x.journal); del('data-gdel', x.globals);
    const remember = r => { QS.names[r.id.toLowerCase()] = r.name || r.id; };
    ddSearch('qs-iadd', ITEM_TYPES.concat(['LIGH']).join(','), r => { keep(); remember(r); const have = x.items.find(i => i[0].toLowerCase() === r.id.toLowerCase()); if (have) have[1]++; else x.items.push([r.id, r.id.toLowerCase() === 'gold_001' ? 500 : 1]); draw(); }, true);
    ddSearch('qs-sadd', 'SPEL', r => { keep(); remember(r); if (!x.spells.some(s => s.toLowerCase() === r.id.toLowerCase())) x.spells.push(r.id); draw(); });
    ddSearch('qs-gadd', 'GLOB', r => { keep(); if (!x.globals.some(g => g[0].toLowerCase() === r.id.toLowerCase())) x.globals.push([r.id, 1]); draw(); });
    // quests: only real quests (with journal stages), from the dialogue list
    const qi = $$('#qs-qadd'), ql = $$('#qs-qadd-l'); let qt, qseq = 0;
    qi.oninput = () => { clearTimeout(qt); qt = setTimeout(async () => {
      const q = qi.value.trim(), my = ++qseq; if (!q){ ql.style.display = 'none'; return; }
      const rows = await api('/api/dlg/index?' + new URLSearchParams({q, kind: 4, limit: 30})).catch(() => []);
      if (my !== qseq) return;
      ql.innerHTML = rows.map((r, n) => `<div data-n="${n}">${esc(r.id)}<small>${r.lines} stages${r.mine ? ' · your mod' : ''}</small></div>`).join('') || '<div class="msg">No quest like that</div>';
      ql.style.display = 'block';
      ql.querySelectorAll('[data-n]').forEach(d => d.onclick = async () => {
        const r = rows[+d.dataset.n]; ql.style.display = 'none'; keep();
        await loadStages(r.id);
        const st = QS.stages[r.id.toLowerCase()];
        if (!x.journal.some(j => j[0].toLowerCase() === r.id.toLowerCase())) x.journal.push([r.id, st && st.length ? st[0].index : 10]);
        draw();
      });
    }, 150); };
    qi.onblur = () => setTimeout(() => { if (!ql.matches(':hover')) ql.style.display = 'none'; }, 150);
  };
  const save = async () => {
    keep();
    try {
      const r = await post('/api/testsetups', {list, on});
      QOL.setups = r; QOL.setupOn = r.on; const b = $('#q-setup'); if (b) b.textContent = '🧪 ' + (r.on || 'Test setup…');
      close(); toast(r.on ? `Play here now starts with "${r.on}".` : 'Saved. Play here starts as usual.');
    } catch (e){ toast(e.message, true); }
  };
  // the quests already in your setups: their stages, to pick from
  await Promise.all(list.flatMap(x => x.journal.map(j => loadStages(j[0]))));
  draw();
}
