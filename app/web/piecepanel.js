// ---------- Pieces: the prefab workbench's shelf as a panel of the World ----------
// The same style shelves (the game's building pieces of a style, by kind, most used first) and "All pieces, by ID"
// (every static and door with what's typed in its ID, kinds to toggle), beside the map and the 3D view. Click a
// piece to place it, click again to stop; or drag it into the view. Optional: open it from Panels. PIN2 on Discord
// (2026-11-02): "add that menu on the left of the prefab menu to the 3D view but have it optional ... act the exact same
// way. Would make main world editing so much easier. Going back and forth between browse and style gets a bit tiresome".
const PCP = {style: null, browse: false, q: '', kinds: null, shelf: null, all: null, allAsk: null, it: null, open: new Set(['wall', 'door'])};
try { const s = JSON.parse(localStorage.getItem('ws-pieces') || '{}'); PCP.style = s.style || null; PCP.browse = !!s.browse; PCP.kinds = s.kinds ? new Set(s.kinds) : null; } catch (e){}
const PCP_KINDS = [['DOOR', 'Doors'], ['STAT', 'Statics'], ['ACTI', 'Activators'], ['LIGH', 'Lights'], ['CONT', 'Containers'], ['MISC', 'Odds and ends']];
const PCP_PAGE = 600;

function pcpPanels(){
  PNL.define('world', 'pieces', {title: 'Pieces', icon: '🧱', home: 'left', w: 300, cls: 'wside ppanel', render: pcpRender, onShow: pcpRender});
}
function pcpKeep(){ try { localStorage.setItem('ws-pieces', JSON.stringify({style: PCP.style, browse: PCP.browse, kinds: PCP.kinds ? [...PCP.kinds] : null})); } catch (e){} }
function pcpCss(){
  if ($('#pcp-css')) return;
  const c = document.createElement('style'); c.id = 'pcp-css';
  c.textContent = `.pbody.ppanel .ppgrid{display:grid!important;grid-template-columns:repeat(auto-fill,minmax(76px,1fr));gap:4px;margin:4px 0}
  .pbody.ppanel .pppc{display:block;border:1px solid var(--line);border-radius:6px;background:var(--panel2);padding:3px;cursor:grab;text-align:center;font-size:10.5px;overflow:hidden}
  .ppanel .pppc:hover{border-color:var(--gold)}.ppanel .pppc.placing{border-color:var(--gold);box-shadow:0 0 0 1px var(--gold) inset}
  .ppanel .pppc img{width:100%;aspect-ratio:1;object-fit:contain;display:block}
  .ppanel .pppc{position:relative}.ppanel .ppeye{position:absolute;right:2px;top:2px;padding:0 3px;font-size:11px;line-height:16px;border:1px solid var(--line);
    border-radius:4px;background:var(--panel);color:var(--text);cursor:pointer;display:none}.ppanel .pppc:hover .ppeye{display:block}
  .ppanel .pppc span{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--text-b)}
  .ppanel .ppkinds{display:flex;flex-wrap:wrap;gap:3px;margin:2px 0 6px}.ppanel .ppkinds .btn{padding:1px 6px;font-size:11px}
  .ppanel .ppkinds .btn.on{background:var(--gold);color:#111}
  .ppanel details summary{cursor:pointer;margin:4px 0;color:var(--muted)}`;
  document.head.appendChild(c);
}

async function pcpRender(it){
  if (it) PCP.it = it;
  const b = PCP.it && PCP.it.el; if (!b) return;
  pcpCss();
  if (!b.querySelector('#pcp-list')){
    b.innerHTML = `<div class="pfrow" style="display:flex;gap:6px;align-items:center"><label class="msg">Style <select id="pcp-style" class="inp" style="width:auto"></select></label></div>
      <input id="pcp-q" class="inp" placeholder="Find a piece…" style="width:100%;margin-top:6px" value="${esc(PCP.q)}">
      <div class="msg" style="margin:4px 0">Click one, then click where it goes; or drag it into the view.</div>
      <div id="pcp-list"></div>`;
    const q = b.querySelector('#pcp-q');
    q.oninput = () => { PCP.q = q.value; pcpList(); };
    q.onkeydown = e => e.stopPropagation();
  }
  await pcpStyles();
}

