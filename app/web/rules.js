// ---------- Factions, classes, races, birthsigns, global variables and game settings ----------
const RU = {tab: 'faction', id: null, data: null, orig: null, opts: null, gq: ''};
const RU_TABS = [['faction', '🏛 Factions'], ['class', '🎓 Classes'], ['race', '🧝 Races'], ['birthsign', '✨ Birthsigns'],
  ['region', '🌦 Regions & weather'], ['global', '🌐 Global variables'], ['gmst', '⚙ Game settings']];
const RU_TYPE = {faction: 'FACT', class: 'CLAS', race: 'RACE', birthsign: 'BSGN', global: 'GLOB', region: 'REGN'};
const RU_WEATHER_ICON = ['☀️', '⛅', '🌫', '☁️', '🌧', '⛈', '🌋', '☣️', '🌨', '❄️'];
// where each kind is read and saved
const ruGetUrl = id => RU.tab === 'global' ? '/api/global?id=' + encodeURIComponent(id) : RU.tab === 'region' ? '/api/region?id=' + encodeURIComponent(id)
  : '/api/org?' + new URLSearchParams({kind: RU.tab, id});
const ruSaveUrl = () => RU.tab === 'global' ? '/api/global/save' : RU.tab === 'region' ? '/api/region/save' : '/api/org/save';
const RU_HELP = {
  faction: 'Guilds, Great Houses and other groups: ranks with what it takes to be promoted, the skills they care about, and how they feel about other factions.',
  class: 'What characters are good at. Classes ending in "Service" sell things when their characters use automatic stats.',
  race: 'Starting attributes, skill bonuses, size and built-in powers.',
  birthsign: 'The sign chosen at the start of the game and the spells or abilities it gives.',
  global: 'Numbers every script and dialogue line can read and change: quest flags, counters, choices the player made.',
  region: 'Areas of the outdoors: the weather they get, their background sounds, what attacks you when you sleep there, and their colour on the map. Paint which cells belong to one on the World map.',
  gmst: 'The game\'s own rules: prices, jump height, bounties, how fast skills rise… Change them carefully: they affect the whole game.'};

