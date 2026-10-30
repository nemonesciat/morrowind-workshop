// ---------- Populate: people for a place (populate.py) ----------
// A window over the World map's view: the cast the Workshop proposes for the place open (who would live
// or work there, as the game's own places of its kind have them), to change, re-roll person by person,
// lock, and place as one change. "Someone who'd live here" does the same for one person, at the spot clicked.
const PO = {el: null, cell: null, data: null, params: {density: 'usual', wealth: 'auto', races: [], faction: '', occupations: [], only: false, own: true, lines: true, creatures: true, band: '', routines: true},
  locked: new Set(), at: null, busy: false};
const PO_TOPIC = {greeting: 'Greeting', 'my trade': 'My trade', 'someone in particular': 'Someone in particular', 'little secret': 'Little secret',
  'latest rumors': 'Latest rumors'};
const PO_WHEN = {first: 'when they first meet', again: 'later on', liked: 'only to someone they like'};

(function poCss(){
  const st = document.createElement('style');
  st.textContent = `
.powin{position:absolute;right:16px;top:16px;width:min(760px,calc(100% - 32px));max-height:calc(100% - 32px);display:flex;flex-direction:column;z-index:45}
.powin .pobody{overflow:auto;padding:10px 14px 16px;min-height:0}
.powin .owhead{cursor:move}
.pogrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:6px 10px;margin:6px 0 10px}
.pogrid label{font-size:11.5px;color:var(--muted);display:flex;flex-direction:column;gap:2px}
.pogrid .inp{padding:3px 6px;font-size:12.5px}
.pochips{display:flex;flex-wrap:wrap;gap:4px;margin-top:2px}
.pochips span{font-size:11.5px;border:1px solid var(--line2);border-radius:10px;padding:0 7px;color:var(--text);cursor:pointer}
.pochips span:hover{border-color:var(--red);color:var(--red)}
.pobar{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:8px 0}
.pocast{display:flex;flex-direction:column;gap:8px}
.poperson{border:1px solid var(--line2);border-radius:9px;background:var(--panel);padding:7px 10px}
.poperson.locked{border-color:var(--gold)}
.poperson .ptop{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.poperson .ptop .inp{font-size:13.5px;font-weight:600;padding:2px 6px;width:200px}
.poperson .pmeta{font-size:12px;color:var(--muted);flex:1;min-width:200px}
.poperson .pbtns{display:flex;gap:3px}
.poperson .pbtns .btn{padding:1px 7px}
.poperson details{margin-top:4px;font-size:12px}
.poperson summary{cursor:pointer;color:var(--muted)}
.poperson .pedit{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:4px 8px;margin-top:6px}
.poperson .pedit label{font-size:11px;color:var(--faint);display:flex;flex-direction:column}
.poperson .pedit .inp{padding:2px 5px;font-size:12px}
.poperson .pitems{color:var(--muted);line-height:1.5;margin-top:4px}
.ponote{font-size:12px;color:var(--amber);margin:4px 0}
.pocrs{display:flex;flex-wrap:wrap;gap:4px;margin:4px 0 10px}
.pocrs span{font-size:12px;border:1px solid var(--line2);border-radius:10px;padding:1px 8px;cursor:pointer}
.pocrs span:hover{border-color:var(--red);color:var(--red)}
.poline{margin-top:6px}
.poline .ai-row{display:flex;gap:4px;align-items:flex-start}
.poline textarea{flex:1;font-size:12.5px;line-height:1.4;min-height:38px;resize:vertical}`;
  document.head.appendChild(st);
})();

