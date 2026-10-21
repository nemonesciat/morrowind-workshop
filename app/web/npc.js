// ---------- Characters ----------
// Everything about one NPC on one page: who they are and how they look, their stats,
// how they behave, what they offer, where they take you, and what they carry and know.
const C = {id: null, data: null, orig: null, opts: null, tab: 'who', calc: null, dirty: false};
const C_TABS = [['who', '👤 Who'], ['stats', '📊 Stats'], ['ai', '🧭 Behaviour'], ['services', '🪙 Services & travel'], ['items', '🎒 Carries & knows']];

async function cOpts(){ if (!C.opts) C.opts = await api('/api/npc/options'); return C.opts; }

async function renderChars(){
  const side = $('#cside');
  if (!side.dataset.ready){
    side.dataset.ready = '1';
    side.innerHTML = `<div class="actions" style="margin-top:0"><button class="btn sm primary" id="c-new">+ New character</button></div>
      <h3>Open a character</h3>
      <div class="dd"><input class="inp" id="c-find" placeholder="Anyone… (e.g. Fargoth)" autocomplete="off"><div class="ddlist" id="c-find-l"></div></div>
      <h3>In my mod</h3><div id="c-mine"></div>
      <h3>Groups and backgrounds</h3><div class="drow" data-crules="faction"><span>🏛 Factions</span></div><div class="drow" data-crules="class"><span>🎓 Classes</span></div>
      <div class="drow" data-crules="race"><span>🧝 Races</span></div><div class="drow" data-crules="birthsign"><span>✨ Birthsigns</span></div>`;
    side.querySelectorAll('[data-crules]').forEach(r => r.onclick = () => ruShow(r.dataset.crules));
    ddSearch('c-find', 'NPC_,CREA', r => cOpen(r.id));
    $('#c-new').onclick = () => { CR.kind = 'npc'; showView('createv'); };
    side.addEventListener('click', e => { const r = e.target.closest('[data-copen]'); if (r) cOpen(r.dataset.copen); });
  }
  cMine();
  if (!C.id) cWelcome();
}
async function cMine(){
  let m; try { m = await api('/api/dlg/mine'); } catch (e){ m = {characters: []}; }
  const chars = (m.characters || []).filter(c => !c.type || c.type === 'NPC_');
  $('#c-mine').innerHTML = chars.length
    ? chars.map(c => `<div class="drow ${C.id && C.id.toLowerCase() === c.id.toLowerCase() ? 'on' : ''}" data-copen="${esc(c.id)}"><span>👤 ${esc(c.name || c.id)}</span><small>${esc(c.id)}</small></div>`).join('')
    : `<div class="msg" style="padding:4px 2px">Characters you create or change show up here.</div>`;
}
function cWelcome(){
  $('#cmain').innerHTML = `<div class="wrap" style="max-width:820px"><h1>Characters</h1>
    <p class="msg" style="font-size:14px;line-height:1.7">Open anyone on the left, from your own characters to Fargoth, and change how they look, what they're good at,
    how they behave, what they sell, where they take you and what they carry. Changing someone from the base game keeps the original safe:
    your version goes into your mod.</p>
    <div class="cgrid">
      <div class="ccard" data-cw="new"><div style="font-size:26px">➕</div><b>Make someone new</b><div class="msg">Pick a role (townsperson, merchant, guard, quest giver) and the Workshop sets them up. Then fine-tune them here.</div></div>
      <div class="ccard" data-cw="find"><div style="font-size:26px">🔎</div><b>Change someone</b><div class="msg">Give a merchant more gold, make a quest giver essential, teach a trainer new skills.</div></div>
      <div class="ccard" data-cw="talk"><div style="font-size:26px">💬</div><b>What they say</b><div class="msg">Greetings and topics are on the Dialogue page. Every character here has a button to go there.</div></div>
    </div></div>`;
  $('#cmain').querySelectorAll('[data-cw]').forEach(c => c.onclick = () => {
    if (c.dataset.cw === 'new') $('#c-new').click(); else if (c.dataset.cw === 'find') $('#c-find').focus(); else showView('dialog');
  });
}

async function cOpen(id, keepTab){
  if (C.dirty && C.id && C.id.toLowerCase() !== id.toLowerCase() && !confirm('You have changes to ' + (C.data.name || C.id) + ' that are not saved. Leave them?')) return;
  showView('chars');
  $('#cmain').innerHTML = '<div class="msg" style="padding:30px"><span class="spin"></span>Loading…</div>';
  try { await cOpts(); C.data = await api('/api/npc?id=' + encodeURIComponent(id)); }
  catch (e){ $('#cmain').innerHTML = `<div class="msg err" style="padding:30px">${esc(e.message)}</div>`; return; }
  C.id = C.data.id; C.orig = JSON.stringify(C.data); C.dirty = false; C.calc = C.data.calc; C.lookFrom = null;
  if (!keepTab) C.tab = 'who';
  cMine(); cRender();
}
function cChanged(){
  C.dirty = JSON.stringify(C.data) !== C.orig;
  const b = $('#c-save'); if (b){ b.disabled = !C.dirty; b.textContent = C.dirty ? '💾 Save changes' : 'Saved'; }
  const r = $('#c-revert'); if (r) r.style.visibility = C.dirty ? 'visible' : 'hidden';
}
window.addEventListener('beforeunload', e => { if (C.dirty){ e.preventDefault(); e.returnValue = ''; } });