async function ruOpts(){ if (!RU.opts) RU.opts = await api('/api/org/options'); return RU.opts; }
function ruShow(tab, id){ RU.tab = tab || RU.tab; RU.id = id || null; RU.data = null; showView('rules'); }
async function renderRules(){
  try { await ruOpts(); }
  catch (e){
    // e.g. opened while the Workshop is still reading the game files
    $('#rmain').innerHTML = `<div class="msg err" style="padding:30px">Could not load the lists: ${esc(e.message)} <button class="btn sm" id="ru-retry">Try again</button></div>`;
    $('#ru-retry').onclick = () => renderRules();
    return;
  }
  if (RU.tab === 'class') await cOpts();      // (service names)
  const side = $('#rside');
  side.innerHTML = `<div class="rutabs">${RU_TABS.map(([k, t]) => `<button data-rut="${k}" class="${RU.tab === k ? 'on' : ''}">${t}</button>`).join('')}</div>
    ${RU.tab === 'gmst' ? '' : `<div class="actions"><button class="btn sm primary" id="ru-new">+ New ${RU.tab === 'global' ? 'variable' : RU.tab}</button></div>
    <div class="dd"><input class="inp" id="ru-find" placeholder="Find…" autocomplete="off"><div class="ddlist" id="ru-find-l"></div></div>`}
    <div class="msg" style="margin-top:12px;line-height:1.6">${RU_HELP[RU.tab]}</div>`;
  side.querySelectorAll('[data-rut]').forEach(b => b.onclick = () => ruShow(b.dataset.rut));
  if (RU.tab !== 'gmst'){
    ddSearch('ru-find', RU_TYPE[RU.tab], r => ruOpen(r.id));
    $('#ru-new').onclick = ruNew;
  }
  if (RU.tab === 'gmst') return ruGmst();
  if (RU.id && !RU.data) return ruOpen(RU.id);
  if (!RU.data) ruList();
}
async function ruList(){
  if (RU.tab === 'region'){
    $('#rmain').innerHTML = '<div class="msg" style="padding:30px"><span class="spin"></span>Loading…</div>';
    const r = await api('/api/regions');
    if (RU.tab !== 'region' || RU.data) return;
    $('#rmain').innerHTML = `<div class="wrap" style="max-width:900px"><h1>🌦 Regions & weather</h1><p class="lead">${RU_HELP.region}</p>
      <div class="actions" style="margin-bottom:10px"><button class="btn sm" id="ru-regmap">🗺 Show regions on the World map</button></div>
      <div class="rugrid">${r.regions.map(x => `<button class="drow" data-ruo="${esc(x.id)}"><span><i class="regsw" style="background:rgb(${x.color.join(',')})"></i>${esc(x.name)}</span><small>${x.cells} cell${x.cells === 1 ? '' : 's'}${x.mine ? ' · ✎' : ''}</small></button>`).join('')}</div></div>`;
    $('#rmain').querySelectorAll('[data-ruo]').forEach(b => b.onclick = () => ruOpen(b.dataset.ruo));
    $('#ru-regmap').onclick = () => regionsOnMap();
    return;
  }
  const o = RU.opts, list = {faction: o.factions, class: o.classes, race: o.races, birthsign: o.birthsigns}[RU.tab];
  $('#rmain').innerHTML = `<div class="wrap" style="max-width:900px"><h1>${RU_TABS.find(t => t[0] === RU.tab)[1]}</h1><p class="lead">${RU_HELP[RU.tab]}</p>
    ${list ? `<div class="rugrid">${list.map(x => `<button class="drow" data-ruo="${esc(x.id)}"><span>${esc(x.name)}</span><small>${esc(x.id !== x.name ? x.id : '')}</small></button>`).join('')}</div>`
      : '<div class="msg">Find one on the left, or make a new one.</div>'}</div>`;
  $('#rmain').querySelectorAll('[data-ruo]').forEach(b => b.onclick = () => ruOpen(b.dataset.ruo));
}
async function ruOpen(id){
  if (RU.data && JSON.stringify(RU.data) !== RU.orig && !confirm('Leave your unsaved changes?')) return;
  if (!$('#rules').classList.contains('on')){ RU.id = id; RU.data = null; showView('rules'); return; }
  $('#rmain').innerHTML = '<div class="msg" style="padding:30px"><span class="spin"></span>Loading…</div>';
  try { RU.data = await api(ruGetUrl(id)); }
  catch (e){ $('#rmain').innerHTML = `<div class="msg err" style="padding:30px">${esc(e.message)}</div>`; return; }
  RU.id = RU.data.id; RU.orig = JSON.stringify(RU.data); ruRender();
}
async function ruNew(){
  if (!await needProject()) return;
  const what = RU.tab === 'global' ? 'variable' : RU.tab;
  const prefix = (S.summary && S.summary.project ? S.summary.project.name : 'mod').replace(/[^A-Za-z0-9]/g, '').slice(0, 8);
  const id = prompt(`ID for the new ${what} (players never see it):`, prefix + '_'); if (!id) return;
  let data;
  if (RU.tab === 'global') data = {type: 's', value: 0};
  else {
    const from = prompt(`Start from an existing ${what}? Type its ID, or leave empty to start from scratch.`, '');
    if (from){ try { data = await api(ruGetUrl(from)); } catch (e){ return toast(e.message, true); } data.name = (data.name || data.id).slice(0, 24) + ' (new)'; }
    else if (RU.tab === 'region') data = {name: id, weather: [40, 30, 10, 10, 10, 0, 0, 0, 0, 0], color: [120, 160, 90], sleep: '', sounds: []};
    else data = {faction: {name: 'New faction', ranks: ['Member'], rank_req: [], attributes: [0, 1], skills: [], reactions: []},
      class: {name: 'New class', spec: 0, attributes: [0, 5], major: [0, 1, 2, 3, 4], minor: [5, 6, 7, 8, 9], playable: true, services: 0},
      race: {name: 'New race', bonuses: [], male: [40, 40, 40, 40, 40, 40, 40, 40], female: [40, 40, 40, 40, 40, 40, 40, 40], height: [1, 1], weight: [1, 1], playable: false, spells: []},
      birthsign: {name: 'New sign', desc: '', spells: []}}[RU.tab];
  }
  try {
    await post(ruSaveUrl(), {kind: RU.tab, id, data, create: true});
    toast('Created ' + id); RU.opts = null; await ruOpts(); afterChange(); RU.data = null; ruOpen(id);
  } catch (e){ toast(e.message, true); }
}