async function pcpStyles(){
  const b = PCP.it.el, sel = b.querySelector('#pcp-style'), list = b.querySelector('#pcp-list');
  let st;
  try { st = (await api('/api/build/modules')).styles || {}; }
  catch (e){ list.innerHTML = `<div class="msg">${/still learning/i.test(e.message) ? 'Learning the game\'s buildings (a few minutes, once)…' : esc(e.message)}</div>`; setTimeout(() => { if (PCP.it && PCP.it.el.isConnected) pcpStyles(); }, 5000); return; }
  const names = Object.keys(st).sort((a, z) => st[z] - st[a]);
  if (!PCP.style || !names.includes(PCP.style)) PCP.style = names[0] || 'Hlaalu';
  sel.innerHTML = `<option value="*all*" ${PCP.browse ? 'selected' : ''}>All pieces, by ID</option>` +
    names.map(n => `<option ${!PCP.browse && n === PCP.style ? 'selected' : ''}>${esc(n)}</option>`).join('');
  sel.onchange = () => { if (sel.value === '*all*') PCP.browse = true; else { PCP.browse = false; PCP.style = sel.value; PCP.shelf = null; } pcpKeep(); pcpList(); };
  pcpList();
}

function pcpTile(id, tag, tip){
  const on = W.mode === 'place' && W.placeId && W.placeId.toLowerCase() === id.toLowerCase();
  return `<div class="pppc ${on ? 'placing' : ''}" draggable="true" data-pid="${esc(id)}" data-pname="${esc(id)}" data-ptype="${esc(tag)}" title="${esc(tip)}">
    <button class="ppeye" title="See it in use: the game's buildings that use it, in the workbench">👁</button><img data-tid="${esc(id)}" data-ts="64" data-tt="${esc(tag)}" alt=""><span>${esc(id)}</span></div>`;
}

async function pcpList(){
  const b = PCP.it && PCP.it.el; if (!b) return;
  const list = b.querySelector('#pcp-list'); if (!list) return;
  const q = PCP.q.trim().toLowerCase();
  if (PCP.browse) return pcpBrowse(list, q);
  if (!PCP.shelf || PCP.shelf.style !== PCP.style){
    list.innerHTML = '<div class="msg">Reading the pieces…</div>';
    try { PCP.shelf = await api('/api/bench/shelf?style=' + encodeURIComponent(PCP.style)); } catch (e){ list.innerHTML = `<div class="msg">${esc(e.message)}</div>`; return; }
  }
  list.innerHTML = PCP.shelf.kinds.map(k => {
    const ps = k.pieces.filter(p => !q || p.id.toLowerCase().includes(q));
    if (!ps.length) return '';
    return `<details data-ppk="${k.kind}" ${q || PCP.open.has(k.kind) ? 'open' : ''}><summary>${esc(k.label)} <span class="msg">${ps.length}</span></summary>
      <div class="ppgrid">${ps.map(p => pcpTile(p.id, p.tag, `${p.id}: the game uses it ${p.n}×. Click, then click where it goes; or drag it into the view.`)).join('')}</div></details>`;
  }).join('') || `<div class="msg">No piece by that name on the ${esc(PCP.style)} shelf. "All pieces, by ID" looks through every one.</div>`;
  pcpBind(list);
}

function pcpBrowse(list, q){
  PCP.kinds = PCP.kinds || new Set(['STAT', 'DOOR']);
  const kinds = `<div class="ppkinds">${PCP_KINDS.map(([t, l]) => `<button class="btn sm ${PCP.kinds.has(t) ? 'on' : ''}" data-ppkind="${t}" title="Show or hide ${l.toLowerCase()}. Ctrl-click: only these">${l}</button>`).join('')}</div>`;
  if (q.length < 2){ list.innerHTML = kinds + '<div class="msg">Type an ID or the start of one: ex_imp_wall, t_imp_set, in_dwrv…</div>'; pcpBind(list); return; }
  if (!(PCP.all && PCP.all.q === q)){
    list.innerHTML = kinds + '<div class="msg">Looking through every piece…</div>'; pcpBind(list);
    if (PCP.allAsk === q) return;
    PCP.allAsk = q; pcpPage(q, 0); return;
  }
  const rows = PCP.all.rows;
  list.innerHTML = kinds + (PCP_KINDS.map(([t, l]) => {
    const ps = rows.filter(r => r.type === t);
    return ps.length ? `<details data-ppk="all-${t}" open><summary>${l} <span class="msg">${ps.length}</span></summary>
      <div class="ppgrid">${ps.map(r => pcpTile(r.id, r.type, `${r.id}${r.name ? ' (' + r.name + ')' : ''}. Click, then click where it goes; or drag it into the view.`)).join('')}</div></details>` : '';
  }).join('') || '<div class="msg">No piece by that ID.</div>') + (PCP.all.total > rows.length
    ? `<div class="msg" style="margin:6px 0">${rows.length} of ${PCP.all.total}. <button class="btn sm" id="pcp-more">Show ${Math.min(PCP_PAGE, PCP.all.total - rows.length)} more</button></div>` : '');
  pcpBind(list);
  const more = list.querySelector('#pcp-more'); if (more) more.onclick = () => { more.disabled = true; pcpPage(q, rows.length); };
}