function cRender(){
  const d = C.data;
  const race = (C.opts.races.find(r => r.id.toLowerCase() === d.race.toLowerCase()) || {}).name || d.race;
  const cls = (C.opts.classes.find(r => r.id.toLowerCase() === d.cls.toLowerCase()) || {}).name || d.cls;
  $('#cmain').innerHTML = `<div class="wrap cwrap">
    <div class="chead">
      <div><h1 style="margin:0">${esc(d.name || d.id)}</h1>
        <div class="msg">${esc(d.id)} · ${d.kind === 'creature' ? `${esc((C.opts.ctypes || [])[d.ctype] || 'Creature')}` : `${d.female ? 'female' : 'male'} ${esc(race)} ${esc(cls)}`}, level ${d.level}${d.essential ? ' · <b>essential</b>' : ''}</div></div>
      <div class="chbtns">
        <button class="btn sm" id="c-talk" title="Greetings and topics for this character">💬 Dialogue</button>
        <button class="btn sm" id="c-copy" title="Make a new character based on this one">⧉ Make a copy</button>
        <button class="btn sm" id="c-revert" style="visibility:hidden" title="Forget the changes you haven't saved">↺ Undo edits</button>
        <button class="btn primary" id="c-save" disabled>Saved</button>
      </div>
    </div>
    ${d.mine ? '' : `<div class="cnote">This character comes from <b>${esc(d.src)}</b>. When you save, your changed version goes into your mod and the original stays untouched.</div>`}
    <div class="ctabs">${C_TABS.map(([k, t]) => `<button data-ctab="${k}" class="${C.tab === k ? 'on' : ''}">${t}</button>`).join('')}</div>
    <div id="cbody"></div></div>`;
  $('#cmain').querySelectorAll('[data-ctab]').forEach(b => b.onclick = () => { C.tab = b.dataset.ctab; cRender(); });
  $('#c-save').onclick = cSave;
  $('#c-revert').onclick = () => { C.data = JSON.parse(C.orig); cRender(); };
  $('#c-talk').onclick = () => { showView('dialog'); dOpen('npc', d.id); };
  $('#c-copy').onclick = cCopy;
  (d.kind === 'creature' ? {who: cWhoCrea, stats: cStatsCrea, ai: cAI, services: cServices, items: cItems}
    : {who: cWho, stats: cStats, ai: cAI, services: cServices, items: cItems})[C.tab]($('#cbody'));
  cChanged();
}

// small helpers for forms bound to C.data
function cField(label, html, hint){ return `<label class="cfield"><span>${label}</span>${html}${hint ? `<small>${hint}</small>` : ''}</label>`; }
function cBind(box){
  box.querySelectorAll('[data-cf]').forEach(el => {
    const set = () => {
      const path = el.dataset.cf.split('.');
      let o = C.data; for (let i = 0; i < path.length - 1; i++) o = o[path[i]];
      const k = path[path.length - 1];
      o[k] = el.type === 'checkbox' ? el.checked : el.dataset.num !== undefined ? (el.value === '' ? 0 : +el.value) : el.value;
      const out = el.parentElement.querySelector('output'); if (out) out.textContent = el.value;
      if (el.dataset.re) cRender(); else cChanged();
      if (el.dataset.calc) cRecalc();
    };
    el.addEventListener(el.type === 'checkbox' || el.tagName === 'SELECT' ? 'change' : 'input', set);
  });
}
function cSelect(path, list, cur, opts){
  opts = opts || {};
  const has = list.some(x => x.id.toLowerCase() === (cur || '').toLowerCase());
  return `<select class="inp" data-cf="${path}" ${opts.re ? 'data-re="1"' : ''} ${opts.calc ? 'data-calc="1"' : ''}>
    ${opts.none ? `<option value="">${opts.none}</option>` : ''}
    ${!has && cur ? `<option value="${esc(cur)}" selected>${esc(cur)}</option>` : ''}
    ${list.map(x => `<option value="${esc(x.id)}" ${x.id.toLowerCase() === (cur || '').toLowerCase() ? 'selected' : ''}>${esc(x.name || x.id)}</option>`).join('')}</select>`;
}
function cSlider(path, val, min, max, label, hint){
  return `<label class="cfield"><span>${label} <output>${val}</output></span><input type="range" min="${min}" max="${max}" value="${val}" data-cf="${path}" data-num>${hint ? `<small>${hint}</small>` : ''}</label>`;
}
async function cRecalc(){
  const d = C.data;
  try { C.calc = await api('/api/npc/calc?' + new URLSearchParams({race: d.race, cls: d.cls, level: d.level, female: d.female ? '1' : '0'})); } catch (e){ C.calc = null; }
  if (C.tab === 'stats') cRender();
}

