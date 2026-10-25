// ---------- Give spells to people: everyone who fits, by what they are and where they stand (spellgive.py) ----------
// Pick the spells, then who: race, class, faction, a spell they know, a skill, spell sellers, and regions or
// towns. The list on the right shows who fits and what each would learn. Give them in each person's record
// (simple, but every one becomes an override in your mod), or by a small Lua script that teaches them as
// they come near (no overrides, works beside any mod; needs an .omwaddon). Each giving is one Undo.
const SG = {bg: null, opts: null, spells: [], f: {}, mode: 'records', seq: 0, t: null};

async function sgShow(start){
  if (SG.bg) SG.bg.remove();
  const bg = document.createElement('div'); bg.className = 'modal-bg'; SG.bg = bg;
  bg.innerHTML = `<div class="modal sg-win"><h2>🪄 Give spells to people</h2><div id="sg-body"><div class="msg"><span class="spin"></span>Reading everyone in the game…</div></div>
    <div class="foot"><span class="msg" id="sg-msg" style="flex:1"></span><button class="btn" id="sg-close">Close</button><button class="btn primary" id="sg-go" disabled>🪄 Give</button></div></div>`;
  document.body.appendChild(bg);
  sgCss();
  bg.querySelector('#sg-close').onclick = () => { bg.remove(); SG.bg = null; };
  bg.querySelector('#sg-go').onclick = sgGive;
  if (start && start.spell && !SG.spells.includes(start.spell)) SG.spells = [start.spell];
  try {
    SG.opts = await api('/api/spellgive/options');
    sgDraw(); sgPreview();
  } catch (e){ const b = bg.querySelector('#sg-body'); if (b) b.innerHTML = `<div class="msg err">${esc(e.message)}</div>`; }
}

function sgMsg(t, err){ const m = SG.bg && SG.bg.querySelector('#sg-msg'); if (m){ m.className = 'msg' + (err ? ' err' : ''); m.innerHTML = t; } }

// a box of chosen things (chips) with a filter to add more from a list: [[value, label, count]]
function sgPick(key, title, rows, ph){
  const cur = SG.f[key] || [];
  const lab = v => { const r = rows.find(x => x[0].toLowerCase() === v.toLowerCase()); return r ? r[1] : v; };
  return `<div class="sg-h">${title}</div>
    <div class="sg-chips">${cur.map(v => `<span class="sg-chip">${esc(lab(v))}<b data-sgx="${key}" data-v="${esc(v)}" title="Take it out">×</b></span>`).join('') || '<span class="msg">anyone</span>'}</div>
    <div class="dd"><input class="inp" data-sgf="${key}" placeholder="${esc(ph)}" autocomplete="off"><div class="ddlist" data-sgl="${key}"></div></div>`;
}