function poOpen(cell, at){
  if (!cell){ toast('Open a place first.'); return; }
  if (W.ext || String(cell).startsWith('#')){ toast('Populate works indoors for now: open an interior.', true); return; }
  if (typeof owCss === 'function') owCss();
  if (PO.cell !== cell){ PO.data = null; PO.locked = new Set(); }
  PO.cell = cell; PO.at = at || null;
  if (!PO.el || !PO.el.isConnected){
    const box = $('#world .mapwrap'); if (!box) return;
    const el = document.createElement('div'); el.className = 'owin powin'; el.setAttribute('data-ownkeys', '');
    el.innerHTML = `<div class="owhead"><span class="owtitle">👥 Populate</span><button class="btn sm" data-poclose title="Close (nothing is placed until you press Place them)">✕</button></div><div class="pobody"></div>`;
    box.appendChild(el); PO.el = el;
    el.querySelector('[data-poclose]').onclick = poClose;
    el.addEventListener('keydown', e => { if (e.key === 'Escape') poClose(); e.stopPropagation(); });
    // drag by the title bar
    const head = el.querySelector('.owhead'); let D = null;
    head.addEventListener('pointerdown', e => { if (e.button || e.target.closest('button')) return; const r = el.getBoundingClientRect(); D = {dx: e.clientX - r.left, dy: e.clientY - r.top}; head.setPointerCapture(e.pointerId); });
    head.addEventListener('pointermove', e => { if (!D) return; const b = box.getBoundingClientRect(); el.style.left = Math.max(0, e.clientX - b.left - D.dx) + 'px'; el.style.top = Math.max(0, e.clientY - b.top - D.dy) + 'px'; el.style.right = 'auto'; });
    head.addEventListener('pointerup', () => { D = null; });
  }
  if (typeof vwFront === 'function') vwFront(PO.el);
  if (at) poCast({count: 1}); else if (!PO.data) poCast(); else poDraw();
}
function poClose(){ if (PO.el){ PO.el.remove(); PO.el = null; } PO.at = null; }