// ----- Who: name, race, class, faction, looks
function cWho(box){
  const d = C.data, o = C.opts;
  const fac = o.factions.find(f => f.id.toLowerCase() === (d.faction || '').toLowerCase());
  box.innerHTML = `<div class="cgrid2">
    <div class="card">
      ${cField('Name', `<input class="inp" data-cf="name" value="${esc(d.name)}" maxlength="31">`, 'What players see.')}
      <div class="crow">${cField('Race', cSelect('race', o.races, d.race, {re: 1, calc: 1}))}
        ${cField('Sex', `<select class="inp" id="c-sex"><option value="">Male</option><option value="1" ${d.female ? 'selected' : ''}>Female</option></select>`)}</div>
      ${cField('Class', cSelect('cls', o.classes, d.cls, {calc: 1}), 'Decides their skills when stats are auto-calculated, and (for those) what services they offer.')}
      <div class="crow">${cField('Faction', cSelect('faction', o.factions, d.faction, {none: 'None', re: 1}))}
        ${fac ? cField('Rank', `<select class="inp" data-cf="rank" data-num>${fac.ranks.map((r, n) => `<option value="${n}" ${n === d.rank ? 'selected' : ''}>${n}. ${esc(r)}</option>`).join('')}</select>`) : ''}</div>
      <div class="crow">${cField('Level', `<input class="inp" type="number" min="0" max="100" data-cf="level" data-num data-calc="1" value="${d.level}">`)}
        ${cField('Size', `<input class="inp" type="number" min="0.5" max="2" step="0.05" data-cf="scale" data-num value="${d.scale}">`, '1 is normal')}</div>
      ${cField('Script', `<div class="dd"><input class="inp" id="c-script" value="${esc(d.script)}" placeholder="None" autocomplete="off"><div class="ddlist" id="c-script-l"></div></div>`,
        'A script that runs on this character, e.g. for a quest.' + (d.script ? ` <a href="#" id="c-openscript">Open it</a>` : ''))}
      <div class="cchecks">
        <label title="The game won't let them die; players get a warning if they're needed for a quest"><input type="checkbox" data-cf="essential" ${d.essential ? 'checked' : ''}> Essential (can't be killed)</label>
        <label title="Comes back some time after being killed (mostly for guards and creatures)"><input type="checkbox" data-cf="respawn" ${d.respawn ? 'checked' : ''}> Respawns</label>
        <label>Blood <select class="inp sm" data-cf="blood" data-num>${o.blood.map(([n, v]) => `<option value="${v}" ${v === d.blood ? 'selected' : ''}>${esc(n)}</option>`).join('')}</select></label>
      </div>
      ${d.placed.length ? `<div class="cplaced"><b>Stands in:</b> ${d.placed.map(p => `<a href="#" data-cplace="${esc(p.key)}">${esc(p.name)}</a>`).join(' · ')}</div>`
        : `<div class="cplaced msg">Not placed anywhere yet. Find them in the World map's Place tab to put them somewhere.</div>`}
    </div>
    <div class="card"><h3 style="margin-top:0">Looks</h3><div id="c-looks"></div></div></div>`;
  cBind(box);
  $('#c-sex').onchange = e => { d.female = !!e.target.value; cRecalc(); cRender(); };
  ddSearch('c-script', 'SCPT', r => { d.script = r.id; cRender(); });
  $('#c-script').addEventListener('change', e => { if (!e.target.value.trim()){ d.script = ''; cChanged(); } });
  const os = $('#c-openscript'); if (os) os.onclick = e => { e.preventDefault(); if (typeof sOpen === 'function') sOpen(d.script); };
  box.querySelectorAll('[data-cplace]').forEach(a => a.onclick = e => { e.preventDefault(); showView('world'); worldOpen(a.dataset.cplace); });
  cLooks();
}
// "b_n_dark elf_m_head_05" -> "05"; heads from other mods keep a short tag of where they're from
function cLookName(id){
  const m = id.match(/(?:head|hair)[_ ]*(.*)$/i), num = m ? (m[1] || '1').replace(/_/g, ' ') : id;
  if (/^b_n_/i.test(id)) return num;
  const tag = id.split(/[_ ]/)[0];
  return m ? `${tag} · ${num}` : id;
}
function cLooks(){
  const d = C.data, box = $('#c-looks'); if (!box) return;
  const race = C.opts.races.find(r => r.id.toLowerCase() === d.race.toLowerCase());
  const names = new Set([d.race.toLowerCase(), race ? race.name.toLowerCase() : '']);
  const fits = (h, part) => h.part === part && h.female === d.female && names.has(h.race.toLowerCase()) && (!h.vampire || C.vamp);
  const grid = (part, cur, path) => {
    const list = C.opts.heads.filter(h => fits(h, part) || h.id.toLowerCase() === (cur || '').toLowerCase());
    if (!list.length) return `<div class="msg">No ${part === 'head' ? 'heads' : 'hair styles'} found for this race and sex.</div>`;
    return `<div class="clooks">${list.map(h => `<button class="clook ${h.id.toLowerCase() === (cur || '').toLowerCase() ? 'on' : ''}" data-look="${path}" data-lid="${esc(h.id)}" title="${esc(h.id)}">
      <img class="thumb" data-tid="${esc(h.id)}" data-tt="BODY" data-ts="96" data-tview="front" alt=""><span>${esc(cLookName(h.id))}</span></button>`).join('')}</div>`;
  };
  box.innerHTML = `<h4>Head</h4>${grid('head', d.head, 'head')}<h4>Hair</h4>${grid('hair', d.hair, 'hair')}
    <label class="msg" style="display:block;margin-top:8px"><input type="checkbox" id="c-vamp" ${C.vamp ? 'checked' : ''}> Also show vampire heads</label>`;
  box.querySelectorAll('[data-look]').forEach(b => b.onclick = () => { d[b.dataset.look] = b.dataset.lid; cLooks(); cChanged(); });
  $('#c-vamp').onchange = e => { C.vamp = e.target.checked; cLooks(); };
  v3ThumbScan(box);
}

// ----- creatures: who they are and how they look (their model), then their stats
function cWhoCrea(box){
  const d = C.data, o = C.opts;
  const chk = (k, label, tip) => `<label title="${tip || ''}"><input type="checkbox" data-cf="${k}" ${d[k] ? 'checked' : ''}> ${label}</label>`;
  box.innerHTML = `<div class="cgrid2">
    <div class="card">
      ${cField('Name', `<input class="inp" data-cf="name" value="${esc(d.name)}" maxlength="31">`)}
      <div class="crow">${cField('Kind', `<select class="inp" data-cf="ctype" data-num>${o.ctypes.map((t, n) => `<option value="${n}" ${n === d.ctype ? 'selected' : ''}>${t}</option>`).join('')}</select>`, 'Spells like Turn Undead or Banish Daedra work on the matching kind.')}
        ${cField('Level', `<input class="inp" type="number" min="0" max="100" data-cf="level" data-num value="${d.level}">`)}
        ${cField('Size', `<input class="inp" type="number" min="0.5" max="2" step="0.05" data-cf="scale" data-num value="${d.scale}">`, '1 is normal')}</div>
      ${cField('Script', `<div class="dd"><input class="inp" id="c-script" value="${esc(d.script)}" placeholder="None" autocomplete="off"><div class="ddlist" id="c-script-l"></div></div>`,
        d.script ? `<a href="#" id="c-openscript">Open it</a>` : 'A script that runs on this creature.')}
      ${cField('Sounds of', `<div class="dd"><input class="inp" id="c-sound" value="${esc(d.sound)}" placeholder="its own" autocomplete="off"><div class="ddlist" id="c-sound-l"></div></div>`, 'Use another creature\'s roars, footsteps and hurt sounds.')}
      <div class="cchecks grid">
        ${chk('walks', 'Walks', 'Moves on the ground')}${chk('swims', 'Swims', 'Can move in water (slaughterfish, dreugh)')}${chk('flies', 'Flies', 'Cliff racers, winged twilights')}
        ${chk('biped', 'Walks on two legs', 'Humanoid shape: can wear armor and clothes')}${chk('weapons', 'Uses weapons & shields', 'Equips the best weapon and shield it carries')}
        ${chk('essential', 'Essential', "Can't be killed")}${chk('respawn', 'Respawns', 'Comes back some time after being killed')}</div>
      <label class="msg">Blood <select class="inp sm" data-cf="blood" data-num>${o.blood.map(([n, v]) => `<option value="${v}" ${v === d.blood ? 'selected' : ''}>${esc(n)}</option>`).join('')}</select></label>
      ${d.placed.length ? `<div class="cplaced"><b>Found in:</b> ${d.placed.map(p => `<a href="#" data-cplace="${esc(p.key)}">${esc(p.name)}</a>`).join(' · ')}</div>` : ''}
    </div>
    <div class="card"><h3 style="margin-top:0">Looks</h3>
      <div class="ccrea"><img class="thumb" data-tid="${esc(C.lookFrom || d.id)}" data-tt="CREA" data-ts="220" alt=""></div>
      <div class="msg" style="margin:6px 0">${esc(d.model)}</div>
      <div class="dd"><input class="inp" id="c-look" placeholder="Look like another creature… (search)" autocomplete="off"><div class="ddlist" id="c-look-l"></div></div>
      <div class="msg" style="margin-top:6px;font-size:11.5px">Uses that creature's model and animations. Its stats stay yours.</div></div></div>`;
  cBind(box);
  ddSearch('c-script', 'SCPT', r => { d.script = r.id; cRender(); });
  $('#c-script').addEventListener('change', e => { if (!e.target.value.trim()){ d.script = ''; cChanged(); } });
  ddSearch('c-sound', 'CREA', r => { d.sound = r.id; cRender(); });
  $('#c-sound').addEventListener('change', e => { if (!e.target.value.trim()){ d.sound = ''; cChanged(); } });
  ddSearch('c-look', 'CREA', async r => {
    try { const other = await api('/api/npc?id=' + encodeURIComponent(r.id)); d.model = other.model; C.lookFrom = r.id; cRender(); }
    catch (e){ toast(e.message, true); }
  });
  const os = $('#c-openscript'); if (os) os.onclick = e => { e.preventDefault(); sOpen(d.script); };
  box.querySelectorAll('[data-cplace]').forEach(a => a.onclick = e => { e.preventDefault(); showView('world'); worldOpen(a.dataset.cplace); });
  v3ThumbScan(box);
}
function cStatsCrea(box){
  const d = C.data, o = C.opts;
  const num = (path, v, max) => `<input class="inp num" type="number" min="0" max="${max || 1000}" data-cf="${path}" data-num value="${v}">`;
  box.innerHTML = `<div class="cgrid2">
    <div class="card"><h3 style="margin-top:0">Attributes</h3><div class="cstats">${o.attributes.map((a, i) => `<span>${a}</span>${num('attributes.' + i, d.attributes[i])}`).join('')}</div>
      <h3>Health, magicka, fatigue</h3><div class="cstats">${['health', 'magicka', 'fatigue'].map(k => `<span>${k[0].toUpperCase() + k.slice(1)}</span>${num(k, d[k], 100000)}`).join('')}</div></div>
    <div class="card"><h3 style="margin-top:0">Fighting</h3>
      <div class="msg" style="margin-bottom:6px">Creatures use three skills for everything: combat (attacks, blocking), magic (spells) and stealth (sneaking, dodging).</div>
      <div class="cstats"><span>Combat</span>${num('combat', d.combat, 255)}<span>Magic</span>${num('magic', d.magic, 255)}<span>Stealth</span>${num('stealth', d.stealth, 255)}</div>
      <h3>Attacks (damage, lowest to highest)</h3><div class="cstats two">${[0, 1, 2].map(n => `<span>Attack ${n + 1}</span><span class="crow" style="gap:4px;flex-wrap:nowrap">${num(`attacks.${n}.0`, d.attacks[n][0])}–${num(`attacks.${n}.1`, d.attacks[n][1])}</span>`).join('')}</div>
      <h3>Other</h3><div class="cstats">
        <span title="How much a soul gem holding its soul is worth; also what it powers when enchanting">Soul</span>
        <span class="crow" style="gap:4px;flex-wrap:nowrap">${num('soul', d.soul, 100000)}<select class="inp sm" id="c-soulpick"><option value="">size…</option>${o.souls.map(([n, v]) => `<option value="${v}">${n} (${v})</option>`).join('')}</select></span>
        <span title="Gold it carries; for merchant creatures (like the Creeper) what they can pay">Gold</span>${num('gold', d.gold, 999999999)}</div></div></div>`;
  cBind(box);
  $('#c-soulpick').onchange = e => { if (e.target.value === '') return; d.soul = +e.target.value; cRender(); };
}