function sgDraw(){
  const box = SG.bg && SG.bg.querySelector('#sg-body'); if (!box) return;
  const O = SG.opts, f = SG.f;
  const rows = {races: O.races.map(([v, n]) => [v, v, n]), classes: O.classes.map(([v, n]) => [v, v, n]), factions: O.factions.map(([v, n]) => [v, v, n]),
                regions: O.regions.map(([v, name, n]) => [v, name, n]), towns: O.towns.map(([v, n]) => [v, v, n])};
  SG.rows = rows;
  box.innerHTML = `<div class="sg-grid">
    <div class="sg-side">
      <div class="sg-h">The spells to give</div>
      <div class="sg-chips">${SG.spells.map(s => `<span class="sg-chip">${esc(s)}<b data-sgsx="${esc(s)}" title="Take it out">×</b></span>`).join('') || '<span class="msg">none yet</span>'}</div>
      <div class="dd"><input class="inp" id="sg-spell" placeholder="Add a spell, ability or power… (search)" autocomplete="off"><div class="ddlist" id="sg-spell-l"></div></div>
      <div class="sg-h" style="margin-top:12px">Who <span class="msg">(all of these; within each, any)</span></div>
      ${sgPick('races', 'Race', rows.races, 'Add a race…')}
      ${sgPick('classes', 'Class', rows.classes, 'Add a class… (e.g. Mage, Healer)')}
      ${sgPick('factions', 'Faction', rows.factions, 'Add a faction… (e.g. Telvanni)')}
      <div class="sg-h">Already knows</div>
      <div class="sg-chips">${(f.knows || []).map(s => `<span class="sg-chip">${esc(s)}<b data-sgx="knows" data-v="${esc(s)}">×</b></span>`).join('') || '<span class="msg">anything</span>'}</div>
      <div class="dd"><input class="inp" id="sg-knows" placeholder="A spell they know… (e.g. fireball)" autocomplete="off"><div class="ddlist" id="sg-knows-l"></div></div>
      <div class="sg-h">Skill</div>
      <div class="sg-row"><select class="inp" id="sg-skill"><option value="">any skills</option>${O.skills.map((s, i) => `<option value="${i}" ${f.skill && +f.skill.i === i ? 'selected' : ''}>${esc(s)}</option>`).join('')}</select>
        <span class="msg">at least</span><input class="inp" id="sg-min" type="number" min="0" max="100" value="${f.skill ? f.skill.min : 30}" style="width:70px"></div>
      <label class="msg sg-row" style="margin-top:6px"><input type="checkbox" id="sg-sellers" ${f.sellers ? 'checked' : ''}> Only those who sell spells</label>
      <div class="sg-h" style="margin-top:12px">Where <span class="msg">(standing in any of these)</span></div>
      ${sgPick('regions', 'Region', rows.regions, 'Add a region… (e.g. West Gash)')}
      ${sgPick('towns', 'Town or city', rows.towns, 'Add a town… (e.g. Balmora)')}
    </div>
    <div class="sg-main">
      <div class="sg-h">Who fits <span class="msg" id="sg-count"></span></div>
      <div class="sg-list" id="sg-list"><div class="msg">Pick the spells first.</div></div>
      <div class="sg-h" style="margin-top:10px">How to give them</div>
      <label class="msg sg-radio"><input type="radio" name="sg-mode" value="records" ${SG.mode === 'records' ? 'checked' : ''}> <b>In their records</b>: each one's spell list in your mod. Simple and plain to see, but every one of them becomes a change of yours, which can clash with another mod that changes the same people.</label>
      <label class="msg sg-radio"><input type="radio" name="sg-mode" value="script" ${SG.mode === 'script' ? 'checked' : ''}> <b>By a script</b>: they learn them the first time they come near in game. Their records stay untouched, so it works beside any mod. Needs the mod as an .omwaddon.</label>
      ${SG.mode === 'script' ? `<input class="inp" id="sg-label" placeholder="A name for this rule (e.g. Telvanni mages learn Levitate)" style="margin-top:6px" value="${esc(SG.label || '')}">` : ''}
      ${(O.rules || []).length ? `<div class="sg-h" style="margin-top:12px">Given by script already</div>
        ${O.rules.map((r, n) => `<div class="sg-rule"><span style="flex:1"><b>${esc(r.label || r.spells.join(', '))}</b> <span class="msg">${esc(r.spells.join(', '))} · ${r.n != null ? r.n + ' people' : ''}</span></span><button class="btn sm danger" data-sgrm="${n}" title="Stop giving these by script">✕</button></div>`).join('')}
        <button class="btn sm" id="sg-refresh" title="Match the rules again against everyone as they are now: after adding mods or people">↻ Match again</button>` : ''}
    </div></div>`;
  ddSearch('sg-spell', 'SPEL', r => { if (!SG.spells.includes(r.id)) SG.spells.push(r.id); sgDraw(); sgPreview(); });
  ddSearch('sg-knows', 'SPEL', r => { f.knows = [...new Set([...(f.knows || []), r.id])]; sgDraw(); sgPreview(); });
  box.querySelectorAll('[data-sgsx]').forEach(b => b.onclick = () => { SG.spells = SG.spells.filter(s => s !== b.dataset.sgsx); sgDraw(); sgPreview(); });
  box.querySelectorAll('[data-sgx]').forEach(b => b.onclick = () => { const k = b.dataset.sgx; f[k] = (f[k] || []).filter(v => v !== b.dataset.v); if (!f[k].length) delete f[k]; sgDraw(); sgPreview(); });
  box.querySelectorAll('[data-sgf]').forEach(inp => {
    const k = inp.dataset.sgf, list = box.querySelector(`[data-sgl="${k}"]`);
    inp.oninput = () => {
      const q = inp.value.trim().toLowerCase();
      if (!q){ list.style.display = 'none'; return; }
      const hits = rows[k].filter(r => r[1].toLowerCase().includes(q) || r[0].toLowerCase().includes(q)).slice(0, 30);
      list.innerHTML = hits.map(r => `<div data-v="${esc(r[0])}">${esc(r[1])}<small>${r[2]} ${r[2] === 1 ? 'person' : 'people'}</small></div>`).join('') || '<div class="msg">No matches</div>';
      list.style.display = 'block';
      list.querySelectorAll('[data-v]').forEach(d => d.onmousedown = e => { e.preventDefault(); f[k] = [...new Set([...(f[k] || []), d.dataset.v])]; sgDraw(); sgPreview(); });
    };
    inp.onblur = () => setTimeout(() => { list.style.display = 'none'; }, 150);
  });
  const skill = () => { const v = $('#sg-skill').value; if (v === '') delete f.skill; else f.skill = {i: +v, min: +$('#sg-min').value || 0}; sgPreview(); };
  $('#sg-skill').onchange = skill; $('#sg-min').oninput = skill;
  $('#sg-sellers').onchange = e => { if (e.target.checked) f.sellers = true; else delete f.sellers; sgPreview(); };
  box.querySelectorAll('[name=sg-mode]').forEach(r => r.onchange = () => { SG.mode = r.value; sgDraw(); sgPreview(); });
  const lb = $('#sg-label'); if (lb) lb.oninput = () => { SG.label = lb.value; };
  box.querySelectorAll('[data-sgrm]').forEach(b => b.onclick = async () => {
    try { const r = await post('/api/spellgive/remove', {n: +b.dataset.sgrm}); SG.opts.rules = r.rules; sgDraw(); sgPreview(); toast('Stopped giving those by script. Undo takes it back.'); }
    catch (e){ sgMsg(esc(e.message), true); }
  });
  const rf = $('#sg-refresh'); if (rf) rf.onclick = async () => {
    try { const r = await post('/api/spellgive/refresh', {}); SG.opts.rules = r.rules; sgDraw(); sgPreview(); toast(`Matched again: ${r.people} people learn something by script.`); }
    catch (e){ sgMsg(esc(e.message), true); }
  };
}

