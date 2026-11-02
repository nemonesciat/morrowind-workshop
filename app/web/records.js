// ---------- Your own skills, attributes and weathers (Create > New skill / attribute / weather; myrecords.py) ----------
// OpenMW 0.52's custom records, made as the game loads by the mod's load script: no Construction Set, no Lua.
// The user, 2026-11-01: "ease of working with new tools right away as they come out".
const RC = {data: null, kind: 'skills', sel: null, form: null};
const RC_KINDS = [['skills', 'Skills', 'skill'], ['attributes', 'Attributes', 'attribute'], ['weathers', 'Weathers', 'weather'], ['lists', 'Lists', 'list addition'],
                  ['loot', 'Loot rules', 'loot rule'], ['ingredients', 'Ingredients', 'ingredient'], ['looks', 'Look at', 'look-at line'],
                  ['traps', 'Traps', 'trap'], ['happens', 'When… then…', 'when… then…']];
const RC_DO = {raise: 'Raise a skill', give: 'Give items', bless: 'A blessing', patron: 'A patron\'s bonus', cast: 'Cast a spell', say: 'Show a line'};
// (a select of the game's skills and attributes and yours: values "s:id" / "a:id"; just skills when only='skill')
function rcStatSel(attr, val, both, only){
  const D = RC.data || {}, cap = x => x.replace(/(^|_)(\w)/g, (m, a, b) => (a ? ' ' : '') + b.toUpperCase());
  const sk = (D.skills_game || []).map(s => ['s:' + s, cap(s)]).concat((D.skills || []).map(s => ['s:' + s.id, '★ ' + s.name]));
  const at = (D.attributes_game || []).map(s => ['a:' + s, cap(s)]).concat((D.attributes || []).map(s => ['a:' + s.id, '★ ' + s.name]));
  const v = only === 'skill' && val && !val.includes(':') ? 's:' + val : val;
  const opt = list => list.map(([k_, t]) => `<option value="${esc(k_)}" ${k_.toLowerCase() === (v || '').toLowerCase() ? 'selected' : ''}>${esc(t)}</option>`).join('');
  return `<select class="inp" ${attr} style="width:auto">${both ? '<option value="">(none)</option>' : ''}${only === 'skill' ? opt(sk) : `<optgroup label="Attributes">${opt(at)}</optgroup><optgroup label="Skills">${opt(sk)}</optgroup>`}</select>`;
}
const rcStatOf = v => v ? {kind: v.startsWith('a:') ? 'attribute' : 'skill', stat: v.slice(2)} : null;
const RC_LOOT = {weapon: 'Weapons', armor: 'Armour', clothing: 'Clothing', potion: 'Potions', ingredient: 'Ingredients', book: 'Books',
                 misc: 'Odds and ends', apparatus: 'Apparatus', lockpick: 'Lockpicks', probe: 'Probes', repair: 'Repair tools', light: 'Lights'};
const RC_TIMES = {sunrise: 'Sunrise', day: 'Day', sunset: 'Sunset', night: 'Night'};
const RC_COLOURS = {skyColor: 'Sky', fogColor: 'Fog', ambientColor: 'Ambient light', sunColor: 'Sunlight'};
const RC_FIELDS = [['windSpeed', 'Wind', 'How hard the rain slants: 0 to 1'], ['cloudSpeed', 'Cloud speed', 'How fast the clouds go by'],
                   ['glareView', 'Sun glare', '0 none to 1 full'], ['cloudTexture', 'Clouds', 'A texture under Textures\\, e.g. tx_sky_stormy.dds'],
                   ['particleEffect', 'Particles', 'A mesh that falls round the player, e.g. meshes\\ashcloud.nif'],
                   ['ambientLoopSoundID', 'Sound', 'A sound that loops: type to search, e.g. Ashstorm'], ['thunderFrequency', 'Thunder', 'How often it thunders']];
const RC_FLAGS = [['isStorm', 'A storm', 'People lean into it and move slower, as in an ash storm'], ['canUseTorches', 'Torches out', 'People take out torches when it is dark'],
                  ['hasRipples', 'Ripples', 'Rain ripples on the water']];

function rcOpenKind(kind){ RC.kind = kind || 'skills'; RC.sel = null; RC.form = null; showView('myrec'); }
// (a new one already filled in: the right-click menu's "Make it a trap…", "When opened…" for the thing clicked)
function rcOpenWith(kind, form){ RC.kind = kind; RC.sel = null; RC.form = form; showView('myrec'); }
// (one of yours opened from elsewhere: Health check's "Check my mod" rows)
function rcOpenOne(kind, id){ RC.kind = kind; RC.sel = null; RC.form = null; RC.want = id; showView('myrec'); }

async function renderMyRecords(){
  const nb = document.querySelector('nav [data-view="createv"]'); if (nb) nb.classList.add('on');
  const box = $('#myrec');
  if (!S.summary || !S.summary.project){ box.innerHTML = '<div class="wrap"><h1>Skills, attributes and weathers</h1><p class="lead">Start a mod first.</p></div>'; return; }
  box.innerHTML = '<div class="msg" style="padding:30px"><span class="spin"></span>Loading…</div>';
  try { RC.data = await api('/api/myrecords'); } catch (e){ box.innerHTML = `<div class="msg err" style="padding:30px">${esc(e.message)}</div>`; return; }
  if (RC.want){ const w = RC.want; RC.want = null; if ((RC.data[RC.kind] || []).some(x => x.id === w)){ rcOpen(w); return; } }
  if (!RC.form) rcNew();
  rcDraw();
}
function rcNew(){
  RC.sel = null;
  RC.form = RC.kind === 'skills' ? {name: '', id: '', description: '', icon: '', specialization: 'combat', attribute: 'strength', gains: [1, 1, 1, 1], werewolf: 0, rises: []}
    : RC.kind === 'attributes' ? {name: '', id: '', description: '', icon: '', werewolf: 0}
    : RC.kind === 'lists' ? {id: '', add: [{id: '', level: 1}]}
    : RC.kind === 'loot' ? {name: '', what: ['weapon'], words: [], min: 0, max: 0, count: 1, chance: 100, perlevel: 0, containers: [], npcs: []}
    : RC.kind === 'ingredients' ? {id: '', effects: [{id: ''}, {id: ''}, {id: ''}, {id: ''}]}
    : RC.kind === 'looks' ? {object: '', cell: '', text: ''}
    : RC.kind === 'traps' ? {name: '', objects: [], cell: '', spell: '', once: true, text: ''}
    : RC.kind === 'happens' ? {name: '', when: 'use', ids: [], water: false, daily: false, once: false, chance: 100, by: null, miss: '', then: [{do: 'say', text: ''}]}
    : {name: '', id: '', template: 'clear', colours: {}, fields: {}, regions: []};
}
function rcOpen(id){
  const e = RC.data[RC.kind].find(x => x.id === id); if (!e) return;
  RC.sel = id; RC.form = JSON.parse(JSON.stringify(e)); rcDraw();
}
// (the template weather's own colour, from openmw.cfg: a row of yours starts from it)
const rcGame = (w, c, t) => ((((RC.data || {}).game_colours || {})[w] || {})[c] || {})[t];
const rcHex = c => typeof c === 'string' ? c : c ? '#' + c.map(v => (+v).toString(16).padStart(2, '0')).join('') : '#808080';

