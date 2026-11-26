// Object lists: everything that can go into a place, one list per kind (Static, Door, Light, NPC…), in the
// panels of the World map. Drag a row onto the map or the 3D view, or double-click it to place it; right-click
// for more. Sorted by a click on a column; the lists load more as they are scrolled. Several can be open at
// once, each on its own kind (a tester used to the old editor, 2026-11-26: "lists callable for every type of
// object that can go into the map").
const OL_TYPES = [['', 'All'], ['STAT', 'Static'], ['ACTI', 'Activator'], ['DOOR', 'Door'], ['CONT', 'Container'], ['LIGH', 'Light'],
  ['NPC_', 'NPC'], ['CREA', 'Creature'], ['LEVC', 'Leveled creature'], ['LEVI', 'Leveled item'], ['WEAP', 'Weapon'], ['ARMO', 'Armor'],
  ['CLOT', 'Clothing'], ['BOOK', 'Book'], ['INGR', 'Ingredient'], ['ALCH', 'Potion'], ['APPA', 'Apparatus'], ['LOCK', 'Lockpick'],
  ['PROB', 'Probe'], ['REPA', 'Repair'], ['MISC', 'Misc']];
const OL_ALL = OL_TYPES.slice(1).map(t => t[0]).join(',');
const OL_LABEL = Object.fromEntries(OL_TYPES.map(([k, v]) => [k, v]));

function olCss(){
  if ($('#ol-css')) return;
  const c = document.createElement('style'); c.id = 'ol-css';
  c.textContent = `
  .ol{display:flex;flex-direction:column;height:100%;min-height:0;font-size:12.5px}
  .ol-types{display:flex;flex-wrap:wrap;gap:2px;padding:6px 6px 4px}
  .ol-types button{background:none;border:1px solid var(--line);border-radius:5px;color:var(--muted);padding:2px 6px;font:inherit;font-size:11.5px;cursor:pointer}
  .ol-types button:hover{color:var(--text);border-color:var(--line2)}
  .ol-types button.on{color:var(--gold2);border-color:var(--gold);background:#ffffff08}
  .ol-bar{display:flex;gap:4px;align-items:center;padding:0 6px 4px}
  .ol-bar input{flex:1;min-width:0}
  .ol-bar .n{color:var(--faint);font-size:11px;white-space:nowrap}
  .ol-head,.ol-r{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(0,1fr) 40px minmax(0,.75fr);gap:6px;padding:2px 8px;align-items:center}
  .ol-head{color:var(--faint);font-size:11px;border-bottom:1px solid var(--line);user-select:none}
  .ol-head span{cursor:pointer;white-space:nowrap;overflow:hidden}
  .ol-head span:hover{color:var(--text)}
  .ol-head span.on{color:var(--gold2)}
  .ol-rows{flex:1;min-height:0;overflow:auto}
  .ol-r{cursor:grab;border-bottom:1px solid #ffffff06}
  .ol-r > *{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .ol-r:hover{background:#ffffff0a}
  .ol-r.on{background:color-mix(in srgb,var(--gold) 22%,transparent)}
  .ol-r .u{text-align:right;color:var(--faint)}
  .ol-r .m{color:var(--faint)}
  .ol-r.mine .m{color:var(--gold2)}`;
  document.head.appendChild(c);
}

// the list's settings: kept with each list (the first one's in the browser, the others' with the layout)
function olState(it){
  if (it.id === 'olist' && !it.state.type && !it.state.loaded){
    try { Object.assign(it.state, JSON.parse(localStorage.getItem('ws-olist') || '{}')); } catch (e){}
    it.state.loaded = true;
  }
  const st = it.state;
  if (st.type == null) st.type = 'STAT';
  if (st.sort == null) st.sort = 'id';
  return st;
}
function olKeep(it){
  if (it.id !== 'olist') return;
  const {type, sort, q, mine} = it.state;
  try { localStorage.setItem('ws-olist', JSON.stringify({type, sort, q, mine})); } catch (e){}
}