// who fits, a moment after each change
function sgPreview(){
  clearTimeout(SG.t);
  SG.t = setTimeout(async () => {
    const go = SG.bg && SG.bg.querySelector('#sg-go'), list = $('#sg-list'), cnt = $('#sg-count'); if (!list) return;
    if (!SG.spells.length){ list.innerHTML = '<div class="msg">Pick the spells first.</div>'; cnt.textContent = ''; go.disabled = true; sgMsg(''); return; }
    const my = ++SG.seq;
    try {
      const r = await post('/api/spellgive/preview', {spells: SG.spells, filters: SG.f});
      if (my !== SG.seq) return;
      cnt.textContent = `${r.n} ${r.n === 1 ? 'person' : 'people'}, ${r.getting} to learn something`;
      list.innerHTML = r.rows.map(p => `<div class="sg-p ${p.new.length ? '' : 'sg-has'}"><span class="lnk" data-sgo="${esc(p.id)}" title="Open their character">${esc(p.name || p.id)}</span>
          <span class="msg">${esc([p.race, p.cls, p.faction].filter(Boolean).join(' · '))}${p.where ? ' · ' + esc(p.where) : ''}</span>
          <span class="msg sg-new">${p.new.length ? '+ ' + esc(p.new.join(', ')) : 'knows them already'}</span></div>`).join('')
        + (r.n > r.rows.length ? `<div class="msg">…and ${r.n - r.rows.length} more.</div>` : '') || '<div class="msg">No one fits. Loosen a filter.</div>';
      list.querySelectorAll('[data-sgo]').forEach(a => a.onclick = () => { if (typeof cOpen === 'function'){ SG.bg.remove(); SG.bg = null; cOpen(a.dataset.sgo); } });
      go.disabled = !r.getting;
      sgMsg(r.getting ? (SG.mode === 'script' ? `A script will teach ${r.getting} people as they come near.` : `${r.getting} people's records will change in your mod.`) + ' One Undo takes it back.' : '');
    } catch (e){ if (my === SG.seq){ list.innerHTML = `<div class="msg err">${esc(e.message)}</div>`; go.disabled = true; } }
  }, 250);
}

async function sgGive(){
  if (!await needProject()) return;
  const go = SG.bg.querySelector('#sg-go'); go.disabled = true;
  try {
    const r = await post('/api/spellgive/give', {spells: SG.spells, filters: SG.f, mode: SG.mode, label: SG.label || ''});
    if (r.rules) SG.opts.rules = r.rules;
    toast(SG.mode === 'script' ? `A script now teaches ${SG.spells.join(', ')} to ${r.given} people.` : `Gave ${SG.spells.join(', ')} to ${r.given} people.`);
    sgDraw(); sgPreview();
  } catch (e){ sgMsg(esc(e.message), true); go.disabled = false; }
}

function sgCss(){
  if (document.getElementById('sg-css')) return;
  const s = document.createElement('style'); s.id = 'sg-css';
  s.textContent = `.sg-win{width:min(1060px,96vw);max-height:92vh;display:flex;flex-direction:column}
  .sg-win #sg-body{overflow:auto;flex:1;min-height:0}
  .sg-grid{display:grid;grid-template-columns:360px 1fr;gap:18px}
  .sg-h{font-weight:600;margin:8px 0 4px}
  .sg-row{display:flex;gap:6px;align-items:center}
  .sg-chips{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:4px}
  .sg-chip{background:var(--panel2);border:1px solid var(--line2);border-radius:12px;padding:1px 8px;font-size:12px}
  .sg-chip b{cursor:pointer;margin-left:6px;opacity:.7}
  .sg-list{border:1px solid var(--line);border-radius:6px;max-height:330px;overflow:auto;padding:4px 8px}
  .sg-p{display:flex;gap:8px;align-items:baseline;padding:3px 0;border-bottom:1px solid var(--line)}
  .sg-p .sg-new{margin-left:auto;white-space:nowrap}
  .sg-has{opacity:.55}
  .sg-radio{display:block;margin:4px 0;line-height:1.45}
  .sg-rule{display:flex;gap:8px;align-items:center;padding:3px 0}`;
  document.head.appendChild(s);
}

if (typeof CF_ACT !== 'undefined') CF_ACT.push({id: 'spellgive', label: 'Give spells to people… (everyone who fits, by region or town)', keys: [], world: false, run: () => sgShow()});
