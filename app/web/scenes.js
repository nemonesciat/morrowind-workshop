// ---------- Scenes: the mod's cutscenes (made in a connected program: bridge.py), listed on the Scripts page ----------
// The scene itself is edited where it was made; here the user picks what starts it in the game (scenes.py plays it).
const SCN = {list: null, open: null, kinds: {}};

async function scnMine(){
  const box = $('#s-scenes'); if (!box) return;
  if (!S.summary || !S.summary.project){ box.innerHTML = ''; return; }
  try { SCN.list = await api('/api/scenes'); } catch (e){ box.innerHTML = `<div class="msg">${esc(e.message)}</div>`; return; }
  SCN.kinds = SCN.list.triggers || {};
  const l = SCN.list.scenes || [];
  box.innerHTML = l.length ? l.map(s => `<div class="drow ${SCN.open === s.scene ? 'on' : ''}" data-scnopen="${esc(s.scene)}"><span>🎬 ${esc(s.name)}</span>
      <small>${s.trigger ? esc({area: 'near a spot', quest: 'quest stage', global: 'global'}[s.trigger.kind] || '') : 'when asked'}</small></div>`).join('')
    : '<div class="msg" style="padding:4px 2px" title="A modding program connected to the Workshop (Settings › Connected programs) sends them here">Scenes made in a connected program show here.</div>';
  box.querySelectorAll('[data-scnopen]').forEach(r => r.onclick = () => scnOpen(r.dataset.scnopen));
}

function scnOpen(id){
  const s = ((SCN.list && SCN.list.scenes) || []).find(x => x.scene === id);
  if (!s) return;
  SCN.open = id; SC.id = null; if (typeof LU !== 'undefined'){ LU.name = null; LU.data = null; }
  const tr = s.trigger || {}, kind = tr.kind || '';
  const cell = Array.isArray(s.cell) ? `${s.cell[0]}, ${s.cell[1]}` : (s.cell || '');
  const c = tr.center || [], num = (v, d) => v == null ? d : v;
  $('#smain').innerHTML = `<div class="wrap" style="max-width:760px"><h1>🎬 ${esc(s.name)}</h1>
    <p class="msg">${esc(cell)} · ${num(s.length, 0)} s · ${s.actors} actor${s.actors === 1 ? '' : 's'} · ${s.shots} shot${s.shots === 1 ? '' : 's'}</p>
    ${SCN.list.lua_ok ? '' : '<p class="msg sev-warning">Scenes play only in an .omwaddon mod (File › Save as…).</p>'}
    <h3>Starts when</h3>
    <div class="frow"><label>When</label><select class="inp" id="scn-kind" style="max-width:320px">
      <option value="">Only when asked (another script)</option>
      <option value="area" ${kind === 'area' ? 'selected' : ''}>The player comes near a spot</option>
      <option value="quest" ${kind === 'quest' ? 'selected' : ''}>A quest reaches a stage</option>
      <option value="global" ${kind === 'global' ? 'selected' : ''} title="Set it from a dialogue result or MWScript: set name to 1">A global variable is set to 1</option></select></div>
    <div id="scn-area" class="frow" style="display:none"><label>Spot</label><span><input class="inp num" id="scn-x" value="${num(c[0], '')}" placeholder="x" style="width:90px">
      <input class="inp num" id="scn-y" value="${num(c[1], '')}" placeholder="y" style="width:90px"> <input class="inp num" id="scn-z" value="${num(c[2], 0)}" placeholder="z" style="width:70px">
      within <input class="inp num" id="scn-r" value="${num(tr.radius, 300)}" style="width:70px"> units</span></div>
    <div id="scn-quest" class="frow" style="display:none"><label>Quest</label><span><input class="inp" id="scn-q" value="${esc(tr.quest || '')}" placeholder="quest ID" style="max-width:220px">
      stage <input class="inp num" id="scn-st" value="${num(tr.stage, 10)}" style="width:70px"></span></div>
    <div id="scn-global" class="frow" style="display:none"><label>Global</label><input class="inp" id="scn-g" value="${esc(tr.name || '')}" placeholder="global variable" style="max-width:220px"></div>
    <label class="msg" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="scn-once" ${tr.once === false ? '' : 'checked'}> Only once a game</label>
    <div class="actions"><button class="btn primary" id="scn-save">Save</button><button class="btn" id="scn-del" title="Remove the scene from your mod (Undo brings it back)">Remove scene</button><span class="msg" id="scn-msg"></span></div></div>`;
  const show = () => { const k = $('#scn-kind').value; ['area', 'quest', 'global'].forEach(n => $('#scn-' + n).style.display = k === n ? '' : 'none'); };
  $('#scn-kind').onchange = show; show();
  $('#scn-save').onclick = async () => {
    const k = $('#scn-kind').value, once = $('#scn-once').checked;
    const t = !k ? null : k === 'area' ? {kind: k, center: [+$('#scn-x').value, +$('#scn-y').value, +$('#scn-z').value || 0], radius: +$('#scn-r').value || 300, once}
      : k === 'quest' ? {kind: k, quest: $('#scn-q').value.trim(), stage: +$('#scn-st').value, once}
      : {kind: k, name: $('#scn-g').value.trim(), value: 1, once};
    if (k === 'area' && ($('#scn-x').value === '' || $('#scn-y').value === '')){ $('#scn-msg').className = 'msg err'; $('#scn-msg').textContent = 'Give the spot.'; return; }
    try { await post('/api/scenes/trigger', {scene: id, trigger: t}); afterChange(); toast('Saved.'); await scnMine(); scnOpen(id); }
    catch (e){ $('#scn-msg').className = 'msg err'; $('#scn-msg').textContent = e.message; }
  };
  $('#scn-del').onclick = async () => {
    try { await post('/api/scenes/delete', {scene: id}); afterChange(); SCN.open = null; await scnMine(); sWelcome(); toast('Scene removed: Undo brings it back.'); }
    catch (e){ toast(e.message, true); }
  };
  scnMine();
}