function olRender(it){
  olCss();
  const st = olState(it), el = it.el;
  const cols = [['id', 'ID'], ['name', 'Name'], ['uses', 'Used'], ['plugin', 'Mod']];
  el.innerHTML = `<div class="ol">
    <div class="ol-types">${OL_TYPES.map(([k, v]) => `<button data-olt="${k}" class="${st.type === k ? 'on' : ''}">${v}</button>`).join('')}</div>
    <div class="ol-bar"><button class="btn sm ${STAMP.on ? 'primary' : ''}" data-olstamp title="On: a click on a row picks it up to place, one click each; off: drag a row, or double-click it">✚ Place</button>
      <input class="inp" data-olq placeholder="Filter…" value="${esc(st.q || '')}">
      <label title="Only what your mod adds"><input type="checkbox" data-olmine ${st.mine ? 'checked' : ''}> Mine</label><span class="n" data-oln></span></div>
    ${STAMP.on ? `<div class="ol-bar"><label title="Stand it on the slope of the ground"><input type="checkbox" data-olstampo="lean" ${STAMP.lean ? 'checked' : ''}> Lean with the ground</label>
      <label title="Each one turned its own way"><input type="checkbox" data-olstampo="rand" ${STAMP.rand ? 'checked' : ''}> Random turn</label></div>` : ''}
    <div class="ol-head">${cols.map(([k, v]) => `<span data-ols="${k}" class="${(st.sort || '').replace('-', '') === k ? 'on' : ''}" title="Sort by ${v.toLowerCase()}">${v}${st.sort === k ? ' ▴' : st.sort === '-' + k ? ' ▾' : ''}</span>`).join('')}</div>
    <div class="ol-rows" data-olrows></div></div>`;
  el.querySelectorAll('[data-olt]').forEach(b => b.onclick = () => { st.type = b.dataset.olt; olKeep(it); PNL.retitle('world', it.id); olRender(it); });
  el.querySelectorAll('[data-ols]').forEach(b => b.onclick = () => {
    const k = b.dataset.ols;
    st.sort = k === 'uses' ? 'uses' : st.sort === k ? '-' + k : k;
    olKeep(it); olRender(it);
  });
  el.querySelector('[data-olstamp]').onclick = () => {
    STAMP.on = !STAMP.on; stampSave();
    if (!STAMP.on && W.mode === 'place') setMode(null);
    for (const x of PNL.all('world', 'olist')) olRender(x);
  };
  el.querySelectorAll('[data-olstampo]').forEach(c => c.onchange = () => { STAMP[c.dataset.olstampo] = c.checked; stampSave(); stampRedraw(); });
  const q = el.querySelector('[data-olq]');
  q.oninput = () => { st.q = q.value; olKeep(it); clearTimeout(it.olT); it.olT = setTimeout(() => olLoad(it, true), 220); };
  el.querySelector('[data-olmine]').onchange = e => { st.mine = e.target.checked; olKeep(it); olLoad(it, true); };
  const rows = el.querySelector('[data-olrows]');
  rows.onscroll = () => { if (rows.scrollTop + rows.clientHeight > rows.scrollHeight - 300) olLoad(it, false); };
  olLoad(it, true);
}