// ----- Stats
function cStats(box){
  const d = C.data, o = C.opts, c = C.calc;
  const fac = o.factions.find(f => f.id.toLowerCase() === (d.faction || '').toLowerCase());
  const num = (path, v, max) => `<input class="inp num" type="number" min="0" max="${max || 255}" data-cf="${path}" data-num value="${v}">`;
  const show = (arr, i) => d.auto ? `<b>${c ? c[arr][i] : '?'}</b>` : num(arr + '.' + i, d[arr][i]);
  box.innerHTML = `<div class="card">
    <label class="cauto"><input type="checkbox" id="c-auto" ${d.auto ? 'checked' : ''}> <b>Work out stats automatically</b>
      <span class="msg">from their race, class and level, the way the game does for most people.</span></label>
    ${d.auto ? `<div class="msg" style="margin:6px 0 0">These are the numbers the game will give them. Untick the box to set each one yourself.</div>` : `<div class="actions" style="margin:6px 0 0"><button class="btn sm" id="c-fill">Fill in the calculated values</button></div>`}
  </div>
  <div class="cgrid2">
    <div class="card"><h3 style="margin-top:0">Attributes</h3><div class="cstats">${o.attributes.map((a, i) => `<span>${a}</span>${show('attributes', i)}`).join('')}</div>
      <h3>Health, magicka, fatigue</h3><div class="cstats">${['health', 'magicka', 'fatigue'].map(k => `<span>${k[0].toUpperCase() + k.slice(1)}</span>${d.auto ? `<b>${c ? c[k] : '?'}</b>` : num(k, d[k], 65535)}`).join('')}</div>
      <h3>Other</h3><div class="cstats">
        <span>Level</span>${num('level', d.level, 100)}
        <span title="How much they like the player to start with (0-100)">Disposition</span>${num('disposition', d.disposition, 100)}
        <span title="How well known they are">Reputation</span>${num('reputation', d.reputation, 255)}
        <span title="What they carry; merchants also use it to buy from the player">Gold</span>${num('gold', d.gold, 999999999)}
        ${fac ? `<span>Rank in ${esc(fac.name)}</span><b>${esc(fac.ranks[d.rank] || d.rank)}</b>` : ''}</div></div>
    <div class="card"><h3 style="margin-top:0">Skills</h3><div class="cstats two">${o.skills.map((s, i) => `<span>${s}</span>${show('skills', i)}`).join('')}</div></div>
  </div>`;
  cBind(box);
  $('#c-auto').onchange = e => {
    d.auto = e.target.checked;
    if (!d.auto && !d.attributes && c){ d.attributes = c.attributes.slice(); d.skills = c.skills.slice(); d.health = c.health; d.magicka = c.magicka; d.fatigue = c.fatigue; }
    cRender();
  };
  const f = $('#c-fill'); if (f) f.onclick = () => { if (!c) return; d.attributes = c.attributes.slice(); d.skills = c.skills.slice(); d.health = c.health; d.magicka = c.magicka; d.fatigue = c.fatigue; cRender(); };
}