// an Icon box with a picture beside it and "From a picture" (iconpick.js): the game's way of naming it, under icons\
function rcIconBox(f, eg){
  const ic = (f.icon || '').trim();
  return `<div style="display:flex;gap:6px;align-items:center">${ic ? `<img src="/api/assets/thumb?path=${encodeURIComponent(ic.replace(/\\/g, '/'))}&w=32" alt="" style="width:32px;height:32px;object-fit:contain" onerror="this.style.display='none'">` : ''}
    <input class="inp" id="rc-icon" value="${esc(ic)}" placeholder="e.g. ${esc(eg)}" style="flex:1">
    <button class="btn sm" id="rc-iconpic" title="Make an icon from a picture of yours (from the Library or your PC)" style="white-space:nowrap">🖼 From a picture…</button></div>`;
}
// the game's own weathers' particles (what falls round the player), for "Particles"
const RC_PARTICLES = [['meshes\\ashcloud.nif', 'Ash (Ash storm)'], ['meshes\\blightcloud.nif', 'Blight (Blight)'], ['meshes\\snow.nif', 'Snow (Snow)'], ['meshes\\blizzard.nif', 'Driving snow (Blizzard)']];
function rcWeatherField(f, k_, h){
  const val = (f.fields || {})[k_] ?? '', ph = `${f.template}'s`;
  const box = id => `<input class="inp" data-wf="${k_}" ${id ? `id="${id}"` : ''} value="${esc(val)}" placeholder="${esc(ph)}" autocomplete="off" style="flex:1;min-width:160px">`;
  if (k_ === 'cloudTexture'){
    const cl = (RC.data || {}).game_clouds || {};
    return `<div style="display:flex;gap:6px;flex-wrap:wrap">${box()}<select class="inp" data-wfpick="${k_}" style="width:auto"><option value="">The game's…</option>${Object.entries(cl).map(([w, t]) => `<option value="${esc(t)}">${esc(w[0].toUpperCase() + w.slice(1))}'s clouds</option>`).join('')}</select></div>`;
  }
  if (k_ === 'particleEffect'){
    return `<div style="display:flex;gap:6px;flex-wrap:wrap">${box()}<select class="inp" data-wfpick="${k_}" style="width:auto"><option value="">The game's…</option>${RC_PARTICLES.map(([m, l]) => `<option value="${esc(m)}">${esc(l)}</option>`).join('')}</select>
      <button class="btn sm" data-wfmodel="${k_}" title="One of your Library's models" style="white-space:nowrap">📦 From the Library…</button></div>`;
  }
  if (k_ === 'ambientLoopSoundID') return `<div class="dd" style="display:flex">${box('rc-wfsnd')}<div class="ddlist" id="rc-wfsnd-l"></div></div>`;
  return `<input class="inp" data-wf="${k_}" value="${esc(val)}" placeholder="${esc(ph)}" style="max-width:340px">`;
}