async function olLoad(it, fresh){
  const st = it.state, el = it.el, rows = el.querySelector('[data-olrows]');
  if (!rows) return;
  if (fresh){ it.olRows = []; it.olTotal = null; it.olSeq = (it.olSeq || 0) + 1; rows.innerHTML = '<div class="msg" style="padding:8px"><span class="spin"></span></div>'; }
  else if (it.olBusy || (it.olTotal != null && it.olRows.length >= it.olTotal)) return;
  const seq = it.olSeq;
  it.olBusy = true;
  let plugin = '';
  if (st.mine){
    const pr = S.summary && S.summary.project;
    if (!pr || pr.pidx == null){ it.olBusy = false; rows.innerHTML = '<div class="msg" style="padding:8px">Open or start a mod first.</div>'; return; }
    plugin = String(pr.pidx);
  }
  let r;
  try {
    r = await api('/api/search?' + new URLSearchParams({q: st.q || '', types: st.type || OL_ALL, plugin, offset: it.olRows.length, limit: 200, sort: st.sort || 'id'}));
  } catch (e){ it.olBusy = false; rows.innerHTML = `<div class="msg" style="padding:8px">${esc(e.message)}</div>`; return; }
  it.olBusy = false;
  if (seq !== it.olSeq) return;
  const first = !it.olRows.length;
  it.olRows = it.olRows.concat(r.rows); it.olTotal = r.total;
  const n = el.querySelector('[data-oln]'); if (n) n.textContent = fmtN(r.total);
  const html = r.rows.map((x, j) => {
    const k = it.olRows.length - r.rows.length + j;
    return `<div class="ol-r ${x.mine ? 'mine' : ''}" draggable="true" data-olr="${k}" title="${esc(x.id)}${x.name ? ' · ' + esc(x.name) : ''}${x.extra ? '\n' + esc(x.extra) : ''}\nDrag onto the map, or double-click to place">
      <span>${esc(x.id)}</span><span>${esc(x.name || '')}</span><span class="u">${x.uses || ''}</span><span class="m">${esc(x.plugin)}</span></div>`;
  }).join('');
  if (first) rows.innerHTML = html || '<div class="msg" style="padding:8px">Nothing here.</div>';
  else rows.insertAdjacentHTML('beforeend', html);
  olBind(it, rows);
}

function olBind(it, rows){
  rows.querySelectorAll('[data-olr]:not([data-b])').forEach(row => {
    row.dataset.b = '1';
    const x = it.olRows[+row.dataset.olr];
    row.onclick = () => {
      const was = row.classList.contains('on');
      rows.querySelectorAll('.ol-r.on').forEach(r => r.classList.remove('on')); row.classList.add('on');
      // (✚ Place on: the click picks it up; again on the same row puts it down)
      if (STAMP.on){ if (was && W.mode === 'place' && W.placeId === x.id){ setMode(null); row.classList.remove('on'); } else olPlace(x); }
    };
    row.ondblclick = () => olPlace(x);
    row.ondragstart = e => {
      e.dataTransfer.setData('text/x-mw-id', x.id); e.dataTransfer.setData('text/x-mw-name', x.name || x.id);
      e.dataTransfer.effectAllowed = 'copy';
    };
    row.oncontextmenu = e => {
      e.preventDefault(); rows.querySelectorAll('.ol-r.on').forEach(r => r.classList.remove('on')); row.classList.add('on');
      pnlMenu(row, [
        {label: '✚ Place it', act: () => olPlace(x)},
        {label: '📄 Open its record', act: () => openRecord(x.i)},
        {label: '📋 This kind in a list of its own', act: () => PNL.open('world', 'olist', {type: x.type, sort: 'id'})},
      ]);
    };
  });
}

function olPlace(x){
  if (!W.key){ toast('Open a place first.', true); return; }
  setMode('place', {id: x.id, name: x.name || x.id, type: x.type});
}

// the panel, on the World map (worldpanels.js calls this once its space is made)
function olPanels(){
  PNL.define('world', 'olist', {title: 'Object list', icon: '📋', home: 'left', multi: true, w: 380, h: 560,
    cloneState: it => ({type: it.state.type, sort: it.state.sort}),
    titleFor: it => { const k = it.state && it.state.type != null ? it.state.type : 'STAT'; return k ? OL_LABEL[k] || 'Object list' : 'All objects'; },
    render: it => olRender(it), onShow: it => { if (!it.el.querySelector('.ol')) olRender(it); }});
}