// ----- Behaviour: AI settings and packages
const C_AI_KINDS = {wander: 'Wander around', travel: 'Walk to a spot', follow: 'Follow someone', escort: 'Escort someone', activate: 'Use an object'};
function cAI(box){
  const d = C.data;
  box.innerHTML = `<div class="cgrid2"><div class="card"><h3 style="margin-top:0">Temper</h3>
      ${cSlider('fight', d.fight, 0, 100, 'Fight', 'How ready they are to attack. Ordinary people ~30, bandits and wild animals 80-100 (attack on sight).')}
      ${cSlider('flee', d.flee, 0, 100, 'Flee', 'How soon they run away when hurt.')}
      ${cSlider('alarm', d.alarm, 0, 100, 'Alarm', 'How likely they report crimes they see. Guards 100.')}
      ${cSlider('hello', d.hello, 0, 255, 'Hello', 'How far away (roughly) they greet a passing player. 0 = never.')}</div>
    <div class="card"><h3 style="margin-top:0">What they do</h3>
      <div class="msg" style="margin-bottom:8px">The first activity starts when the game loads them. Most people just wander a little around where they stand.</div>
      <div id="c-ailist"></div>
      <div class="actions"><select class="inp sm" id="c-aiadd"><option value="">+ Add an activity…</option>${Object.entries(C_AI_KINDS).map(([k, t]) => `<option value="${k}">${t}</option>`).join('')}</select></div></div></div>`;
  cBind(box);
  const list = $('#c-ailist');
  list.innerHTML = d.ai.map((a, n) => {
    let body = '';
    if (a.kind === 'wander'){
      body = `<div class="crow">${cField('Distance', `<input class="inp num" type="number" min="0" max="5000" data-cf="ai.${n}.distance" data-num value="${a.distance}">`, 'game units; 0 = stays put, 512 ≈ a room')}
        ${cField('For hours', `<input class="inp num" type="number" min="0" max="24" data-cf="ai.${n}.duration" data-num value="${a.duration}">`, '0 = forever')}</div>
        <details><summary class="msg">Idle animations (how often they fidget)</summary><div class="cidles">${C.opts.idles.map((nm, i) => cSlider(`ai.${n}.idle.${i}`, a.idle[i] || 0, 0, 100, nm)).join('')}</div></details>`;
    } else if (a.kind === 'travel'){
      body = `<div class="crow">${['X', 'Y', 'Z'].map((l, i) => cField(l, `<input class="inp num" type="number" data-cf="ai.${n}.p.${i}" data-num value="${Math.round(a.p[i])}">`)).join('')}</div>`;
    } else if (a.kind === 'follow' || a.kind === 'escort'){
      body = `<div class="crow">${cField(a.kind === 'follow' ? 'Follow' : 'Escort', `<input class="inp" data-cf="ai.${n}.target" value="${esc(a.target)}" placeholder="player">`, 'an NPC or creature ID, or "player"')}
        ${cField('For hours', `<input class="inp num" type="number" min="0" max="24" data-cf="ai.${n}.duration" data-num value="${a.duration}">`, '0 = until they get there')}</div>
        <div class="crow">${cField('Place (indoors)', `<input class="inp" data-cf="ai.${n}.cell" value="${esc(a.cell)}" placeholder="outdoors">`)}
        ${['X', 'Y', 'Z'].map((l, i) => cField(l, `<input class="inp num" type="number" data-cf="ai.${n}.p.${i}" data-num value="${Math.round(a.p[i])}">`)).join('')}</div>`;
    } else if (a.kind === 'activate'){
      body = cField('Object ID', `<input class="inp" data-cf="ai.${n}.target" value="${esc(a.target)}">`, 'e.g. a lever or door they go and use');
    }
    return `<div class="cai"><div class="caihead"><b>${n + 1}. ${C_AI_KINDS[a.kind] || a.kind}</b>
      <span><button class="btn sm" data-aiup="${n}" ${n ? '' : 'disabled'}>↑</button><button class="btn sm danger" data-aidel="${n}">✕</button></span></div>${body}</div>`;
  }).join('') || '<div class="msg">Nothing: they stand still.</div>';
  cBind(list);
  list.querySelectorAll('[data-aidel]').forEach(b => b.onclick = () => { d.ai.splice(+b.dataset.aidel, 1); cRender(); });
  list.querySelectorAll('[data-aiup]').forEach(b => b.onclick = () => { const n = +b.dataset.aiup; [d.ai[n - 1], d.ai[n]] = [d.ai[n], d.ai[n - 1]]; cRender(); });
  $('#c-aiadd').onchange = e => {
    const k = e.target.value; if (!k) return;
    d.ai.push(k === 'wander' ? {kind: k, distance: 512, duration: 5, idle: [60, 20, 10, 10, 0, 0, 0, 0], repeat: true}
      : k === 'activate' ? {kind: k, target: '', repeat: false} : {kind: k, p: [0, 0, 0], duration: 0, target: 'player', cell: '', repeat: false});
    cRender();
  };
}