// ----- the editors
function ruSel(path, list, cur, extra){ return `<select class="inp" data-rf="${path}" data-num ${extra || ''}>${list.map((x, n) => `<option value="${n}" ${n === cur ? 'selected' : ''}>${esc(x)}</option>`).join('')}</select>`; }
function ruRender(){
  const d = RU.data, o = RU.opts, k = RU.tab;
  let body = '';
  if (k === 'faction'){
    body = `<div class="cgrid2"><div class="card">
        ${cField('Name', `<input class="inp" data-rf="name" value="${esc(d.name)}">`)}
        <div class="crow">${cField('Favoured attribute', ruSel('attributes.0', o.attributes, d.attributes[0]))}${cField('and', ruSel('attributes.1', o.attributes, d.attributes[1]))}</div>
        <label class="cfield"><span>Skills the faction cares about (up to 7)</span><div class="ruchips">${o.skills.map((s, n) => `<label class="${d.skills.includes(n) ? 'on' : ''}"><input type="checkbox" data-fskill="${n}" ${d.skills.includes(n) ? 'checked' : ''}> ${s}</label>`).join('')}</div>
          <small>Rank requirements below refer to these skills.</small></label>
        <label class="msg plrow" title="Players never see it in their stats (used for groups like the Sixth House)"><input type="checkbox" data-rf="hidden" ${d.hidden ? 'checked' : ''}> Hidden from the player</label>
        ${d.members.length ? `<div class="cplaced"><b>Members:</b> ${d.members.slice(0, 30).map(m => `<a href="#" data-rumem="${esc(m.id)}">${esc(m.name || m.id)}</a>`).join(' · ')}${d.members.length >= 60 ? ' …' : ''}</div>` : ''}</div>
      <div class="card"><h3 style="margin-top:0">How it feels about others</h3>
        <div class="msg" style="margin-bottom:6px">Positive: members like people from that faction (better disposition); negative: they dislike them.</div>
        <table class="t">${d.reactions.map((r, n) => `<tr><td>${esc(r.faction)}</td><td><input class="inp num" type="number" data-rf="reactions.${n}.value" data-num value="${r.value}"></td><td><button class="btn sm danger" data-rureac="${n}">✕</button></td></tr>`).join('')}</table>
        <div class="dd" style="margin-top:6px"><input class="inp" id="ru-addreac" placeholder="+ Add a faction… (search)" autocomplete="off"><div class="ddlist" id="ru-addreac-l"></div></div></div></div>
      <div class="card" style="margin-top:14px"><h3 style="margin-top:0">Ranks</h3>
        <div class="msg" style="margin-bottom:6px">To be promoted to a rank, a member needs both favoured attributes at the first two numbers, one favoured skill at the third and another at the fourth, and that much reputation in the faction.</div>
        <table class="t rurank"><tr><th>#</th><th>Rank name</th><th>${esc(o.attributes[d.attributes[0]])}</th><th>${esc(o.attributes[d.attributes[1]])}</th><th>1 skill at</th><th>2nd skill at</th><th>Reputation</th><th></th></tr>
        ${d.ranks.map((r, n) => `<tr><td>${n}</td><td><input class="inp" data-rf="ranks.${n}" value="${esc(r)}" maxlength="31"></td>
          ${['attr1', 'attr2', 'skill1', 'skill2', 'rep'].map(f => `<td><input class="inp num" type="number" data-rf="rank_req.${n}.${f}" data-num value="${d.rank_req[n][f]}" style="width:66px"></td>`).join('')}
          <td>${n === d.ranks.length - 1 && n > 0 ? `<button class="btn sm danger" id="ru-droprank">✕</button>` : ''}</td></tr>`).join('')}</table>
        ${d.ranks.length < 10 ? '<button class="btn sm" id="ru-addrank">+ Add a rank</button>' : ''}</div>`;
  } else if (k === 'class'){
    const skillPick = (path, cur) => `<select class="inp" data-rf="${path}" data-num>${o.skills.map((s, n) => `<option value="${n}" ${n === cur ? 'selected' : ''}>${s}</option>`).join('')}</select>`;
    body = `<div class="cgrid2"><div class="card">
        ${cField('Name', `<input class="inp" data-rf="name" value="${esc(d.name)}">`)}
        ${cField('Description', `<textarea class="inp" data-rf="desc" rows="3">${esc(d.desc)}</textarea>`, 'Shown when the player picks a class.')}
        <div class="crow">${cField('Specialization', ruSel('spec', o.specs, d.spec), 'Skills of this kind rise faster.')}
          ${cField('Favoured attributes', ruSel('attributes.0', o.attributes, d.attributes[0]))}${cField('&nbsp;', ruSel('attributes.1', o.attributes, d.attributes[1]))}</div>
        <label class="msg plrow"><input type="checkbox" data-rf="playable" ${d.playable ? 'checked' : ''}> Players can pick it</label></div>
      <div class="card"><div class="crow"><div style="flex:1"><h3 style="margin-top:0">Major skills</h3>${d.major.map((s, n) => skillPick('major.' + n, s)).join('')}</div>
        <div style="flex:1"><h3 style="margin-top:0">Minor skills</h3>${d.minor.map((s, n) => skillPick('minor.' + n, s)).join('')}</div></div></div>
      <div class="card"><h3 style="margin-top:0">Services (for characters with automatic stats)</h3>
        <div class="msg" style="margin-bottom:6px">${d.playable ? 'Classes players can pick never offer services; untick "Players can pick it" to use these.' : 'Characters of this class whose stats are worked out automatically offer these.'}</div>
        <div class="cchecks grid">${(C.opts ? C.opts.services : []).map(([nm, bit]) => `<label><input type="checkbox" data-rsvc="${bit}" ${d.services & bit ? 'checked' : ''}> ${esc(nm)}</label>`).join('') || '<span class="msg">Open the Characters page once to load the service names.</span>'}</div></div></div>`;
  } else if (k === 'race'){
    body = `<div class="cgrid2"><div class="card">
        ${cField('Name', `<input class="inp" data-rf="name" value="${esc(d.name)}">`)}
        ${cField('Description', `<textarea class="inp" data-rf="desc" rows="3">${esc(d.desc)}</textarea>`)}
        <div class="cchecks"><label><input type="checkbox" data-rf="playable" ${d.playable ? 'checked' : ''}> Players can pick it</label>
          <label title="Like Argonians and Khajiit: no shoes or closed helmets"><input type="checkbox" data-rf="beast" ${d.beast ? 'checked' : ''}> Beast race</label></div>
        <div class="crow">${cField('Height (men)', `<input class="inp num" type="number" step="0.01" data-rf="height.0" data-num value="${d.height[0]}">`)}${cField('(women)', `<input class="inp num" type="number" step="0.01" data-rf="height.1" data-num value="${d.height[1]}">`)}
          ${cField('Build (men)', `<input class="inp num" type="number" step="0.01" data-rf="weight.0" data-num value="${d.weight[0]}">`)}${cField('(women)', `<input class="inp num" type="number" step="0.01" data-rf="weight.1" data-num value="${d.weight[1]}">`)}</div>
        <h3>Powers and abilities</h3>${ruSpells(d)}</div>
      <div class="card"><h3 style="margin-top:0">Starting attributes</h3><table class="t"><tr><th></th><th>Men</th><th>Women</th></tr>
        ${o.attributes.map((a, n) => `<tr><td>${a}</td><td><input class="inp num" type="number" data-rf="male.${n}" data-num value="${d.male[n]}"></td><td><input class="inp num" type="number" data-rf="female.${n}" data-num value="${d.female[n]}"></td></tr>`).join('')}</table>
        <h3>Skill bonuses (up to 7)</h3><table class="t">${d.bonuses.map((b, n) => `<tr><td><select class="inp" data-rf="bonuses.${n}.skill" data-num>${o.skills.map((s, i) => `<option value="${i}" ${i === b.skill ? 'selected' : ''}>${s}</option>`).join('')}</select></td>
          <td><input class="inp num" type="number" data-rf="bonuses.${n}.bonus" data-num value="${b.bonus}"></td><td><button class="btn sm danger" data-rubon="${n}">✕</button></td></tr>`).join('')}</table>
        ${d.bonuses.length < 7 ? '<button class="btn sm" id="ru-addbon">+ Add a bonus</button>' : ''}</div></div>`;
  } else if (k === 'birthsign'){
    body = `<div class="cgrid2"><div class="card">${cField('Name', `<input class="inp" data-rf="name" value="${esc(d.name)}">`)}
      ${cField('Description', `<textarea class="inp" data-rf="desc" rows="3">${esc(d.desc)}</textarea>`)}
      ${cField('Constellation picture', `<input class="inp" data-rf="picture" value="${esc(d.picture)}">`, 'A texture file, e.g. birthsigns\\atronach.tga')}</div>
      <div class="card"><h3 style="margin-top:0">Spells and abilities it gives</h3>${ruSpells(d)}</div></div>`;
  } else if (k === 'region'){
    const names = ['Clear', 'Cloudy', 'Foggy', 'Overcast', 'Rain', 'Thunderstorm', 'Ash storm', 'Blight', 'Snow', 'Blizzard'];
    const total = d.weather.reduce((a, b) => a + (+b || 0), 0);
    const hex = '#' + d.color.map(v => (+v).toString(16).padStart(2, '0')).join('');
    body = `<div class="cgrid2"><div class="card">
        ${cField('Name', `<input class="inp" data-rf="name" value="${esc(d.name)}" maxlength="31">`, 'Shown when the player walks into the region.')}
        ${cField('Colour on the map', `<input type="color" id="ru-regcol" value="${hex}" style="width:80px;height:34px;padding:0;border:0;background:none">`)}
        ${cField('Sleep encounters', `<div class="dd"><input class="inp" id="ru-sleep" value="${esc(d.sleep)}" placeholder="A leveled creature list… (search)" autocomplete="off"><div class="ddlist" id="ru-sleep-l"></div></div>`,
          'What may attack when the player sleeps outdoors here. Leave empty for nothing.')}
        <div class="cplaced"><b>${d.cells.length}</b> outdoor cell${d.cells.length === 1 ? '' : 's'} belong to it.
          <button class="btn sm" id="ru-regpaint">🖌 Paint cells on the World map</button></div></div>
      <div class="card"><h3 style="margin-top:0">Weather</h3>
        <div class="regbar">${d.weather.map((v, n) => v ? `<span style="flex:${v};background:${['#e8c860', '#a8b8c8', '#c8c8c0', '#8890a0', '#5878a8', '#384868', '#a05030', '#a04050', '#e8f0f8', '#c0d8f0'][n]}" title="${names[n]} ${v}%"></span>` : '').join('')}</div>
        <table class="t regw">${names.map((nm, n) => `<tr><td>${RU_WEATHER_ICON[n]} ${nm}${n >= 8 ? ' <small style="color:var(--faint)">(Bloodmoon)</small>' : ''}</td>
          <td><input type="range" min="0" max="100" data-regw="${n}" value="${d.weather[n]}"></td>
          <td><input class="inp num" type="number" min="0" max="100" data-regwn="${n}" value="${d.weather[n]}" style="width:64px">%</td></tr>`).join('')}</table>
        <div class="msg ${total === 100 ? '' : 'err'}" id="ru-wtotal">Adds up to ${total}%${total === 100 ? ' ✓' : ' — it must be exactly 100%.'}
          ${total !== 100 && total > 0 ? '<button class="btn sm" id="ru-wfix">Make it 100%</button>' : ''}</div></div></div>
      <div class="card" style="margin-top:14px"><h3 style="margin-top:0">Background sounds</h3>
        <div class="msg" style="margin-bottom:6px">Each sound plays now and then outdoors in the region; the number is its chance (higher plays more often). Up to 32.</div>
        <table class="t">${d.sounds.map((s, n) => `<tr><td><button class="btn sm" data-regplay="${esc(s.id)}" title="Listen">▶</button> ${esc(s.id)}</td>
          <td><input class="inp num" type="number" min="0" max="100" data-rf="sounds.${n}.chance" data-num value="${s.chance}" style="width:70px"></td>
          <td><button class="btn sm danger" data-regsnd="${n}">✕</button></td></tr>`).join('') || '<tr><td class="msg">None: the region is silent.</td></tr>'}</table>
        ${d.sounds.length < 32 ? '<div class="dd" style="margin-top:6px"><input class="inp" id="ru-addsnd" placeholder="+ Add a sound… (search, e.g. wind, howl, rocks)" autocomplete="off"><div class="ddlist" id="ru-addsnd-l"></div></div>' : ''}</div>`;
  } else if (k === 'global'){
    body = `<div class="card" style="max-width:620px">
      <div class="crow">${cField('Kind', `<select class="inp" data-rf="type">${Object.entries({s: 'Whole number (short)', l: 'Whole number (long)', f: 'Decimal number (float)'}).map(([v, t]) => `<option value="${v}" ${v === d.type ? 'selected' : ''}>${t}</option>`).join('')}</select>`)}
        ${cField('Starting value', `<input class="inp" type="number" step="${d.type === 'f' ? 'any' : '1'}" data-rf="value" data-num value="${d.value}">`, 'What it holds when a new game starts.')}</div>
      <div class="msg" style="line-height:1.6">In scripts: <code>set ${esc(d.id)} to 1</code> and <code>if ( ${esc(d.id)} == 1 )</code>. In dialogue: the condition "Global variable".</div>
      <h3>Used by</h3>${d.used_by.length ? d.used_by.map(u => `<div class="drow"><span>${u.kind === 'script' ? '📝' : '💬'} ${esc(u.id)}</span><button class="btn sm" data-ruuse="${u.kind}" data-ruid="${esc(u.id)}">Open</button></div>`).join('') : '<div class="msg">Nothing mentions it yet.</div>'}</div>`;
  }
  $('#rmain').innerHTML = `<div class="wrap cwrap"><div class="chead"><div><h1 style="margin:0">${esc(d.name || d.id)}</h1>
      <div class="msg">${esc(d.id)} · ${d.mine ? (d.created ? 'made in your mod' : 'changed in your mod') : 'from ' + esc(d.src) + '. Saving puts your version in your mod.'}</div></div>
      <div class="chbtns"><button class="btn sm" id="ru-back">← All</button><button class="btn sm" id="ru-revert" style="visibility:hidden">↺ Undo edits</button><button class="btn primary" id="ru-save" disabled>Saved</button></div></div>${body}</div>`;
  ruBind();
}
function ruSpells(d){
  return `<table class="t">${d.spells.map((s, n) => `<tr class="${s.missing ? 'bad' : ''}"><td>${esc(s.name || s.id)}<small style="display:block;color:var(--faint)">${esc(s.name ? s.id : '')}</small></td><td><button class="btn sm danger" data-ruspell="${n}">✕</button></td></tr>`).join('') || '<tr><td class="msg">None.</td></tr>'}</table>
    <div class="dd" style="margin-top:6px"><input class="inp" id="ru-addspell" placeholder="+ Add a spell, power or ability… (search)" autocomplete="off"><div class="ddlist" id="ru-addspell-l"></div></div>`;
}
function ruDirty(){ const x = JSON.stringify(RU.data) !== RU.orig, b = $('#ru-save'); if (!b) return; b.disabled = !x; b.textContent = x ? '💾 Save' : 'Saved'; $('#ru-revert').style.visibility = x ? 'visible' : 'hidden'; }
function ruBind(){
  const d = RU.data, box = $('#rmain');
  box.querySelectorAll('[data-rf]').forEach(el => {
    el.addEventListener(el.type === 'checkbox' || el.tagName === 'SELECT' ? 'change' : 'input', () => {
      const p = el.dataset.rf.split('.'); let o = d; for (let i = 0; i < p.length - 1; i++) o = o[p[i]];
      o[p[p.length - 1]] = el.type === 'checkbox' ? el.checked : el.dataset.num !== undefined ? (el.value === '' ? 0 : +el.value) : el.value;
      if (el.tagName === 'SELECT' && (p[0] === 'attributes' || p[0] === 'type')) ruRender(); else ruDirty();
    });
  });
  box.querySelectorAll('[data-fskill]').forEach(c => c.onchange = () => {
    const n = +c.dataset.fskill;
    if (c.checked){ if (d.skills.length >= 7){ c.checked = false; return toast('A faction cares about at most 7 skills.', true); } d.skills.push(n); }
    else d.skills = d.skills.filter(x => x !== n);
    ruRender();
  });
  box.querySelectorAll('[data-rureac]').forEach(b => b.onclick = () => { d.reactions.splice(+b.dataset.rureac, 1); ruRender(); });
  box.querySelectorAll('[data-rubon]').forEach(b => b.onclick = () => { d.bonuses.splice(+b.dataset.rubon, 1); ruRender(); });
  box.querySelectorAll('[data-ruspell]').forEach(b => b.onclick = () => { d.spells.splice(+b.dataset.ruspell, 1); ruRender(); });
  box.querySelectorAll('[data-rsvc]').forEach(c => c.onchange = () => { const b = +c.dataset.rsvc; d.services = c.checked ? d.services | b : d.services & ~b; ruDirty(); });
  box.querySelectorAll('[data-rumem]').forEach(a => a.onclick = e => { e.preventDefault(); cOpen(a.dataset.rumem); });
  box.querySelectorAll('[data-ruuse]').forEach(b => b.onclick = () => { if (b.dataset.ruuse === 'script') sOpen(b.dataset.ruid); else { showView('dialog'); } });
  const ar = $('#ru-addrank'); if (ar) ar.onclick = () => { d.ranks.push('New rank'); ruRender(); };
  const dr = $('#ru-droprank'); if (dr) dr.onclick = () => { d.ranks.pop(); ruRender(); };
  const ab = $('#ru-addbon'); if (ab) ab.onclick = () => { d.bonuses.push({skill: 0, bonus: 5}); ruRender(); };
  if ($('#ru-addreac')) ddSearch('ru-addreac', 'FACT', r => { if (!d.reactions.some(x => x.faction.toLowerCase() === r.id.toLowerCase())) d.reactions.push({faction: r.id, value: 0}); ruRender(); });
  if ($('#ru-addspell')) ddSearch('ru-addspell', 'SPEL', r => { if (!d.spells.some(x => x.id.toLowerCase() === r.id.toLowerCase())) d.spells.push({id: r.id, name: r.name}); ruRender(); });
  // regions: weather sliders and numbers move together, the total is checked as you go
  const wTotal = () => {
    const t = d.weather.reduce((a, b) => a + (+b || 0), 0), el = $('#ru-wtotal'); if (!el) return;
    el.className = 'msg' + (t === 100 ? '' : ' err');
    el.innerHTML = `Adds up to ${t}%${t === 100 ? ' ✓' : ' — it must be exactly 100%.'} ${t !== 100 && t > 0 ? '<button class="btn sm" id="ru-wfix">Make it 100%</button>' : ''}`;
    const fx = $('#ru-wfix'); if (fx) fx.onclick = wFix;
    const sv = $('#ru-save'); if (sv && t !== 100){ sv.disabled = true; sv.textContent = 'Weather ≠ 100%'; }
  };
  const wFix = () => {
    const t = d.weather.reduce((a, b) => a + b, 0); if (!t) return;
    let w = d.weather.map(v => Math.floor(v * 100 / t)), left = 100 - w.reduce((a, b) => a + b, 0);
    const order = d.weather.map((v, n) => [v * 100 / t - w[n], n]).sort((a, b) => b[0] - a[0]);
    for (let i = 0; left > 0; i++, left--) w[order[i % 10][1]]++;
    d.weather = w; ruRender();
  };
  box.querySelectorAll('[data-regw]').forEach(el => el.oninput = () => {
    const n = +el.dataset.regw; d.weather[n] = +el.value; box.querySelector(`[data-regwn="${n}"]`).value = el.value; ruDirty(); wTotal();
  });
  box.querySelectorAll('[data-regw]').forEach(el => el.onchange = () => ruRender());
  box.querySelectorAll('[data-regwn]').forEach(el => el.onchange = () => { d.weather[+el.dataset.regwn] = Math.max(0, Math.min(100, Math.round(+el.value || 0))); ruRender(); });
  const fx = $('#ru-wfix'); if (fx) fx.onclick = wFix;
  const rc = $('#ru-regcol'); if (rc) rc.oninput = () => { const v = rc.value; d.color = [1, 3, 5].map(i => parseInt(v.slice(i, i + 2), 16)); ruDirty(); };
  if ($('#ru-sleep')){
    ddSearch('ru-sleep', 'LEVC', r => { d.sleep = r.id; $('#ru-sleep').value = r.id; ruDirty(); });
    $('#ru-sleep').addEventListener('change', () => { d.sleep = $('#ru-sleep').value.trim(); ruDirty(); });
  }
  if ($('#ru-addsnd')) ddSearch('ru-addsnd', 'SOUN', r => { if (!d.sounds.some(s => s.id.toLowerCase() === r.id.toLowerCase())) d.sounds.push({id: r.id, chance: 5}); ruRender(); });
  box.querySelectorAll('[data-regsnd]').forEach(b => b.onclick = () => { d.sounds.splice(+b.dataset.regsnd, 1); ruRender(); });
  box.querySelectorAll('[data-regplay]').forEach(b => b.onclick = () => {
    if (RU.audio) RU.audio.pause();
    RU.audio = new Audio('/api/sound?id=' + encodeURIComponent(b.dataset.regplay));
    RU.audio.play().catch(() => toast('Could not play that sound (its file may be missing).', true));
  });
  const rp = $('#ru-regpaint'); if (rp) rp.onclick = () => regionsOnMap(d.id);
  $('#ru-back').onclick = () => { RU.data = null; RU.id = null; ruList(); };
  $('#ru-revert').onclick = () => { RU.data = JSON.parse(RU.orig); ruRender(); };
  $('#ru-save').onclick = async () => {
    if (!await needProject()) return;
    try {
      const r = await post(ruSaveUrl(), {kind: RU.tab, id: RU.id, data: RU.data});
      RU.data = r; RU.orig = JSON.stringify(r); toast('Saved ' + (r.name || r.id)); afterChange(); RU.opts = null; await ruOpts(); ruRender();
    } catch (e){ toast(e.message, true); }
  };
  ruDirty();
  if (RU.tab === 'region') wTotal();
}

