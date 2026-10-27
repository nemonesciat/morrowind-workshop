// ---------- Ownership & lock: who owns a placed object, its lock, key and trap, uses left, the soul in a gem ----------
// (the Selected panel on the World map; the CS's Instances table has these as columns)
const RP = {cell: null, k: null, open: false, data: null, orig: null, loading: false};

function refPropsReset(){ RP.data = null; RP.orig = null; }

// called after the Selected panel is drawn: a button, or the open form for the selected object
async function refPropsRender(){
  const box = $('#w-props'); if (!box) return;
  const sel = W.sel && findRef(W.sel.cell, W.sel.k);
  if (!sel || sel.type === 'NPC_' || sel.type === 'CREA'){ box.innerHTML = ''; return; }
  const same = RP.cell === W.sel.cell && RP.k === sel.k;
  if (!same){ RP.cell = W.sel.cell; RP.k = sel.k; refPropsReset(); }
  if (!RP.open){
    box.innerHTML = `<button class="btn sm" id="w-props-open" title="Who owns it, the lock and key, the trap, uses left">🔒 Ownership &amp; lock…</button>`;
    $('#w-props-open').onclick = () => { RP.open = true; refPropsRender(); };
    return;
  }
  if (!RP.data){
    box.innerHTML = '<div class="msg"><span class="spin"></span>Loading…</div>';
    if (RP.loading) return;
    RP.loading = true;
    try { const d = await api('/api/ref/props?' + new URLSearchParams({cell: RP.cell, ref: RP.k})); if (RP.k === sel.k) { RP.data = d; RP.orig = JSON.stringify(d); } }
    catch (e){ box.innerHTML = `<div class="msg err">${esc(e.message)}</div>`; RP.loading = false; return; }
    RP.loading = false;
    if (RP.k !== sel.k) return refPropsRender();
  }
  const d = RP.data, dirty = JSON.stringify(d) !== RP.orig;
  const pick = (f, ph) => `<div class="dd"><input class="inp" id="rp-${f}" value="${esc(d[f] || '')}" placeholder="${ph}" autocomplete="off"><div class="ddlist" id="rp-${f}-l"></div></div>${d[f + '_missing'] ? `<small class="err">"${esc(d[f])}" doesn't exist</small>` : d[f + '_name'] && d[f + '_name'].toLowerCase() !== (d[f] || '').toLowerCase() ? `<small style="color:var(--faint)">${esc(d[f + '_name'])}</small>` : ''}`;
  let h = `<div class="rpbox"><h3 style="margin:10px 0 4px">🔒 Ownership &amp; lock <button class="btn sm" id="rp-close" style="float:right" title="Close">✕</button></h3>`;
  if (d.can_own){
    h += `<label class="cfield"><span>Belongs to</span>${pick('owner', 'a person… (search); empty: no one')}<small>Taking it counts as stealing from them, and they tell you off for using their bed.</small></label>
      <div class="crow"><label class="cfield" style="flex:2"><span>or to the faction</span>${pick('faction', 'a faction… (search)')}</label>
        ${d.faction ? `<label class="cfield" style="flex:1"><span>free from rank</span><select class="inp" id="rp-rank">${(d.ranks && d.ranks.length ? d.ranks : ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']).map((r, n) => `<option value="${n}" ${n === (d.rank || 0) ? 'selected' : ''}>${esc(r)}</option>`).join('')}</select></label>` : ''}</div>
      <label class="cfield"><span>Owner set by a global variable</span>${pick('global', 'a global variable… (search); usually empty')}<small>While the variable is 1 (or more), it belongs to nobody: how the game rents out beds.</small></label>`;
  }
  if (d.can_lock){
    h += `<div class="crow"><label class="cfield" style="flex:1"><span>Lock level</span><input class="inp num" type="number" id="rp-lock" min="0" max="1000" value="${d.lock || 0}"><small>0: unlocked. 1 easy … 100 hard; over 100 only the key opens it.</small></label>
        <label class="cfield" style="flex:2"><span>Key</span>${pick('key', 'a key… (search)')}</label></div>
      <label class="cfield"><span>Trap</span>${pick('trap', 'a spell… (search); empty: no trap')}<small>Cast on whoever opens it (a touch spell, like the game's trap spells).</small></label>`;
  }
  if (d.uses_label){
    h += `<label class="cfield"><span>${esc(d.uses_label)}</span><input class="inp num" type="number" id="rp-uses" min="0" value="${d.uses == null ? '' : d.uses}" placeholder="as new"><small>Empty: as new. The game's used-up picks and worn weapons are made this way.</small></label>`;
  }
  if (d.can_soul){
    h += `<label class="cfield"><span>Soul inside</span>${pick('soul', 'a creature… (search); for soul gems')}<small>A filled soul gem: it holds that creature's soul for enchanting.</small></label>`;
  }
  if (!d.can_own && !d.can_lock && !d.uses_label && !d.can_soul) h += '<div class="msg">Nothing of this kind to set on this object.</div>';
  h += `<div class="actions"><button class="btn sm primary" id="rp-save" ${dirty ? '' : 'disabled'}>${dirty ? 'Save' : 'Saved'}</button>${dirty ? '<button class="btn sm" id="rp-undo">↺ Undo edits</button>' : ''}</div></div>`;
  box.innerHTML = h;
  const bind = (f, types) => {
    const inp = $('#rp-' + f); if (!inp) return;
    ddSearch('rp-' + f, types, r => { d[f] = r.id; d[f + '_name'] = r.name || ''; d[f + '_missing'] = false; if (f === 'faction'){ d.owner = d.owner && ''; } refPropsRender(); });
    inp.addEventListener('change', () => { d[f] = inp.value.trim(); d[f + '_missing'] = false; d[f + '_name'] = ''; if (f === 'faction' && !d[f]) d.rank = 0; refPropsRender(); });
  };
  bind('owner', 'NPC_'); bind('faction', 'FACT'); bind('global', 'GLOB'); bind('key', 'MISC'); bind('trap', 'SPEL'); bind('soul', 'CREA');
  const rk = $('#rp-rank'); if (rk) rk.onchange = () => { d.rank = +rk.value; refPropsRender(); };
  const lk = $('#rp-lock'); if (lk) lk.onchange = () => { d.lock = Math.max(0, +lk.value || 0); refPropsRender(); };
  const us = $('#rp-uses'); if (us) us.onchange = () => { d.uses = us.value === '' ? null : Math.max(0, +us.value || 0); refPropsRender(); };
  $('#rp-close').onclick = () => { RP.open = false; refPropsRender(); };
  const un = $('#rp-undo'); if (un) un.onclick = () => { RP.data = JSON.parse(RP.orig); refPropsRender(); };
  $('#rp-save').onclick = async () => {
    if (!await needProject()) return;
    const cell = RP.cell, k = RP.k;
    const data = {owner: d.owner, faction: d.faction, rank: d.rank, global: d.global, soul: d.soul, lock: d.lock, key: d.key, trap: d.trap, uses: d.uses};
    if (data.faction && data.owner){ toast('Pick either a person or a faction as the owner, not both.'); return; }
    try {
      const m = await refAction('/api/ref/props', {cell, ref: k, data}, cell, k, 'Saved');
      if (m && m.props){ RP.data = m.props; RP.orig = JSON.stringify(m.props); }
      refPropsRender();
    } catch (e){ toast(e.message, true); }
  };
}