// ----- Services and travel
function cServices(box){
  const d = C.data, o = C.opts;
  const cls = o.classes.find(c => c.id.toLowerCase() === d.cls.toLowerCase());
  const goods = o.services.slice(0, 13), other = o.services.slice(13);
  const chk = ([n, bit]) => `<label><input type="checkbox" data-svc="${bit}" ${d.services & bit ? 'checked' : ''} ${d.auto ? 'disabled' : ''}> ${esc(n)}</label>`;
  box.innerHTML = `<div class="cgrid2"><div class="card"><h3 style="margin-top:0">Trade and services</h3>
      ${d.auto ? `<div class="cnote">Characters with automatic stats offer the services of their class (${esc(cls ? cls.name : d.cls)}), not the ones ticked here.
        To choose services yourself, turn off <b>Work out stats automatically</b> on the Stats tab, or pick a class that offers them (classes ending in "Service" do).</div>` : ''}
      <h4>Buys and sells</h4><div class="cchecks grid">${goods.map(chk).join('')}</div>
      <h4>Offers</h4><div class="cchecks grid">${other.map(chk).join('')}</div>
      <div class="msg" style="margin-top:8px">Spells for sale and skills for training come from what they know and are best at (Carries & knows, Stats). Their gold is what they can pay you.</div></div>
    <div class="card"><h3 style="margin-top:0">Travel</h3>
      <div class="msg" style="margin-bottom:8px">Places this character can take the player (like silt strider caravaners, boatmen and guild guides).</div>
      <div id="c-trav"></div>
      <div class="dd" style="margin-top:8px"><input class="inp" id="c-dest" placeholder="+ Add a destination… (search places used in the game)" autocomplete="off"><div class="ddlist" id="c-dest-l"></div></div></div></div>`;
  box.querySelectorAll('[data-svc]').forEach(c => c.onchange = () => { const b = +c.dataset.svc; d.services = c.checked ? d.services | b : d.services & ~b; cChanged(); });
  const tl = $('#c-trav');
  tl.innerHTML = d.travel.map((t, n) => `<div class="drow"><span>🧭 ${esc(t.cell || 'Outdoors')} <small>${t.p.slice(0, 3).map(v => Math.round(v)).join(', ')}</small></span><button class="btn sm danger" data-trdel="${n}">✕</button></div>`).join('')
    || '<div class="msg">No destinations.</div>';
  tl.querySelectorAll('[data-trdel]').forEach(b => b.onclick = () => { d.travel.splice(+b.dataset.trdel, 1); cRender(); });
  const inp = $('#c-dest'), ll = $('#c-dest-l');
  inp.oninput = () => {
    const q = inp.value.toLowerCase().trim(); if (!q){ ll.style.display = 'none'; return; }
    const hits = o.destinations.filter(x => ((x.cell || 'outdoors') + ' ' + (x.by || '')).toLowerCase().includes(q)).slice(0, 30);
    ll.innerHTML = hits.map((x, n) => `<div data-n="${n}">${esc(x.cell || 'Outdoors ' + x.p.slice(0, 2).map(v => Math.round(v)).join(', '))}<small>used by ${esc(x.by || '?')}</small></div>`).join('') || '<div class="msg">No matches</div>';
    ll.style.display = 'block';
    ll.querySelectorAll('[data-n]').forEach(el => el.onclick = () => { const x = hits[+el.dataset.n]; d.travel.push({p: x.p.slice(), cell: x.cell}); cRender(); });
  };
  inp.onblur = () => setTimeout(() => { ll.style.display = 'none'; }, 200);
}