async function poCast(extra, keep){
  if (PO.busy) return;
  PO.busy = true;
  const body = PO.el && PO.el.querySelector('.pobody');
  if (body && !PO.data) body.innerHTML = '<div class="msg" style="padding:16px"><span class="spin"></span>Finding who would live here…</div>';
  const P = PO.params;
  const params = {density: P.density, wealth: P.wealth, races: P.races, faction: P.faction, occupations: P.occupations, only: P.only, setting: P.setting || null,
                  lines: P.lines, creatures: P.creatures, band: P.band};
  // (keeping people: the band they are of stays, whatever the page's choice says)
  if (keep && keep.length && PO.data) params.band = PO.data.band || 'none';
  Object.assign(params, extra || {});
  let r;
  try { r = await post('/api/populate/cast', {cell: PO.cell, params, keep: keep || [], seed: null}); }
  catch (e){ PO.busy = false; toast(e.message, true); if (body && !PO.data) body.innerHTML = `<div class="msg err" style="padding:16px">${esc(e.message)}</div>`; return; }
  PO.busy = false;
  if (r.learning){
    if (body) body.innerHTML = `<div class="msg" style="padding:16px;line-height:1.6"><span class="spin"></span>Learning who the game's people are first (${esc(r.learning.join(', '))}). This takes about half a minute, once.</div>`;
    setTimeout(() => { if (PO.el) poCast(extra, keep); }, 4000);
    return;
  }
  if (PO.at && r.people.length && (!keep || !keep.length)){
    // "Someone who'd live here": they stand where you clicked
    const p = r.people[r.people.length - 1];
    p.spot = [PO.at.x, PO.at.y, PO.at.z != null ? PO.at.z + 4 : (p.spot ? p.spot[2] : 0), p.spot ? p.spot[3] : 0];
    p.spot_by = '';
  }
  PO.data = r;
  poDraw();
}
// re-roll everyone not locked (or just one person), keeping the rest where they are
function poReroll(only){
  const d = PO.data; if (!d) return;
  const keep = d.people.filter(p => only ? p.key !== only : PO.locked.has(p.key));
  poCast(only ? {count: d.people.length, keep_creatures: d.creatures || [], keep_loot: d.loot || []} : {count: d.people.length}, keep);
}
function poDraw(){
  const d = PO.data, el = PO.el; if (!d || !el) return;
  el.querySelector('.owtitle').textContent = '👥 Populate: ' + d.place;
  const P = PO.params, o = d.options || {};
  const relName = {head: 'head of the household', family: 'family', servant: 'servant', lodger: 'lodger', patron: 'patron', guard: 'guard',
    leader: 'leader', band: (d.band_label || 'band').toLowerCase()};
  const sel = (k, list, v) => `<select class="inp" data-pp="${k}">${list.map(([val, t]) => `<option value="${esc(val)}" ${String(v) === String(val) ? 'selected' : ''}>${esc(t)}</option>`).join('')}</select>`;
  const kinds = {house: 'houses', manor: 'manors', shop: 'shops', tavern: 'taverns', temple: 'temples', guild: 'guildhalls and offices',
    guard: 'guard posts', plaza: 'plazas', cave: 'caves', mine: 'mines', tomb: 'tombs', dwemer: 'Dwemer ruins', daedric: 'Daedric shrines',
    ruin: 'ruins', stronghold: 'strongholds', camp: 'camps', sewer: 'sewers', hideout: 'hideouts'};
  const crs = d.creatures || [];
  const crN = {}, lts = d.loot || [], ltN = {};
  crs.forEach(c => { crN[c.id] = (crN[c.id] || 0) + 1; });
  lts.forEach(c => { ltN[c.id] = (ltN[c.id] || 0) + 1; });
  let h = `<div class="msg" style="line-height:1.55">${d.people.length} ${d.people.length === 1 ? 'person' : 'people'}${crs.length ? ` and ${crs.length} creature${crs.length === 1 ? '' : 's'}` : ''} for <b>${esc(d.place)}</b>${d.band ? `: <b>${esc(d.band_label)}</b>` : ''}, as the game's own ${d.culture && d.culture !== '?' ? esc(d.culture) + ' ' : ''}<b>${esc(kinds[d.setting] || d.setting)}</b> have them.
      ${d.already ? `${d.already} already ${d.already === 1 ? 'lives' : 'live'} here.` : ''} Nothing is placed until you press <b>Place them</b>.</div>
    <div class="pogrid">
      <label>How busy${sel('density', [['quiet', 'Quiet'], ['usual', 'As the game has it'], ['busy', 'Busy'], ['1', '1 person'], ['2', '2'], ['3', '3'], ['5', '5'], ['8', '8'], ['12', '12']], P.density)}</label>
      <label>Wealth${sel('wealth', [['auto', 'As the game has it'], ['poor', 'Poor'], ['common', 'Common'], ['fine', 'Well off'], ['rich', 'Rich']], P.wealth)}</label>
      ${(o.bands || []).length ? `<label>Band${sel('band', [['', 'As the game has it'], ...o.bands, ['none', 'No band']], P.band)}</label>` : ''}
      <label>Kind of place${sel('setting', [['', 'As it is (' + d.setting + ')'], ...(o.settings || []).filter(s => s !== 'outdoors').map(s => [s, s])], P.setting || '')}</label>
      <label>Faction<input class="inp" data-pp="faction" list="po-factions" placeholder="as the game has it" value="${esc(P.faction)}"></label>
      <label>Races <span class="msg" style="font-size:10.5px">(none: as the game has it)</span><input class="inp" data-pp="race" list="po-races" placeholder="add a race…">
        <div class="pochips">${P.races.map(x => `<span data-prm="races|${esc(x)}" title="Remove">${esc(x)} ✕</span>`).join('')}</div></label>
      <label>Occupations<input class="inp" data-pp="occ" list="po-classes" placeholder="add a class…">
        <div class="pochips">${P.occupations.map(x => `<span data-prm="occupations|${esc(x)}" title="Remove">${esc(x)} ✕</span>`).join('')}</div>
        ${P.occupations.length ? `<span><input type="checkbox" data-pp="only" ${P.only ? 'checked' : ''}> only these</span>` : ''}</label>
    </div>
    <datalist id="po-races">${(o.races || []).map(x => `<option value="${esc(x)}">`).join('')}</datalist>
    <datalist id="po-classes">${(o.classes || []).map(x => `<option value="${esc(x)}">`).join('')}</datalist>
    <datalist id="po-factions">${((D.opts && D.opts.factions) || []).map(x => `<option value="${esc(x)}">`).join('')}</datalist>
    <div class="pobar"><button class="btn" data-pa="again" title="New people for everyone not locked (🔒)">🎲 New cast</button>
      <button class="btn" data-pa="more">+ One more</button>
      <label class="msg"><input type="checkbox" data-pp="own" ${P.own ? 'checked' : ''}> the household owns the beds and chests</label>
      <label class="msg" title="Each sleeps by their own bed, eats at a table, works and spends the evening by the hours (OpenMW: a script in your mod keeps them to it; guards and patrons stay put)"><input type="checkbox" data-pp="routines" ${P.routines ? 'checked' : ''}> daily routines</label>
      <label class="msg" title="The creatures and creature lists the game's places of this kind hold (a list picks by the player's level)"><input type="checkbox" data-pp="creatures" ${P.creatures ? 'checked' : ''}> creatures</label>
      <label class="msg" title="A greeting, my trade, someone in particular, a little secret and a rumour each, written from templates (no AI): change any of them below or later in Dialogue"><input type="checkbox" data-pp="lines" ${P.lines ? 'checked' : ''}> words of their own</label>
      <span style="flex:1"></span><button class="btn primary" data-pa="place" ${d.people.length || crs.length ? '' : 'disabled'}>Place them</button></div>
    ${(d.notes || []).map(n => `<div class="ponote">${esc(n)}</div>`).join('')}
    ${crs.length ? `<div class="msg" style="display:flex;align-items:center;gap:6px">Creatures <button class="btn sm" data-pa="crs" title="Other creatures, the people kept">🎲</button></div>
      <div class="pocrs">${Object.entries(crN).map(([id, n]) => { const c = crs.find(x => x.id === id);
        return `<span data-pcr="${esc(id)}" title="${c.list ? 'A creature list: the game picks by the player\'s level. ' : ''}Click to leave one out">${esc(c.name)}${c.list ? ' ⟳' : ''}${n > 1 ? ' ×' + n : ''}</span>`; }).join('')}</div>` : ''}
    ${lts.length ? `<div class="msg" style="display:flex;align-items:center;gap:6px">Loot <button class="btn sm" data-pa="lts" title="Other loot, the rest kept">🎲</button></div>
      <div class="pocrs">${Object.entries(ltN).map(([id, n]) => { const c = lts.find(x => x.id === id);
        return `<span data-plt="${esc(id)}" title="${esc(id)}: against a wall. Click to leave one out">${esc(c.name)}${n > 1 ? ' ×' + n : ''}</span>`; }).join('')}</div>` : ''}
    <div class="pocast">${d.people.map((p, n) => {
      const lk = PO.locked.has(p.key);
      return `<div class="poperson ${lk ? 'locked' : ''}" data-pn="${n}"><div class="ptop">
        <input class="inp" data-pf="name" value="${esc(p.name)}" title="Their name">
        <span class="pmeta">${esc(p.female ? 'female' : 'male')} ${esc(p.race)} · ${esc(p.cls)} · level ${p.level}${p.faction ? ' · ' + esc(p.faction) + ' rank ' + p.rank : ''}
          · ${esc({poor: 'poor', common: 'common', fine: 'well off', rich: 'rich'}[p.band] || p.band)}${p.spouse && p.relation !== 'head' ? ' · ' + (p.female ? 'his wife' : 'her husband') : p.relation ? ' · ' + esc(relName[p.relation] || p.relation) : ''}
          · ${p.spot ? (p.spot_by ? 'by the ' + esc(p.spot_by) : 'on the floor') : '<span style="color:var(--amber)">no spot: placed by hand later</span>'}</span>
        <span class="pbtns"><button class="btn sm" data-pl title="${lk ? 'Unlock: New cast may change them' : 'Lock: New cast keeps them'}">${lk ? '🔒' : '🔓'}</button>
          <button class="btn sm" data-pr title="Someone else instead of them">🎲</button><button class="btn sm danger" data-px title="Leave them out">✕</button></span></div>
        <div class="pitems">${p.items.map(([id, c]) => esc(id) + (Math.abs(c) > 1 ? ' ×' + Math.abs(c) : '')).join(' · ')}${p.spells.length ? ' · spells: ' + p.spells.map(esc).join(', ') : ''}${p.services ? ' · sells, gold ' + p.gold : ''}</div>
        <details><summary>Change them</summary><div class="pedit">
          <label>Race<input class="inp" data-pf="race" list="po-races" value="${esc(p.race)}"></label>
          <label>Sex<select class="inp" data-pf="female"><option value="0" ${p.female ? '' : 'selected'}>male</option><option value="1" ${p.female ? 'selected' : ''}>female</option></select></label>
          <label>Class<input class="inp" data-pf="cls" list="po-classes" value="${esc(p.cls)}"></label>
          <label>Faction<input class="inp" data-pf="faction" list="po-factions" value="${esc(p.faction)}"></label>
          <label>Rank<input class="inp" type="number" min="0" max="9" data-pf="rank" value="${p.rank}"></label>
          <label>Level<input class="inp" type="number" min="1" max="100" data-pf="level" value="${p.level}"></label>
          <label>Fight<input class="inp" type="number" min="0" max="100" data-pf="fight" value="${p.fight}"></label>
          <label>Wander<input class="inp" type="number" min="0" max="2000" data-pf="wander" value="${p.wander}"></label>
        </div><div class="msg" style="margin-top:4px">A change of race or class keeps the outfit: 🎲 makes a new person in full.</div></details>
        ${(p.lines || []).length ? `<details><summary>Their words (${p.lines.length})</summary>${p.lines.map((ln, i) => `<div class="poline">
          <span class="msg">${esc(PO_TOPIC[ln.topic] || ln.topic)}${ln.when ? ' · ' + esc(PO_WHEN[ln.when] || ln.when) : ''}</span>
          <div class="ai-row"><textarea class="inp" data-pline="${i}" rows="2">${esc(ln.text)}</textarea><button class="btn sm" data-pai="${i}" title="Write it better with the Assistant (asks first; uses your API key)">✦</button></div></div>`).join('')}</details>` : ''}</div>`;
    }).join('')}</div>`;
  const body = el.querySelector('.pobody'); body.innerHTML = h;
  // (a change of how busy, wealth, races…: a new cast by them, the locked people kept)
  const redo = () => poCast({}, d.people.filter(p => PO.locked.has(p.key)));
  body.querySelectorAll('[data-pp]').forEach(inp => inp.onchange = () => {
    const k = inp.dataset.pp, v = inp.type === 'checkbox' ? inp.checked : inp.value.trim();
    if (k === 'race'){ if (v && !P.races.includes(v)) P.races.push(v); inp.value = ''; }
    else if (k === 'occ'){ if (v && !P.occupations.includes(v)) P.occupations.push(v); inp.value = ''; }
    else if (k === 'own'){ P.own = v; return; }
    else if (k === 'routines'){ P.routines = v; return; }
    else if (k === 'lines'){ P.lines = v; if (!v) d.people.forEach(p => { p.lines = []; }); }
    else if (k === 'creatures'){ P.creatures = v; if (!v){ d.creatures = []; poDraw(); return; } poCast({count: d.people.length}, d.people); return; }
    else P[k] = v;
    redo();
  });
  body.querySelectorAll('[data-prm]').forEach(s => s.onclick = () => { const [k, v] = s.dataset.prm.split('|'); P[k] = P[k].filter(x => x !== v); redo(); });
  body.querySelector('[data-pa="again"]').onclick = redo;
  body.querySelector('[data-pa="more"]').onclick = () => poCast({count: d.people.length + 1, keep_creatures: crs, keep_loot: lts}, d.people);
  const rc = body.querySelector('[data-pa="crs"]'); if (rc) rc.onclick = () => poCast({count: d.people.length, keep_loot: lts}, d.people);
  const rl = body.querySelector('[data-pa="lts"]'); if (rl) rl.onclick = () => poCast({count: d.people.length, keep_creatures: crs}, d.people);
  body.querySelectorAll('[data-plt]').forEach(s => s.onclick = () => { const i = lts.findIndex(c => c.id === s.dataset.plt); if (i >= 0) lts.splice(i, 1); poDraw(); });
  body.querySelectorAll('[data-pcr]').forEach(s => s.onclick = () => { const i = crs.findIndex(c => c.id === s.dataset.pcr); if (i >= 0) crs.splice(i, 1); poDraw(); });
  body.querySelector('[data-pa="place"]').onclick = poPlace;
  body.querySelectorAll('[data-pn]').forEach(card => {
    const p = d.people[+card.dataset.pn];
    card.querySelector('[data-pl]').onclick = () => { if (PO.locked.has(p.key)) PO.locked.delete(p.key); else PO.locked.add(p.key); poDraw(); };
    card.querySelector('[data-pr]').onclick = () => poReroll(p.key);
    card.querySelector('[data-px]').onclick = () => { d.people.splice(+card.dataset.pn, 1); PO.locked.delete(p.key); poDraw(); };
    card.querySelectorAll('[data-pline]').forEach(ta => ta.oninput = () => {
      p.lines[+ta.dataset.pline].text = ta.value; p.lines_edited = true; PO.locked.add(p.key);
    });
    card.querySelectorAll('[data-pai]').forEach(b => b.onclick = () => {
      const ln = p.lines[+b.dataset.pai], ta = card.querySelector(`[data-pline="${b.dataset.pai}"]`);
      aiDraft({kind: ln.topic === 'greeting' ? 'greeting' : 'topic', topic: ln.topic === 'greeting' ? 'greeting 5' : ln.topic, npc: '',
               brief: `${p.name}, a ${p.female ? 'female' : 'male'} ${p.race} ${p.cls} in ${d.place}`, current: ta.value},
              b, t => { ta.value = t; ln.text = t; p.lines_edited = true; PO.locked.add(p.key); });
    });
    card.querySelectorAll('[data-pf]').forEach(inp => inp.onchange = () => {
      const f = inp.dataset.pf;
      p[f] = f === 'female' ? inp.value === '1' : ['rank', 'level', 'fight', 'wander'].includes(f) ? +inp.value : inp.value.trim();
      PO.locked.add(p.key);              // (someone you changed by hand stays as you made them)
      if (f !== 'name') poDraw();
    });
  });
  if (!D.opts) dOpts().then(() => { if (PO.data === d) poDraw(); }).catch(() => {});
}
async function poPlace(){
  const d = PO.data; if (!d || !(d.people.length || (d.creatures || []).length)) return;
  if (!await needProject()) return;
  const btn = PO.el.querySelector('[data-pa="place"]'); btn.disabled = true; btn.innerHTML = '<span class="spin"></span>Placing…';
  try {
    const r = await post('/api/populate/place', {cell: PO.cell, people: d.people, own: PO.params.own, creatures: d.creatures || [], loot: d.loot || [],
      routines: PO.params.routines});
    toast(`Placed ${r.placed} ${r.placed === 1 ? 'person' : 'people'}${r.creatures ? `, ${r.creatures} creature${r.creatures === 1 ? '' : 's'}` : ''}${r.loot ? `, ${r.loot} loot container${r.loot === 1 ? "" : "s"}` : ''}${r.owned ? `; they own ${r.owned} beds and containers` : ''}${r.routines ? `; ${r.routines} keep daily routines` : ''}. One Undo takes it all back. New people appear in the game after restarting it with Play here.`);
    const ck = PO.cell;
    poClose(); PO.data = null; PO.locked = new Set();
    await afterChange();
    if (W.cells[ck] && W.cells[ck].exists) await worldReloadCell(ck);
    if (typeof V3 !== 'undefined' && V3.on && typeof v3Refresh === 'function') v3Refresh();
  } catch (e){ toast(e.message, true); btn.disabled = false; btn.textContent = 'Place them'; }
}

// ---------------------------------------------------------------- the ways in
// the view's right-click menu: "👥 Populate this place…" and "🧍 Someone who'd live here"
CF_MENU_MORE.push((e, hit, at) => {
  if (W.mode === 'paths' || W.ext || !W.key) return [];
  if (hit && W.multi.size > 1 && inMulti(hit[0], hit[1].k)) return [];
  const spot = typeof vwSpot === 'function' ? vwSpot(at || (hit && hit[1] && hit[1].p) || null) : null;
  return [{label: '👥 Populate this place…', title: 'People who would live or work here, as the game\'s own places of this kind have them: see them first, then place them', act: () => poOpen(W.key, null)},
          {label: '🧍 Someone who\'d live here', title: 'One person for this place, standing where you clicked', act: () => { PO.data = null; poOpen(W.key, spot); }}];
});
CF_ACT.push({id: 'populate', label: 'Populate this place… (people who would live or work here)', keys: [], world: true, run: () => poOpen(W.key, null)});