function rcFormHtml(){
  const D = RC.data, f = RC.form, k = RC.kind;
  if (k === 'loot') return `<div class="msg" style="margin-bottom:10px">Loot picked in play from everything the player's load order has (other mods'
      too), by your rule: into the containers named the first time each is opened, onto the people named the first time each is met.</div>
    <div class="frow"><label>Name</label><input class="inp" id="rc-name" maxlength="48" value="${esc(f.name || '')}" placeholder="e.g. Daedric hoard">
      <label>Gives</label><div style="display:flex;flex-wrap:wrap;gap:4px 14px">${Object.entries(RC_LOOT).map(([v, t]) => `<label class="chk"><input type="checkbox" data-lw="${v}" ${(f.what || []).includes(v) ? 'checked' : ''}> ${t}</label>`).join('')}</div>
      <label>Words</label><div><input class="inp" id="rc-words" value="${esc((f.words || []).join(', '))}" placeholder="any of these in its ID or name, e.g. daedric, glass (empty: anything)"></div>
      <label>Worth</label><div style="display:flex;gap:6px;align-items:center"><input class="inp" type="number" min="0" id="rc-min" value="${f.min || 0}" style="width:100px"> to <input class="inp" type="number" min="0" id="rc-max" value="${f.max || 0}" style="width:100px"><span class="msg">gold (0: no limit)</span></div>
      <label>How many</label><div style="display:flex;gap:6px;align-items:center"><input class="inp" type="number" min="1" max="20" id="rc-count" value="${f.count || 1}" style="width:70px"> with a chance of <input class="inp" type="number" min="0" max="100" id="rc-chance" value="${f.chance ?? 100}" style="width:70px"> %</div>
      <label>Player's level</label><div><input class="inp" type="number" min="0" id="rc-perlevel" value="${f.perlevel || 0}" style="width:100px"><div class="hint">Gold a level: at 100, a level 10 player finds things worth up to 1000. 0: any.</div></div>
      <label>Containers</label><input class="inp" id="rc-conts" value="${esc((f.containers || []).join(', '))}" placeholder="container IDs, e.g. chest_small_01">
      <label>People</label><input class="inp" id="rc-npcs" value="${esc((f.npcs || []).join(', '))}" placeholder="NPC or creature IDs">
      <label>Glow</label><div style="display:flex;gap:6px;align-items:center"><label class="chk"><input type="checkbox" id="rc-glow" ${f.glow ? 'checked' : ''}> the containers glow until opened</label>
        <input type="color" id="rc-glowc" value="${rcHex(f.glow || [255, 214, 120])}" style="width:44px;height:26px;padding:0"><span class="msg">(OpenMW 0.52)</span></div></div>`;
  if (k === 'happens'){
    const then = f.then || [], by = f.by || {};
    const row = (a, i) => {
      const d = a.do || 'say', at = (n, p) => `data-h${n}="${i}"`;
      const amt = `<input class="inp" type="number" step="0.5" ${at('amount')} value="${a.amount ?? 5}" style="width:70px" title="How much it adds">`;
      const scale = `<span class="msg">+</span><input class="inp" type="number" step="0.05" min="0" ${at('sper')} value="${(a.scale || {}).per ?? 0}" style="width:70px" title="Added for each point of the stat beside it">
        <span class="msg">a point of</span>${rcStatSel(`data-hsstat="${i}"`, a.scale && a.scale.stat ? (a.scale.kind === 'attribute' ? 'a:' : 's:') + a.scale.stat : '', true)}`;
      const body = d === 'raise' ? `${rcStatSel(`data-hstat="${i}"`, a.stat || a.skill || '', false, 'skill')}<span class="msg">by</span><input class="inp" type="number" step="0.5" min="0" ${at('gain')} value="${a.gain ?? 1}" style="width:70px">`
        : d === 'give' ? `<div class="dd" style="flex:1;min-width:180px"><input class="inp" ${at('id')} id="rc-hid-${i}" value="${esc(a.id || '')}" placeholder="An item… (search)" title="Or * for one more of what the thing activated holds (a plant's own ingredient)" autocomplete="off"><div class="ddlist" id="rc-hid-${i}-l"></div></div>
            <span class="msg">×</span><input class="inp" type="number" min="1" max="100" ${at('count')} value="${a.count || 1}" style="width:60px">`
        : d === 'bless' || d === 'patron' ? `${rcStatSel(`data-hstat="${i}"`, (a.kind === 'attribute' ? 'a:' : 's:') + (a.stat || ''), true)}${amt}${scale}
            ${d === 'bless' ? `<span class="msg">for</span><input class="inp" type="number" min="0.1" step="1" ${at('hours')} value="${a.hours ?? 24}" style="width:60px"><span class="msg">hours</span>`
                            : `<span class="msg">one at a time of</span><input class="inp" ${at('group')} value="${esc(a.group || 'patron')}" style="width:90px" title="Picking another of this group takes this one's bonus away: one patron at a time">`}`
        : d === 'cast' ? `<div class="dd" style="flex:1;min-width:180px"><input class="inp" ${at('spell')} id="rc-hsp-${i}" value="${esc(a.spell || '')}" placeholder="A spell… (search)" autocomplete="off"><div class="ddlist" id="rc-hsp-${i}-l"></div></div>`
        : `<input class="inp" ${at('text')} value="${esc(a.text || '')}" maxlength="200" placeholder="A line on screen" style="flex:1">`;
      return `<div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-bottom:6px"><select class="inp" data-hdo="${i}" style="width:auto">${Object.entries(RC_DO).map(([v, t]) => `<option value="${v}" ${v === d ? 'selected' : ''}>${t}</option>`).join('')}</select>${body}
        <button class="btn sm" data-hdel="${i}" title="Take this out">✕</button></div>`;
    };
    return `<div class="msg" style="margin-bottom:10px">When the player does something, then something happens: the building block of a new skill's use,
      a shrine's blessing, a book that teaches. No scripting: the Workshop writes the scripts. Needs OpenMW 0.52.</div>
    <div class="frow"><label>Name</label><input class="inp" id="rc-name" maxlength="48" value="${esc(f.name || '')}" placeholder="e.g. Catch a fish">
      <label>When the player</label><div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center"><select class="inp" id="rc-when" style="width:auto">
        <option value="use" ${f.when === 'use' ? 'selected' : ''}>uses</option><option value="activate" ${f.when === 'activate' ? 'selected' : ''}>activates</option>
        <option value="read" ${f.when === 'read' ? 'selected' : ''}>reads</option></select>
        <input class="inp" id="rc-hids" value="${esc((f.ids || []).join(', '))}" placeholder="${f.when === 'read' ? 'book IDs, e.g. bk_PilgrimsPath' : f.when === 'activate' ? 'IDs, e.g. Furn_shrine_Rilm_cure_01' : 'item IDs, e.g. misc_de_fishing_pole'}" style="flex:1;min-width:240px"></div>
      <label>Only if</label><div style="display:flex;gap:4px 14px;flex-wrap:wrap;align-items:center"><label class="chk"><input type="checkbox" id="rc-water" ${f.water ? 'checked' : ''}> by water</label>
        <select class="inp" id="rc-often" style="width:auto"><option value="">every time</option><option value="daily" ${f.daily ? 'selected' : ''}>once a day for each one</option><option value="once" ${f.once ? 'selected' : ''}>once ever for each one</option></select></div>
      <label>Chance</label><div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center"><input class="inp" type="number" min="0" max="100" id="rc-hchance" value="${f.chance ?? 100}" style="width:70px"><span class="msg">% +</span>
        <input class="inp" type="number" step="0.1" min="0" id="rc-hper" value="${by.per ?? 0}" style="width:70px"><span class="msg">% a point of</span>${rcStatSel('id="rc-hby"', by.stat ? (by.kind === 'attribute' ? 'a:' : 's:') + by.stat : '', true)}</div>
      <label>Else it says</label><input class="inp" id="rc-miss" maxlength="200" value="${esc(f.miss || '')}" placeholder="when the chance doesn't come up, e.g. Nothing bites.">
      <label>Then</label><div>${then.map(row).join('')}<button class="btn sm" id="rc-hadd">+ Then…</button>
        <div class="hint">Skills rise for trying; the rest happens when the chance comes up. Blessings and patrons grow with the stat named.</div></div></div>`;
  }
  if (k === 'traps') return `<div class="msg" style="margin-bottom:10px">A spell strikes whoever opens, takes or uses a thing: a cursed chest, a door
      that burns, a book that drains the reader. With OpenMW 0.52 by the game's own rules, its area going off where the thing is.</div>
    <div class="frow"><label>Name</label><input class="inp" id="rc-name" maxlength="48" value="${esc(f.name || '')}" placeholder="e.g. Burning door">
      <label>Set off by</label><input class="inp" id="rc-objs" value="${esc((f.objects || []).join(', '))}" placeholder="IDs, e.g. chest_small_02, bk_darkestdarkness">
      <label>Only in</label><input class="inp" id="rc-cell" value="${esc(f.cell || '')}" placeholder="a place's name (empty: every copy, everywhere)">
      <label>The spell</label><div class="dd"><input class="inp" id="rc-spell" value="${esc(f.spell || '')}" placeholder="A spell… (search)" autocomplete="off" style="max-width:320px"><div class="ddlist" id="rc-spell-l"></div></div>
      <label>How often</label><label class="chk"><input type="checkbox" id="rc-once" ${f.once !== false ? 'checked' : ''}> once for each one (off: every time)</label>
      <label>It says</label><input class="inp" id="rc-text" maxlength="200" value="${esc(f.text || '')}" placeholder="e.g. A rune flares on the lid!"></div>`;
  if (k === 'ingredients'){
    const E = D.effects_all || [], ef = f.effects || [];
    return `<div class="msg" style="margin-bottom:10px">An ingredient's four effects, as the game loads: the game's, Tamriel Data's or your own, so alchemy brews them.</div>
    ${RC.sel ? '' : `<div class="radios" style="margin-bottom:8px"><label><input type="radio" name="rc-ingnew" value="0" ${f.new ? '' : 'checked'}> An ingredient that exists</label>
      <label><input type="radio" name="rc-ingnew" value="1" ${f.new ? 'checked' : ''}> A new ingredient</label></div>`}
    ${f.new && !RC.sel ? `<div class="frow"><label>Name</label><input class="inp" id="rc-iname" maxlength="31" value="${esc(f.name || '')}" placeholder="e.g. Ember Moss" style="max-width:320px">
      <label>Looks like</label><div class="dd"><input class="inp" id="rc-ilook" value="${esc(f.look || '')}" placeholder="An ingredient… (search): its model and icon, unless yours below" autocomplete="off" style="max-width:420px"><div class="ddlist" id="rc-ilook-l"></div></div>
      <label>Model</label><div style="display:flex;gap:6px"><input class="inp" id="rc-imodel" value="${esc(f.model || '')}" placeholder="the one it looks like" style="flex:1"><button class="btn sm" id="rc-imodelpic" style="white-space:nowrap" title="One of your Library's models">📦 From the Library…</button></div>
      <label>Icon</label><div style="display:flex;gap:6px"><input class="inp" id="rc-iicon" value="${esc(f.icon || '')}" placeholder="the one it looks like" style="flex:1"><button class="btn sm" id="rc-iiconpic" style="white-space:nowrap" title="Make an inventory icon from a picture of yours">🖼 From a picture…</button></div>
      <label>Weight, value</label><div style="display:flex;gap:6px;align-items:center"><input class="inp" type="number" step="0.1" min="0" id="rc-iweight" value="${f.weight ?? 0.1}" style="width:90px"><input class="inp" type="number" min="0" id="rc-ivalue" value="${f.value ?? 1}" style="width:90px"><span class="msg">gold</span></div></div>`
      : `<div class="frow"><label>Ingredient</label><input class="inp" id="rc-ing" value="${esc(f.id || '')}" placeholder="its ID, e.g. ingred_ectoplasm_01" style="max-width:320px" ${RC.sel ? 'disabled' : ''}></div>`}
    <div style="margin-top:8px">${[0, 1, 2, 3].map(i => { const e = ef[i] || {}, info = E.find(x => x.id === e.id) || {};
      return `<div style="display:flex;gap:6px;margin-bottom:5px;align-items:center"><span class="msg" style="width:60px">Effect ${i + 1}</span>
        <select class="inp" data-ie="${i}" style="max-width:300px"><option value="">(none)</option>${E.map(x => `<option value="${esc(x.id)}" ${x.id === e.id ? 'selected' : ''}>${esc(x.name)}</option>`).join('')}</select>
        ${info.attribute ? `<select class="inp" data-ia="${i}" style="width:140px">${D.attributes_game.concat(D.attributes.map(a => a.id.toLowerCase())).map(a => `<option value="${esc(a)}" ${a === e.attribute ? 'selected' : ''}>${esc(a)}</option>`).join('')}</select>` : ''}
        ${info.skill ? `<select class="inp" data-is="${i}" style="width:140px">${D.skills_game.concat(D.skills.map(s => s.id.toLowerCase())).map(s => `<option value="${esc(s)}" ${s === e.skill ? 'selected' : ''}>${esc(s)}</option>`).join('')}</select>` : ''}</div>`; }).join('')}</div>`;
  }
  if (k === 'looks') return `<div class="msg" style="margin-bottom:10px">A line shown at the bottom of the screen while the player looks at a thing:
      every copy of it, or only in one place. Stories told by what lies about.</div>
    <div class="frow"><label>The thing</label><input class="inp" id="rc-obj" value="${esc(f.object || '')}" placeholder="its ID, e.g. misc_skull00" style="max-width:320px">
      <label>Only in</label><input class="inp" id="rc-cell" value="${esc(f.cell || '')}" placeholder="a place's name, e.g. Balmora, Council Club (empty: everywhere)" style="max-width:380px">
      <label>It says</label><textarea class="inp" id="rc-text" rows="3" maxlength="300" placeholder="e.g. Scratched into the bone: 'Forgive me, Hlaren.'">${esc(f.text || '')}</textarea></div>`;
  if (k === 'lists') return `<div class="msg" style="margin-bottom:10px">Things added to one of the game's random loot or creature lists as the game
      loads. The list itself is left as it is, so what other mods add to it stays (a list your mod changes in Lists replaces it whole).</div>
    <label class="chk" style="margin-bottom:12px;display:block"><input type="checkbox" id="rc-lbs" ${D.options && D.options.lists_by_script ? 'checked' : ''}>
      The Forge adds to the game's lists this way too</label>
    <div class="frow"><label>The game's list</label><div><input class="inp" id="rc-lid" value="${esc(f.id || '')}" placeholder="its ID, e.g. random_imperial_weapon" style="max-width:320px" ${RC.sel ? 'disabled' : ''}></div></div>
    <h3 style="margin-top:14px">Added to it</h3>
    <div id="rc-adds">${(f.add || []).map((a, i) => `<div style="display:flex;gap:6px;margin-bottom:5px;align-items:center">
        <input class="inp" data-aid="${i}" value="${esc(a.id || '')}" placeholder="an item, creature or list ID" style="max-width:320px">
        from level <input class="inp" type="number" min="1" max="1000" data-alv="${i}" value="${a.level || 1}" style="width:70px">
        <button class="btn sm" data-adel="${i}">✕</button></div>`).join('')}</div>
    <div class="actions" style="margin-top:4px"><button class="btn sm" id="rc-aadd">+ Something to add</button></div>`;
  const top = `<label>Name</label><input class="inp" id="rc-name" maxlength="48" value="${esc(f.name || '')}" placeholder="${k === 'skills' ? 'e.g. Brewing' : k === 'attributes' ? 'e.g. Faith' : 'e.g. Ember Rain'}">
    <label>ID</label><div><input class="inp" id="rc-id" maxlength="32" value="${esc(f.id || '')}" placeholder="filled in from the name" style="max-width:260px"><div class="hint">Its handle in scripts.</div></div>`;
  if (k === 'attributes') return `<div class="frow">${top}
      <label>Description</label><textarea class="inp" id="rc-desc" rows="2">${esc(f.description || '')}</textarea>
      <label>Icon</label><div>${rcIconBox(f, 'icons\\k\\attribute_wilpower.dds')}<div class="hint">Left empty, it has none.</div></div>
      <label>Werewolf</label><div><input class="inp" type="number" id="rc-wolf" value="${f.werewolf || 0}" style="max-width:110px"><div class="hint">Its value while the player is a werewolf.</div></div></div>
    ${rcLinksHtml()}`;
  if (k === 'skills'){
    const atts = D.attributes_game.map(a => [a, a[0].toUpperCase() + a.slice(1)]).concat(D.attributes.map(a => [a.id, a.name + ' (yours)']));
    return `<div class="frow">${top}
      <label>Description</label><textarea class="inp" id="rc-desc" rows="2">${esc(f.description || '')}</textarea>
      <label>Icon</label><div>${rcIconBox(f, 'icons\\k\\alchemy.dds')}</div>
      <label>Kind</label><select class="inp" id="rc-spec" style="max-width:160px">${D.specializations.map(s => `<option value="${s}" ${s === f.specialization ? 'selected' : ''}>${s[0].toUpperCase() + s.slice(1)}</option>`).join('')}</select>
      <label>Governed by</label><select class="inp" id="rc-att" style="max-width:220px">${atts.map(([v, l]) => `<option value="${esc(v)}" ${v.toLowerCase() === (f.attribute || '').toLowerCase() ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select>
      <label>Skill gains</label><div><div style="display:flex;gap:6px">${[0, 1, 2, 3].map(i => `<input class="inp" type="number" step="0.1" min="0" data-gain="${i}" value="${(f.gains || [])[i] ?? 1}" style="width:70px">`).join('')}</div>
        <div class="hint">What each of its four kinds of use gives toward the next level.</div></div>
      <label>Werewolf</label><input class="inp" type="number" id="rc-wolf" value="${f.werewolf || 0}" style="max-width:110px">
      <label>Magic</label><div><label class="chk"><input type="checkbox" id="rc-school" ${f.school ? 'checked' : ''}> A school of magic</label>
        <div class="hint">Your magic effects can be of it (Magic effects &gt; School), and casting their spells trains it.</div>
        ${f.school ? `<div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-top:6px">Sounds like
          <select class="inp" id="rc-like" style="width:150px">${D.schools_game.map(x => `<option value="${x}" ${x === f.school.like ? 'selected' : ''}>${x[0].toUpperCase() + x.slice(1)}</option>`).join('')}</select>
          spells it auto-calculates <input class="inp" type="number" min="0" max="50" id="rc-autocalc" value="${f.school.autoCalcMax || 0}" style="width:64px"></div>
          <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:6px;margin-top:6px">${D.school_sounds.map(k_ => `<input class="inp" data-ssnd="${k_}" value="${esc(f.school[k_] || '')}" placeholder="${k_.replace('Sound', '')} sound">`).join('')}</div>` : ''}</div>
    </div>
    <h3 style="margin-top:16px">How it rises</h3>
    <div class="msg" style="margin-bottom:6px">Each time the player uses or activates one of these, by the gain given.</div>
    <div id="rc-rises">${(f.rises || []).map((r, i) => `<div style="display:flex;gap:6px;margin-bottom:5px;align-items:center">
        <select class="inp" data-rhow="${i}" style="width:120px"><option value="use" ${r.how === 'use' ? 'selected' : ''}>Using</option><option value="activate" ${r.how === 'activate' ? 'selected' : ''}>Activating</option></select>
        <input class="inp" data-rids="${i}" value="${esc((r.ids || []).join(', '))}" placeholder="IDs, e.g. apparatus_a_mortar_01, furn_de_keg_01">
        <input class="inp" type="number" step="0.1" min="0" data-rgain="${i}" value="${r.gain ?? 1}" style="width:70px" title="Gain">
        <button class="btn sm" data-rdel="${i}">✕</button></div>`).join('') || '<div class="msg">Nothing yet: it would only rise by training.</div>'}</div>
    <div class="actions" style="margin-top:4px"><button class="btn sm" id="rc-radd">+ A way it rises</button></div>
    <div class="frow" style="margin-top:10px"><label>Books</label><div><input class="inp" id="rc-books" value="${esc((f.books || []).join(', '))}" placeholder="book IDs, e.g. bookskill_alchemy1">
      <div class="hint">Reading one raises it, as the game's skill books do.</div></div></div>
    <h3 style="margin-top:16px">Who has it</h3>
    <div class="msg" style="margin-bottom:6px">Raised to the value when first met, never lowered. With a high enough value the game's trainers may teach it.</div>
    <div id="rc-people">${(f.people || []).map((p, i) => `<div style="display:flex;gap:6px;margin-bottom:5px;align-items:center">
        <select class="inp" data-phow="${i}" style="width:150px">${[['npc', 'The person'], ['class', 'Everyone of the class'], ['faction', 'Everyone in the faction']].map(([v, t]) => `<option value="${v}" ${v === p.how ? 'selected' : ''}>${t}</option>`).join('')}</select>
        ${p.how === 'npc' ? `<input class="inp" data-pid="${i}" value="${esc(p.id || '')}" placeholder="an NPC's ID" style="max-width:220px">`
          : `<select class="inp" data-pid="${i}" style="max-width:220px">${(p.how === 'class' ? D.classes : D.factions).map(r => `<option value="${esc(r.id)}" ${r.id.toLowerCase() === (p.id || '').toLowerCase() ? 'selected' : ''}>${esc(r.name)}</option>`).join('')}</select>`}
        at <input class="inp" type="number" min="1" max="200" data-pval="${i}" value="${p.value ?? 30}" style="width:70px">
        <button class="btn sm" data-pdel="${i}">✕</button></div>`).join('') || '<div class="msg">No one yet.</div>'}</div>
    <div class="actions" style="margin-top:4px"><button class="btn sm" id="rc-padd">+ Someone who has it</button></div>
    ${rcLinksHtml()}`;
  }
  const col = f.colours || {};
  return `<div class="frow">${top}
      <label>Starts from</label><div><select class="inp" id="rc-tpl" style="max-width:200px">${D.weathers_game.map(w => `<option value="${w}" ${w === f.template ? 'selected' : ''}>${w[0].toUpperCase() + w.slice(1)}</option>`).join('')}</select>
        <div class="hint">Everything you leave alone is this weather's.</div></div></div>
    <h3 style="margin-top:16px">Colours</h3>
    <div class="rcgrid"><span></span>${Object.values(RC_TIMES).map(t => `<b>${t}</b>`).join('')}
      ${Object.entries(RC_COLOURS).map(([c, l]) => `<label class="chk"><input type="checkbox" data-cown="${c}" ${col[c] ? 'checked' : ''}> ${l}</label>
        ${Object.keys(RC_TIMES).map(t => `<input type="color" data-col="${c}" data-t="${t}" value="${rcHex((col[c] || {})[t] || rcGame(f.template, c, t))}" ${col[c] ? '' : 'disabled'}>`).join('')}`).join('')}</div>
    <div class="hint">Ticked rows are yours; the rest are ${esc(f.template)}'s.</div>
    <h3 style="margin-top:16px">Sky and sound</h3>
    <div class="frow">${RC_FIELDS.map(([k_, l, h]) => `<label>${l}</label><div>${rcWeatherField(f, k_, h)}<div class="hint">${esc(h)}</div></div>`).join('')}
      ${RC_FLAGS.map(([k_, l, h]) => `<label>${l}</label><div><select class="inp" data-wb="${k_}" style="max-width:160px" title="${esc(h)}"><option value="">${esc(f.template)}'s</option><option value="1" ${(f.fields || {})[k_] === true ? 'selected' : ''}>Yes</option><option value="0" ${(f.fields || {})[k_] === false ? 'selected' : ''}>No</option></select></div>`).join('')}</div>
    <h3 style="margin-top:16px">Where it comes</h3>
    <div class="msg" style="margin-bottom:6px">Its share of each region's weathers, as the game's ash storms have theirs (the others made smaller). Your own magic effects can call it too.</div>
    <div id="rc-regs">${(f.regions || []).map((r, i) => `<div style="display:flex;gap:6px;margin-bottom:5px;align-items:center">
        <select class="inp" data-greg="${i}" style="max-width:280px">${D.regions.map(g => `<option value="${esc(g.id)}" ${g.id.toLowerCase() === (r.region || '').toLowerCase() ? 'selected' : ''}>${esc(g.name)}</option>`).join('')}</select>
        <input class="inp" type="number" min="0" max="100" step="0.5" data-gch="${i}" value="${r.chance ?? 10}" style="width:80px"> %
        <button class="btn sm" data-gdel="${i}">✕</button></div>`).join('') || '<div class="msg">Nowhere yet.</div>'}</div>
    <div class="actions" style="margin-top:4px"><button class="btn sm" id="rc-gadd">+ A region</button>
      <label class="chk" title="It comes only after dark (8 pm to 5 am, that chance each hour) and clears at dawn: an aurora, a ghostly mist"><input type="checkbox" id="rc-night" ${f.night ? 'checked' : ''}> Only at night</label></div>`;
}

// where a skill or attribute of yours counts: classes, factions, races (the game's or your mod's)
const RC_HOW = {skills: [['major', 'Major skill of'], ['minor', 'Minor skill of'], ['faction', 'Skill of the faction'], ['race', 'Bonus for the race']],
                attributes: [['class', 'Favoured by the class'], ['faction', 'Attribute of the faction'], ['race', 'Base value for the race']]};
function rcLinksHtml(){
  const D = RC.data, f = RC.form, k = RC.kind;
  const listOf = how => how === 'race' ? D.races : how === 'faction' ? D.factions : D.classes;
  const instead = k === 'skills' ? D.skills_game.concat(D.skills.map(x => x.id)) : D.attributes_game.concat(D.attributes.map(x => x.id));
  return `<h3 style="margin-top:16px">Where it counts</h3>
    <div class="msg" style="margin-bottom:6px">Put into the game's classes, factions and races (or your mod's) as the game loads.</div>
    <div id="rc-links">${(f.links || []).map((l, i) => `<div style="display:flex;gap:6px;margin-bottom:5px;align-items:center;flex-wrap:wrap">
        <select class="inp" data-lhow="${i}" style="width:190px">${RC_HOW[k].map(([v, t]) => `<option value="${v}" ${v === l.how ? 'selected' : ''}>${t}</option>`).join('')}</select>
        <select class="inp" data-lid="${i}" style="max-width:220px">${listOf(l.how).map(r => `<option value="${esc(r.id)}" ${r.id.toLowerCase() === (l.id || '').toLowerCase() ? 'selected' : ''}>${esc(r.name)}</option>`).join('')}</select>
        ${l.how === 'race' ? (k === 'skills' ? `+<input class="inp" type="number" min="0" max="100" data-lbonus="${i}" value="${l.bonus ?? 5}" style="width:70px" title="Bonus points">`
            : `men <input class="inp" type="number" data-lmale="${i}" value="${l.male ?? 40}" style="width:64px"> women <input class="inp" type="number" data-lfemale="${i}" value="${l.female ?? 40}" style="width:64px">`)
          : `<select class="inp" data-linst="${i}" style="width:150px" title="Take the place of one it has, or be one more"><option value="">as one more</option>${instead.map(x => `<option value="${esc(x.toLowerCase())}" ${x.toLowerCase() === (l.instead || '') ? 'selected' : ''}>in place of ${esc(x)}</option>`).join('')}</select>`}
        <button class="btn sm" data-ldel="${i}">✕</button></div>`).join('') || '<div class="msg">Nowhere yet.</div>'}</div>
    <div class="actions" style="margin-top:4px"><button class="btn sm" id="rc-ladd">+ Somewhere it counts</button></div>`;
}

function rcDraw(){
  const box = $('#myrec'), D = RC.data, k = RC.kind, one = RC_KINDS.find(x => x[0] === k)[2];
  const warn = !D.lua ? `<div class="msg warn" style="margin-bottom:10px">These are made by OpenMW Lua scripts, which a plain .esp can't carry: Save as… on My mod makes it an .omwaddon.</div>`
    : !D.ready ? `<div class="msg warn" style="margin-bottom:10px">Needs OpenMW ${D.needs} or newer; the Workshop starts ${D.openmw ? 'OpenMW ' + esc(D.openmw) : 'an OpenMW it can\'t date'}. Made now, they show once you play on ${D.needs}.</div>` : '';
  box.innerHTML = `<aside class="dside"><div class="actions" style="margin-top:0"><button class="btn sm primary" id="rc-new">+ New ${one}</button><button class="btn sm" id="rc-back">← Create</button></div>
      <div class="rctabs">${RC_KINDS.map(([kk, l]) => `<button class="btn sm ${kk === k ? 'on' : ''}" data-rctab="${kk}">${l}</button>`).join('')}</div>
      ${D[k].length ? D[k].map(e => `<div class="li ${RC.sel === e.id ? 'on' : ''}" data-rcopen="${esc(e.id)}" style="cursor:pointer;padding:6px 8px;border-radius:6px">${esc(e.name)}${((D.missing || {})[k] || {})[e.id] ? ' <span title="Something is still missing: open it to see what" style="color:#e0a040">⚠</span>' : ''}<div class="msg">${esc(e.id)}</div></div>`).join('') : `<div class="msg">None yet.</div>`}
      ${(D.examples || []).length ? `<h4 style="margin:16px 0 6px">Start from an example</h4>
        ${D.examples.map(x => `<div class="rcexrow"><button class="btn sm rcex" data-rcex="${x.key}" title="${esc(x.line)}">${x.icon} ${esc(x.name)}</button>${x.made
          ? `<button class="btn sm" data-rctry="${x.key}" title="Try it in the game: its test setup switched on, then pick where to start (${esc(x.where)})">▶</button>` : ''}</div>`).join('')}
        <div class="msg" style="margin-top:4px">Each makes everything it needs, ready to play and to change. ▶ tries it in the game.</div>` : ''}
      <div class="msg" style="margin-top:14px;line-height:1.6">${k === 'traps' ? 'Works on OpenMW 0.51 too; 0.52 adds the game\'s own spell rules.' : 'New to the game in OpenMW ' + D.needs + ': made as it loads.'}
        ${typeof guideLink === 'function' ? guideLink('openmw-052.md', 'What OpenMW 0.52 adds') : ''}</div></aside>
    <main class="dmain"><div class="wrap" style="max-width:860px">
      <h1>${RC.sel ? esc(RC.form.name || RC.sel) : 'New ' + one}</h1>${warn}
      ${RC.sel && ((D.missing || {})[k] || {})[RC.sel] ? `<div class="msg warn" style="margin-bottom:10px"><b>Still missing:</b><ul style="margin:4px 0 0 18px;padding:0">${D.missing[k][RC.sel].map(t => `<li>${esc(t)}</li>`).join('')}</ul></div>` : ''}
      ${rcFormHtml()}
      <div class="actions" style="margin-top:20px"><button class="btn primary" id="rc-save">${RC.sel ? 'Save' : 'Make the ' + one}</button>
        ${RC.sel ? '<button class="btn danger" id="rc-del">Remove it</button>' : ''}
        <button class="btn" id="rc-lua" title="The scripts the Workshop wrote for these, with what each does: to read, and learn from">📜 See the script</button><span class="msg" id="rc-msg"></span></div>
    </div></main>`;
  box.style.display = '';
  rcBind();
}

function rcKeep(){
  const f = RC.form, k = RC.kind, v = id => { const el = $('#' + id); return el ? el.value : undefined; };
  f.name = v('rc-name'); f.id = v('rc-id');
  if (k !== 'weathers'){ f.description = v('rc-desc'); f.icon = v('rc-icon'); f.werewolf = +v('rc-wolf') || 0; }
  const ids = id => (v(id) || '').split(/[\s,;]+/).filter(Boolean);
  if (k === 'loot'){
    f.name = v('rc-name'); f.what = [...document.querySelectorAll('[data-lw]')].filter(c => c.checked).map(c => c.dataset.lw);
    f.words = ids('rc-words'); f.min = +v('rc-min') || 0; f.max = +v('rc-max') || 0; f.count = +v('rc-count') || 1;
    f.chance = +v('rc-chance'); f.perlevel = +v('rc-perlevel') || 0; f.containers = ids('rc-conts'); f.npcs = ids('rc-npcs');
    f.glow = $('#rc-glow') && $('#rc-glow').checked ? v('rc-glowc') : null;
    return;
  }
  if (k === 'traps'){
    f.name = v('rc-name'); f.objects = ids('rc-objs'); f.cell = v('rc-cell'); f.spell = v('rc-spell');
    f.once = $('#rc-once').checked; f.text = v('rc-text');
    return;
  }
  if (k === 'happens'){
    f.name = v('rc-name'); f.when = v('rc-when'); f.ids = ids('rc-hids'); f.water = $('#rc-water').checked;
    const of = v('rc-often'); f.daily = of === 'daily'; f.once = of === 'once';
    f.chance = +v('rc-hchance'); f.miss = v('rc-miss');
    const b = rcStatOf(v('rc-hby')); f.by = b ? Object.assign(b, {per: +v('rc-hper') || 0}) : null;
    const g = (n, i) => document.querySelector(`[data-h${n}="${i}"]`);
    f.then = (f.then || []).map((a, i) => {
      const d = g('do', i).value, out = {do: d};
      if (d === 'raise'){ out.skill = (rcStatOf(g('stat', i).value) || {}).stat; out.gain = +g('gain', i).value || 1; }
      if (d === 'give'){ out.id = g('id', i).value.trim(); out.count = +g('count', i).value || 1; }
      if (d === 'bless' || d === 'patron'){
        Object.assign(out, rcStatOf(g('stat', i).value) || {}); out.amount = +g('amount', i).value || 0;
        const sc = rcStatOf(g('sstat', i).value); if (sc) out.scale = Object.assign(sc, {per: +g('sper', i).value || 0});
        if (d === 'bless') out.hours = +g('hours', i).value || 24; else out.group = g('group', i).value;
      }
      if (d === 'cast') out.spell = g('spell', i).value.trim();
      if (d === 'say') out.text = g('text', i).value;
      return out;
    });
    return;
  }
  if (k === 'ingredients'){
    if ($('#rc-ing')) f.id = v('rc-ing');
    if ($('#rc-iname')){ f.name = v('rc-iname'); f.look = v('rc-ilook'); f.model = v('rc-imodel'); f.icon = v('rc-iicon'); f.weight = v('rc-iweight'); f.value = v('rc-ivalue'); }
    f.effects = [0, 1, 2, 3].map(i => { const s = document.querySelector(`[data-ie="${i}"]`), a = document.querySelector(`[data-ia="${i}"]`), sk = document.querySelector(`[data-is="${i}"]`);
      const e = {id: s.value}; if (a) e.attribute = a.value; if (sk) e.skill = sk.value; return e; });
    return;
  }
  if (k === 'looks'){ f.object = v('rc-obj'); f.cell = v('rc-cell'); f.text = v('rc-text'); f.name = (f.text || '').slice(0, 40); return; }
  if (k === 'lists'){
    if ($('#rc-lid')) f.id = v('rc-lid');
    f.add = (f.add || []).map((a, i) => ({id: document.querySelector(`[data-aid="${i}"]`).value.trim(), level: +document.querySelector(`[data-alv="${i}"]`).value || 1}));
    return;
  }
  if (k !== 'weathers') f.links = (f.links || []).map((l, i) => {
    const g = s => document.querySelector(`[${s}="${i}"]`), out = {how: g('data-lhow').value, id: g('data-lid') ? g('data-lid').value : ''};
    if (g('data-linst')) out.instead = g('data-linst').value;
    if (g('data-lbonus')) out.bonus = +g('data-lbonus').value;
    if (g('data-lmale')){ out.male = +g('data-lmale').value; out.female = +g('data-lfemale').value; }
    return out;
  });
  if (k === 'skills'){
    const sc = $('#rc-school');
    if (sc && !sc.checked) f.school = null;
    else if (sc && sc.checked){
      const s_ = f.school || {like: 'mysticism'};
      if ($('#rc-like')){ s_.like = v('rc-like'); s_.autoCalcMax = +v('rc-autocalc') || 0; }
      document.querySelectorAll('[data-ssnd]').forEach(i => { s_[i.dataset.ssnd] = i.value.trim(); });
      f.school = s_;
    }
    f.specialization = v('rc-spec');
    f.books = (v('rc-books') || '').split(/[\s,;]+/).filter(Boolean);
    f.people = (f.people || []).map((p, i) => ({how: document.querySelector(`[data-phow="${i}"]`).value, id: document.querySelector(`[data-pid="${i}"]`).value.trim(),
      value: +document.querySelector(`[data-pval="${i}"]`).value || 30})); f.attribute = v('rc-att');
    f.gains = [0, 1, 2, 3].map(i => +document.querySelector(`[data-gain="${i}"]`).value || 0);
    f.rises = (f.rises || []).map((r, i) => ({how: document.querySelector(`[data-rhow="${i}"]`).value, ids: document.querySelector(`[data-rids="${i}"]`).value.split(/[\s,;]+/).filter(Boolean),
      gain: +document.querySelector(`[data-rgain="${i}"]`).value || 1}));
  }
  if (k === 'weathers'){
    f.template = v('rc-tpl');
    const cols = {};
    document.querySelectorAll('[data-cown]').forEach(c => {
      if (!c.checked) return;
      const row = {}; document.querySelectorAll(`[data-col="${c.dataset.cown}"]`).forEach(i => { row[i.dataset.t] = i.value; });
      cols[c.dataset.cown] = row;
    });
    f.colours = cols;
    const fl = {};
    document.querySelectorAll('[data-wf]').forEach(i => { if (i.value.trim() !== '') fl[i.dataset.wf] = i.value.trim(); });
    document.querySelectorAll('[data-wb]').forEach(i => { if (i.value !== '') fl[i.dataset.wb] = i.value === '1'; });
    f.fields = fl;
    f.night = !!($('#rc-night') && $('#rc-night').checked);
    f.regions = (f.regions || []).map((r, i) => ({region: document.querySelector(`[data-greg="${i}"]`).value, chance: +document.querySelector(`[data-gch="${i}"]`).value || 0}));
  }
}

// the scripts the forms wrote, read-only, each with a line on what it does: a way in to writing your own
async function rcScripts(){
  let r; try { r = await api('/api/myrecords/scripts'); } catch (e){ return toast(e.message, true); }
  if (!r.scripts.length) return toast('Nothing made yet: save one first, then its scripts are here.');
  const bg = document.createElement('div'); bg.className = 'modal-bg';
  bg.innerHTML = `<div class="modal" style="width:min(900px,94vw);max-height:88vh;display:flex;flex-direction:column"><h3 style="margin-top:0">📜 The scripts the Workshop wrote</h3>
    <div class="msg" style="margin-bottom:8px">OpenMW Lua, kept in your mod and changed for you each time you save. Read them to see how it's done; to write your own, open the Scripts page.</div>
    <div class="rctabs">${r.scripts.map((x, i) => `<button class="btn sm ${i ? '' : 'on'}" data-sct="${i}">${esc(x.name)} <span class="msg">${esc(x.kind)}</span></button>`).join('')}</div>
    <div class="msg" id="rc-swhat" style="margin:4px 0 8px"></div>
    <pre id="rc-stext" style="flex:1;overflow:auto;margin:0;padding:10px;background:var(--panel2);border:1px solid var(--line);border-radius:6px;font-size:12px;white-space:pre"></pre>
    <div class="foot"><button class="btn" id="rc-sclose">Close</button></div></div>`;
  document.body.appendChild(bg);
  const show = i => { const x = r.scripts[i]; bg.querySelector('#rc-swhat').textContent = x.what; bg.querySelector('#rc-stext').textContent = x.text;
    bg.querySelectorAll('[data-sct]').forEach(b => b.classList.toggle('on', +b.dataset.sct === i)); };
  bg.querySelectorAll('[data-sct]').forEach(b => b.onclick = () => show(+b.dataset.sct));
  const close = () => bg.remove();
  bg.querySelector('#rc-sclose').onclick = close; bg.onclick = e => { if (e.target === bg) close(); };
  show(0);
}

function rcBind(){
  const f = RC.form;
  $('#rc-new').onclick = () => { rcNew(); rcDraw(); };
  $('#rc-back').onclick = () => showView('createv');
  document.querySelectorAll('[data-rctab]').forEach(b => b.onclick = () => { RC.kind = b.dataset.rctab; rcNew(); rcDraw(); });
  document.querySelectorAll('[data-rcopen]').forEach(el => el.onclick = () => rcOpen(el.dataset.rcopen));
  const ra = $('#rc-radd'); if (ra) ra.onclick = () => { rcKeep(); f.rises = (f.rises || []).concat([{how: 'use', ids: [], gain: 1}]); rcDraw(); };
  document.querySelectorAll('[data-rdel]').forEach(b => b.onclick = () => { rcKeep(); f.rises.splice(+b.dataset.rdel, 1); rcDraw(); });
  document.querySelectorAll('[data-ie]').forEach(s => s.onchange = () => { rcKeep(); rcDraw(); });
  const ip = $('#rc-iconpic'); if (ip) ip.onclick = () => icPick('item', {name: $('#rc-name') && $('#rc-name').value, onDone: p => { rcKeep(); f.icon = 'icons' + String.fromCharCode(92) + p; rcDraw(); }});
  document.querySelectorAll('[data-wfpick]').forEach(sel => sel.onchange = () => { if (!sel.value) return; const box = document.querySelector(`[data-wf="${sel.dataset.wfpick}"]`); box.value = sel.value; sel.value = ''; });
  document.querySelectorAll('[data-wfmodel]').forEach(b => b.onclick = () => icModelPick(p => { document.querySelector(`[data-wf="${b.dataset.wfmodel}"]`).value = 'meshes' + String.fromCharCode(92) + p; }));
  if ($('#rc-wfsnd')) ddSearch('rc-wfsnd', 'SOUN', r => { $('#rc-wfsnd').value = r.id; });
  document.querySelectorAll('[name=rc-ingnew]').forEach(r => r.onchange = () => { rcKeep(); f.new = r.value === '1'; rcDraw(); });
  if ($('#rc-ilook')) ddSearch('rc-ilook', 'INGR', r => { $('#rc-ilook').value = r.id; });
  const imp = $('#rc-imodelpic'); if (imp) imp.onclick = () => icModelPick(p => { $('#rc-imodel').value = p; });
  const iip = $('#rc-iiconpic'); if (iip) iip.onclick = () => icPick('item', {name: $('#rc-iname').value, onDone: p => { $('#rc-iicon').value = p; }});
  const ha = $('#rc-hadd'); if (ha) ha.onclick = () => { rcKeep(); f.then = (f.then || []).concat([{do: 'say', text: ''}]); rcDraw(); };
  document.querySelectorAll('[data-hdel]').forEach(b => b.onclick = () => { rcKeep(); f.then.splice(+b.dataset.hdel, 1); rcDraw(); });
  document.querySelectorAll('[data-hdo]').forEach(s => s.onchange = () => { rcKeep(); f.then[+s.dataset.hdo] = {do: s.value}; rcDraw(); });
  const hw = $('#rc-when'); if (hw) hw.onchange = () => { rcKeep(); rcDraw(); };
  document.querySelectorAll('[id^="rc-hid-"]').forEach(i => { if (!i.id.endsWith('-l')) ddSearch(i.id, 'MISC,INGR,ALCH,WEAP,ARMO,CLOT,BOOK,APPA,LOCK,PROB,REPA,LIGH', r => { i.value = r.id; }); });
  document.querySelectorAll('[id^="rc-hsp-"]').forEach(i => { if (!i.id.endsWith('-l')) ddSearch(i.id, 'SPEL', r => { i.value = r.id; }); });
  if ($('#rc-spell')) ddSearch('rc-spell', 'SPEL', r => { RC.form.spell = r.id; $('#rc-spell').value = r.id; });
  const aa = $('#rc-aadd'); if (aa) aa.onclick = () => { rcKeep(); f.add = (f.add || []).concat([{id: '', level: 1}]); rcDraw(); };
  document.querySelectorAll('[data-adel]').forEach(b => b.onclick = () => { rcKeep(); f.add.splice(+b.dataset.adel, 1); rcDraw(); });
  const lbs = $('#rc-lbs'); if (lbs) lbs.onchange = async () => {
    try { RC.data = await post('/api/myrecords/option', {name: 'lists_by_script', value: lbs.checked});
      toast(lbs.checked ? 'The Forge now adds to the game\'s lists as the game loads (OpenMW 0.52).' : 'The Forge changes the game\'s lists in your mod again.'); }
    catch (e){ lbs.checked = !lbs.checked; toast(e.message, true); }
  };
  const pa = $('#rc-padd'); if (pa) pa.onclick = () => { rcKeep(); f.people = (f.people || []).concat([{how: 'npc', id: '', value: 30}]); rcDraw(); };
  document.querySelectorAll('[data-pdel]').forEach(b => b.onclick = () => { rcKeep(); f.people.splice(+b.dataset.pdel, 1); rcDraw(); });
  document.querySelectorAll('[data-phow]').forEach(b => b.onchange = () => { rcKeep(); const p = f.people[+b.dataset.phow];
    p.id = p.how === 'class' ? ((RC.data.classes[0] || {}).id || '') : p.how === 'faction' ? ((RC.data.factions[0] || {}).id || '') : ''; rcDraw(); });
  const la = $('#rc-ladd'); if (la) la.onclick = () => { rcKeep(); const how = RC_HOW[RC.kind][0][0];
    f.links = (f.links || []).concat([{how, id: ((RC.data.classes[0]) || {}).id || ''}]); rcDraw(); };
  document.querySelectorAll('[data-ldel]').forEach(b => b.onclick = () => { rcKeep(); f.links.splice(+b.dataset.ldel, 1); rcDraw(); });
  // (another kind of place: its list changes)
  document.querySelectorAll('[data-lhow]').forEach(b => b.onchange = () => { rcKeep(); const l = f.links[+b.dataset.lhow];
    const lst = l.how === 'race' ? RC.data.races : l.how === 'faction' ? RC.data.factions : RC.data.classes; l.id = (lst[0] || {}).id || ''; rcDraw(); });
  const ga = $('#rc-gadd'); if (ga) ga.onclick = () => { rcKeep(); f.regions = (f.regions || []).concat([{region: (RC.data.regions[0] || {}).id || '', chance: 10}]); rcDraw(); };
  document.querySelectorAll('[data-gdel]').forEach(b => b.onclick = () => { rcKeep(); f.regions.splice(+b.dataset.gdel, 1); rcDraw(); });
  document.querySelectorAll('[data-cown]').forEach(c => c.onchange = () => document.querySelectorAll(`[data-col="${c.dataset.cown}"]`).forEach(i => { i.disabled = !c.checked; }));
  const tp = $('#rc-tpl'); if (tp) tp.onchange = () => { rcKeep(); rcDraw(); };
  const scb = $('#rc-school'); if (scb) scb.onchange = () => { rcKeep(); rcDraw(); };
  $('#rc-lua').onclick = rcScripts;
  // ▶ Try it: the example's test setup switched on (Play here gives it), then where to start, as Play here asks
  document.querySelectorAll('[data-rctry]').forEach(b => b.onclick = async () => {
    try {
      const r = await post('/api/myrecords/try', {key: b.dataset.rctry});
      showView('world');
      setTimeout(() => { setMode('play'); setBanner(`Test setup <b>${esc(r.setup)}</b> is on. ${W.key ? 'Click where to start' : 'Open a place, then click where to start'}: ${esc(r.where)}. ${esc(r.how)} Esc to cancel.`, 'play'); }, 250);
    } catch (e){ toast(e.message, true); }
  });
  document.querySelectorAll('[data-rcex]').forEach(b => b.onclick = async () => {
    const x = RC.data.examples.find(e => e.key === b.dataset.rcex);
    if (!confirm(`Add the ${x.name} example to your mod?

${x.line}

It's yours to change; My mod's Undo it all takes it back.`)) return;
    b.disabled = true; b.innerHTML = `<span class="spin"></span>${esc(x.name)}…`;
    try {
      const r = await post('/api/myrecords/example', {key: x.key});
      RC.data = r; const [kind, id] = r.example.open;
      RC.kind = kind; RC.sel = null; RC.form = null; rcOpen(id);
      toast(`Made ${r.example.made}. ▶ beside it tries it in the game.`);
      if (typeof afterChange === 'function') await afterChange();
      rcDraw();
    } catch (e){ toast(e.message, true); b.disabled = false; b.textContent = `${x.icon} ${x.name}`; }
  });
  $('#rc-save').onclick = async () => {
    rcKeep();
    const m = $('#rc-msg');
    try {
      const r = await post('/api/myrecords/save', {kind: RC.kind, record: RC.form, old_id: RC.sel});
      toast(`${RC.sel ? 'Saved' : 'Made'} ${r.saved.name}. One Undo takes it back.`);
      RC.data = r; RC.sel = r.saved.id; RC.form = JSON.parse(JSON.stringify(r.saved));
      if (typeof afterChange === 'function') await afterChange();
      rcDraw();
    } catch (e){ m.textContent = e.message; m.className = 'msg err'; }
  };
  const del = $('#rc-del'); if (del) del.onclick = async () => {
    if (!confirm(`Remove ${f.name}? One Undo brings it back.`)) return;
    try { RC.data = await post('/api/myrecords/delete', {kind: RC.kind, id: RC.sel}); rcNew(); rcDraw(); }
    catch (e){ const m = $('#rc-msg'); m.textContent = e.message; m.className = 'msg err'; }
  };
}

(function(){
  const st = document.createElement('style');
  st.textContent = `.rctabs{display:flex;flex-wrap:wrap;gap:4px;margin:10px 0}.rctabs .btn.on{background:var(--gold);color:#111}.rcexrow{display:flex;gap:4px;margin-bottom:4px}.rcex{display:block;flex:1;text-align:left}
    .rcgrid{display:grid;grid-template-columns:150px repeat(4, 70px);gap:6px 10px;align-items:center;font-size:13px}
    .rcgrid input[type=color]{width:60px;height:26px;padding:0;border:1px solid var(--line);border-radius:5px;background:none}
    .rcgrid input[type=color]:disabled{opacity:.35}`;
  document.head.appendChild(st);
})();