// ----- Carries & knows
function cItems(box){
  const d = C.data;
  box.innerHTML = `<div class="cgrid2"><div class="card"><h3 style="margin-top:0">Carries</h3>
      <div class="msg" style="margin-bottom:8px">They wear the best clothes and armor they carry and use the best weapon. For merchants, "restocks" items come back after they sell them.</div>
      <table class="t citems">${d.items.map((it, n) => `<tr class="${it.missing ? 'bad' : ''}"><td><input class="inp num" type="number" min="1" data-cf="items.${n}.count" data-num value="${it.count}"></td>
        <td>${esc(it.name || it.id)}<small>${esc(it.name ? it.id : '')}${it.missing ? ' · not found in your load order' : ''}</small></td>
        <td><label class="msg" title="Comes back after being sold"><input type="checkbox" data-cf="items.${n}.restock" ${it.restock ? 'checked' : ''}> restocks</label></td>
        <td><button class="btn sm danger" data-itdel="${n}">✕</button></td></tr>`).join('') || '<tr><td class="msg">Nothing.</td></tr>'}</table>
      <div class="dd" style="margin-top:8px"><input class="inp" id="c-additem" placeholder="+ Add an item… (search)" autocomplete="off"><div class="ddlist" id="c-additem-l"></div></div></div>
    <div class="card"><h3 style="margin-top:0">Knows these spells</h3>
      <table class="t">${d.spells.map((s, n) => `<tr class="${s.missing ? 'bad' : ''}"><td>${esc(s.name || s.id)}<small>${esc(s.name ? s.id : '')}</small></td><td><button class="btn sm danger" data-spdel="${n}">✕</button></td></tr>`).join('') || '<tr><td class="msg">None.</td></tr>'}</table>
      <div class="dd" style="margin-top:8px"><input class="inp" id="c-addspell" placeholder="+ Teach a spell… (search)" autocomplete="off"><div class="ddlist" id="c-addspell-l"></div></div>
      ${d.auto ? '<div class="msg" style="margin-top:8px">Characters with automatic stats also get spells that suit their race and class.</div>' : ''}</div></div>`;
  cBind(box);
  box.querySelectorAll('[data-itdel]').forEach(b => b.onclick = () => { d.items.splice(+b.dataset.itdel, 1); cRender(); });
  box.querySelectorAll('[data-spdel]').forEach(b => b.onclick = () => { d.spells.splice(+b.dataset.spdel, 1); cRender(); });
  ddSearch('c-additem', 'WEAP,ARMO,CLOT,MISC,BOOK,ALCH,INGR,APPA,LOCK,PROB,REPA,LIGH,LEVI', r => {
    const ex = d.items.find(x => x.id.toLowerCase() === r.id.toLowerCase());
    if (ex) ex.count++; else d.items.push({id: r.id, name: r.name, count: 1, restock: false, type: r.type});
    cRender();
  });
  ddSearch('c-addspell', 'SPEL', r => { if (!d.spells.some(x => x.id.toLowerCase() === r.id.toLowerCase())) d.spells.push({id: r.id, name: r.name}); cRender(); });
}

// ----- saving and copying
async function cSave(){
  if (!C.dirty || !await needProject()) return;
  const b = $('#c-save'); b.disabled = true; b.innerHTML = '<span class="spin"></span>Saving…';
  try {
    const r = await post('/api/npc/save', {id: C.id, data: C.data});
    C.data = r; C.orig = JSON.stringify(r); C.calc = r.calc; C.dirty = false;
    toast('Saved ' + (r.name || r.id) + '. It applies in game after a restart (or when the cell loads again).');
    cMine(); cRender(); afterChange();
  } catch (e){ toast(e.message, true); cChanged(); }
}
async function cCopy(){
  if (!await needProject()) return;
  const id = await askText('ID for the copy (players never see it):', (C.id + '_copy').slice(0, 31));
  if (!id) return;
  try {
    await post('/api/duplicate', {i: C.data.i, id});
    toast('Made a copy: ' + id); C.dirty = false; await afterChange(); cOpen(id);
  } catch (e){ toast(e.message, true); }
}