function pcpPage(q, offset){
  const kinds = PCP_KINDS.map(k => k[0]).filter(t => PCP.kinds.has(t));
  api('/api/search?' + new URLSearchParams({q, types: kinds.join(','), limit: PCP_PAGE, offset, sort: 'id'})).then(r => {
    const got = (r.rows || []).filter(x => kinds.includes(x.type));
    PCP.all = {q, rows: offset && PCP.all && PCP.all.q === q ? PCP.all.rows.concat(got) : got, total: r.total || 0};
    if (PCP.browse && PCP.q.trim().toLowerCase() === q) pcpList();
  }).catch(e => { PCP.allAsk = null; const l = PCP.it && PCP.it.el.querySelector('#pcp-list'); if (l) l.innerHTML = `<div class="msg">${esc(e.message)}</div>`; });
}

// (the workbench shows a piece in the game's buildings, one at a time: opened for that, the world left as it is)
async function pcpSeeInUse(id){
  if (typeof benchOpen !== 'function') return;
  await benchOpen(); benchExample(id);
}

function pcpBind(list){
  list.querySelectorAll('[data-ppkind]').forEach(b => b.onclick = e => {
    const t = b.dataset.ppkind;
    if (e.ctrlKey || e.metaKey) PCP.kinds = new Set([t]);
    else if (PCP.kinds.has(t) && PCP.kinds.size > 1) PCP.kinds.delete(t); else PCP.kinds.add(t);
    PCP.all = null; PCP.allAsk = null; pcpKeep(); pcpList();
  });
  list.querySelectorAll('details').forEach(d => d.ontoggle = () => { if (d.open){ PCP.open.add(d.dataset.ppk); v3ThumbScan(d); } else PCP.open.delete(d.dataset.ppk); });
  list.querySelectorAll('details[open]').forEach(d => v3ThumbScan(d));
  // (a click starts placing it, again stops: the world's own tile click does that for every [data-pid] in #world;
  // here too when the panel floats outside it)
  list.querySelectorAll('.pppc').forEach(el => {
    el.querySelector('.ppeye').onclick = e => { e.stopPropagation(); pcpSeeInUse(el.dataset.pid); };
    el.onclick = e => {
      e.stopPropagation();
      if (W.mode === 'place' && W.placeId && W.placeId.toLowerCase() === el.dataset.pid.toLowerCase()) setMode(null);
      else setMode('place', {id: el.dataset.pid, name: el.dataset.pname, type: el.dataset.ptype});
      list.querySelectorAll('.pppc').forEach(x => x.classList.toggle('placing', W.mode === 'place' && W.placeId === x.dataset.pid));
    };
    el.oncontextmenu = e => {
      e.preventDefault();
      pnlMenu({x: e.clientX, y: e.clientY}, [{label: el.dataset.pid, disabled: true},
        {label: '📍 Place it', act: () => setMode('place', {id: el.dataset.pid, name: el.dataset.pname, type: el.dataset.ptype})},
        {label: '👁 See it in use', act: () => pcpSeeInUse(el.dataset.pid)},
        {label: '🔎 Open its record', act: () => { showView('browse'); S.q = el.dataset.pid; S.types = []; runSearch(); }},
        {label: '🔨 Put it on the workbench', act: async () => { if (typeof benchOpen === 'function'){ await benchOpen(); await benchAddAt(el.dataset.pid, el.dataset.ptype, null); } }}]);
    };
  });
}