// ----- game settings: a searchable list, edited in place
async function ruGmst(){
  const m = $('#rmain');
  m.innerHTML = `<div class="wrap" style="max-width:980px"><h1>⚙ Game settings</h1><p class="lead">${RU_HELP.gmst}</p>
    <input class="inp" id="ru-gq" placeholder="Search… (e.g. jump, barter, crime, travel)" value="${esc(RU.gq)}" style="max-width:420px">
    <div id="ru-glist" style="margin-top:10px"><span class="spin"></span></div></div>`;
  let t; $('#ru-gq').oninput = e => { clearTimeout(t); t = setTimeout(() => { RU.gq = e.target.value; RU.goff = 0; ruGmstList(); }, 250); };
  ruGmstList();
}
const RU_PAGE = 200;
async function ruGmstList(){
  const box = $('#ru-glist'); if (!box) return;
  const all = RU.gall, off = all ? 0 : (RU.goff || 0);
  const r = await api('/api/gmst?' + new URLSearchParams({q: RU.gq || '', offset: off, limit: all ? 0 : RU_PAGE}));
  RU.goff = r.offset;
  const end = r.offset + r.rows.length;
  // ‹ Previous · 201–400 of 1,808 · Next › · Show all
  const pager = r.total <= RU_PAGE ? '' : `<div class="rupager">
      <button class="btn sm" data-rupg="prev" ${all || r.offset === 0 ? 'disabled' : ''}>‹ Previous ${RU_PAGE}</button>
      <span>${fmtN(r.offset + 1)}–${fmtN(end)} of ${fmtN(r.total)}</span>
      <button class="btn sm" data-rupg="next" ${all || end >= r.total ? 'disabled' : ''}>Next ${RU_PAGE} ›</button>
      <button class="btn sm" data-rupg="all">${all ? 'Show in pages' : 'Show all'}</button></div>`;
  box.innerHTML = `<div class="msg" style="margin-bottom:6px">${fmtN(r.total)} setting${r.total === 1 ? '' : 's'}. The ones people change most come first, then other numbers, then the game's words.
      <br>* The Workshop's best guess from how the game uses it, not checked in play.</div>${pager}
    <table class="t">${r.rows.map((g, n) => `<tr class="${g.mine ? 'mine' : ''}"><td><b>${esc(g.id)}</b>${g.help ? `<small style="display:block;color:var(--muted)">${g.sure ? '' : '* '}${esc(g.help)}</small>` : ''}</td>
      <td style="width:240px">${g.type === 's' ? `<input class="inp" data-gm="${n}" value="${esc(g.value)}">` : `<input class="inp num" type="number" step="${g.type === 'f' ? 'any' : '1'}" data-gm="${n}" value="${g.value}" style="width:120px">`}
        ${g.mine ? `<small style="display:block;color:var(--faint)">✎ changed in your mod${g.original != null ? ' (was ' + esc(g.original) + ')' : ''}</small>` : ''}</td></tr>`).join('')}</table>${pager}`;
  box.querySelectorAll('[data-rupg]').forEach(b => b.onclick = () => {
    const a = b.dataset.rupg;
    if (a === 'all') RU.gall = !RU.gall;
    else RU.goff = Math.max(0, (RU.goff || 0) + (a === 'next' ? RU_PAGE : -RU_PAGE));
    ruGmstList().then(() => { const w = $('#ru-glist'); if (w) w.scrollIntoView({block: 'start'}); });
  });
  box.querySelectorAll('[data-gm]').forEach(inp => inp.onchange = async () => {
    if (!await needProject()) return;
    const g = r.rows[+inp.dataset.gm];
    try { await post('/api/gmst/save', {id: g.id, value: inp.value}); toast(`${g.id} = ${inp.value}`); afterChange(); ruGmstList(); }
    catch (e){ toast(e.message, true); }
  });
}
