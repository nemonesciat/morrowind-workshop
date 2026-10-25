// The Style palette: a window over the World map that sorts the game's building pieces, furniture, decor
// and sets by theme (Hlaalu, Redoran, Telvanni, Velothi, Nord, Imperial, the Legion, Gold Coast...) and by how
// they're used together, for someone who has never built and wants to know what goes with what. Learnt
// from the game's own places (stylesurvey.py): each place is a greenlist of what's in it, and a thing goes
// with a theme when the theme's places hold it far more often than places in general. Each piece shows how
// often the theme's places hold it (staples first); resting the mouse on it shows what the game stands next
// to it, puts on it or joins to it. Click to place it, or drag it into the map or the 3D view; a set goes
// down whole, as one Undo. Two views of the same lists: pictures, and a tree.
const SP = {themes: null, cur: null, data: {}, q: '', view: 'grid', fits: false, here: null, open: {Shell: true, Furniture: true, Decor: true, Sets: true}};
try { Object.assign(SP, JSON.parse(localStorage.getItem('ws-stylepal') || '{}') || {}); } catch (e){}
SP.data = {}; SP.themes = null;
const SP_SECS = [['Shell', '🧱 Shell', 'Walls, corners, floors, ceilings, doorways, stairs, columns: what the place is built of'],
  ['Furniture', '🪑 Furniture', 'Beds, tables, seats, storage, counters and shelves'],
  ['Decor', '🕯 Decor', 'Lights, rugs, tapestries and banners, plants, tableware and clutter'],
  ['Sets', '🧩 Sets', 'What the game puts together: a table with its chairs, a bed with its chest, a hearth with its things. Placed whole, one Undo']];
const SP_HOW = {next: 'stands next to it', on: 'on it', under: 'it stands on', joins: 'joins it'};
function spKeep(){ try { localStorage.setItem('ws-stylepal', JSON.stringify({cur: SP.cur, view: SP.view, fits: SP.fits, open: SP.open})); } catch (e){} }

function spCss(){
  if (typeof owCss === 'function') owCss();
  if (typeof vwCss === 'function') vwCss();
  if ($('#sp-css')) return;
  const c = document.createElement('style'); c.id = 'sp-css';
  c.textContent = `
  .spwin .vwbody{display:flex;min-height:0}
  .sp-tabs{width:168px;flex:none;overflow:auto;border-right:1px solid var(--line);padding:6px 0;background:var(--bg3-b)}
  .sp-tabs button{display:flex;justify-content:space-between;gap:6px;width:100%;text-align:left;background:none;border:0;color:var(--text);padding:5px 10px;font:inherit;cursor:pointer;border-left:3px solid transparent}
  .sp-tabs button:hover{background:var(--panel2)}
  .sp-tabs button.on{border-left-color:var(--gold);background:var(--panel2);color:var(--gold2);font-weight:600}
  .sp-tabs button small{color:var(--faint);font-weight:400}
  .sp-tabs .sp-hd{font-size:11px;color:var(--faint);padding:8px 10px 2px;text-transform:uppercase;letter-spacing:.04em}
  .sp-main{flex:1;min-width:0;overflow:auto;padding:8px 12px 24px}
  .sp-bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:6px}
  .sp-bar .inp{flex:1;min-width:140px}
  .sp-bar label{display:flex;gap:4px;align-items:center;font-size:12px;color:var(--muted);white-space:nowrap}
  .sp-line{color:var(--muted);font-size:12px;margin:0 0 8px}
  .sp-sec{margin:0 0 6px}
  .sp-sec > summary{cursor:pointer;font-weight:600;font-size:14px;padding:4px 0;color:var(--gold2)}
  .sp-sec > summary small{color:var(--faint);font-weight:400;margin-left:6px}
  .sp-grp{font-size:12px;color:var(--muted);margin:8px 0 2px}
  .sp-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(92px,1fr));gap:6px}
  .sp-grid .tile{padding:3px 3px 4px;font-size:11.5px}
  .sp-grid .tile .thumb{width:100%;height:auto;aspect-ratio:1}
  .sp-grid .tile span{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .sp-badge{position:absolute;top:3px;left:3px;font-size:10.5px;padding:0 4px;border-radius:4px;background:color-mix(in srgb,var(--panel) 80%,transparent);color:var(--muted)}
  .sp-badge.staple{color:var(--bg);background:var(--gold)}
  .sp-sets{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:8px}
  .sp-set{border:1px solid var(--line);background:var(--panel2);border-radius:8px;padding:6px;cursor:grab;user-select:none}
  .sp-set:hover,.sp-grid .tile:hover{border-color:var(--goldline)}
  .sp-set .sp-strip{display:flex;gap:2px;align-items:flex-end}
  .sp-set .sp-strip .thumb{width:48px;height:48px}
  .sp-set .sp-strip .thumb:first-child{width:72px;height:72px}
  .sp-set b{display:block;font-size:12.5px;margin-top:4px}
  .sp-set .msg{font-size:11.5px}
  .sp-tree{font-size:12.5px}
  .sp-tree details{margin-left:12px}
  .sp-tree summary{cursor:pointer;padding:2px 0}
  .sp-tree .sp-row{display:flex;gap:6px;align-items:center;padding:1px 0 1px 14px;cursor:grab}
  .sp-tree .sp-row:hover{background:var(--panel2)}
  .sp-tree .sp-row .thumb{width:28px;height:28px}
  .sp-tree .sp-row small{color:var(--faint)}
  .sp-card{position:fixed;z-index:200;width:300px;background:var(--panel);border:1px solid var(--line2);border-radius:10px;box-shadow:0 14px 44px #000b;padding:10px;font-size:12.5px;display:none}
  .sp-card .thumb{width:120px;height:120px;float:right;margin:0 0 6px 8px}
  .sp-card h4{margin:0 0 2px;font-size:14px}
  .sp-card .sp-goes{clear:both;display:grid;grid-template-columns:36px 1fr;gap:3px 6px;align-items:center;margin-top:6px}
  .sp-card .sp-goes .thumb{width:36px;height:36px;float:none;margin:0}
  .sp-card .sp-goes span small{display:block;color:var(--faint)}
  .sp-wait{padding:20px}`;
  document.head.appendChild(c);
}

// ---------------------------------------------------------------- the window
VW_HOST.stylepal = {title: () => '🎨 Style palette' + (SP.cur ? ': ' + (SP.cur === '*' ? 'Used everywhere' : SP.cur) : ''), render: () => spRender(), w: 900};
function spWin(){ return VW.wins.stylepal && VW.wins.stylepal.el.isConnected ? VW.wins.stylepal : null; }
async function spOpen(theme){
  if (!cfWorldOn()) showView('world');
  spCss();
  let w = spWin();
  if (!w){
    const box = vwBox(); if (!box) return;
    const el = document.createElement('div'); el.className = 'owin vwin spwin'; el.dataset.vw = 'stylepal';
    el.setAttribute('data-ownkeys', '');
    el.innerHTML = `<div class="owhead"><span class="owtitle"></span>
        <button class="btn sm" data-vwclose title="Close (Esc)">✕</button></div>
      <div class="vwbody"><div class="sp-tabs"></div><div class="sp-main"></div></div>`;
    box.appendChild(el);
    w = VW.wins.stylepal = {v: 'stylepal', el, home: null};
    el.querySelector('[data-vwclose]').onclick = () => vwClose('stylepal');
    el.addEventListener('pointerdown', () => vwFront(el), true);
    el.addEventListener('keydown', e => { if (e.key !== 'Escape') e.stopPropagation(); });
    vwDrag(el, 'stylepal');
    const p = VW.pos.stylepal || {};
    el.style.width = Math.min(p.w || 900, box.clientWidth - 24) + 'px';
    el.style.height = Math.min(p.h || 620, box.clientHeight - 24) + 'px';
    w.pos = p.x != null ? {x: p.x, y: p.y} : {x: 24, y: 56};
    vwPlace(w);
    if (typeof ResizeObserver !== 'undefined'){
      let down = false;
      el.addEventListener('pointerdown', () => { down = true; window.addEventListener('pointerup', () => { down = false; }, {once: true}); });
      new ResizeObserver(() => { if (down && el.isConnected && el.offsetWidth) vwKeep('stylepal', {w: el.offsetWidth, h: el.offsetHeight}); }).observe(el);
    }
    spBind(el);
  }
  vwFront(w.el);
  if (theme) SP.cur = theme;
  vwTitle('stylepal');
  await spLoadThemes();
  spRender();
}

// the list of themes (and the open place's), waiting with a progress line while they're learnt
async function spLoadThemes(){
  const w = spWin(); if (!w) return;
  for (;;){
    let r;
    try { r = await api('/api/style/themes' + (W.key ? '?key=' + encodeURIComponent(W.key) : '')); } catch (e){ w.el.querySelector('.sp-main').innerHTML = `<div class="sp-wait msg">${esc(e.message)}</div>`; return; }
    if (r.ready){
      SP.themes = r.themes; SP.here = r.here || null; SP.hereKey = W.key;
      if (!SP.cur || (SP.cur !== '*' && !r.themes.some(t => t.name === SP.cur))) SP.cur = SP.here || r.themes[0].name;
      return;
    }
    const box = w.el.querySelector('.sp-main');
    box.innerHTML = '<div class="sp-wait" id="sp-wait"></div>';
    await waitForLearning(r.waiting, $('#sp-wait'), 'the palette fills in by itself');
    if (!spWin()) return;
  }
}
async function spTheme(name){
  if (SP.data[name]) return SP.data[name];
  const d = await api('/api/style/theme?name=' + encodeURIComponent(name));
  SP.data[name] = d;
  return d;
}

function spTabsHtml(){
  const t = SP.themes || [];
  const btn = (name, label, n, title) => `<button data-sptab="${esc(name)}" class="${SP.cur === name ? 'on' : ''}" title="${esc(title || '')}">${esc(label)}${n != null ? `<small>${fmtN(n)}</small>` : ''}</button>`;
  const list = SP.fits && SP.here ? t.filter(x => x.name === SP.here) : t;
  return `<div class="sp-hd">Styles${SP.fits && SP.here ? ' that fit here' : ''}</div>` +
    list.map(x => btn(x.name, (x.name === SP.here ? '◆ ' : '') + x.name, x.places, x.line + ` (${x.places} of the game's places)` + (x.name === SP.here ? '. The place open now is built in this style.' : ''))).join('') +
    `<div class="sp-hd">And</div>` + btn('*', 'Used everywhere', null, 'What the game stands in places of every style alike: crates, sacks, bread, the common clutter');
}

async function spRender(){
  const w = spWin(); if (!w || !SP.themes) return;
  // (the place changed under the window: its style, for the ◆ mark and "Only what fits here")
  if (SP.hereKey !== W.key){
    SP.hereKey = W.key;
    try { const r = await api('/api/style/themes' + (W.key ? '?key=' + encodeURIComponent(W.key) : '')); if (r.ready) SP.here = r.here || null; } catch (e){}
    if (SP.fits && SP.here) SP.cur = SP.here;
  }
  w.el.querySelector('.sp-tabs').innerHTML = spTabsHtml();
  vwTitle('stylepal');
  const main = w.el.querySelector('.sp-main');
  const bar = `<div class="sp-bar"><input class="inp" id="sp-q" placeholder="Search in this style… (bed, lantern, wall)" value="${esc(SP.q)}" autocomplete="off">
    <label title="Pictures, or the same lists as a tree"><select id="sp-view" class="inp" style="width:auto;padding:2px 6px"><option value="grid" ${SP.view === 'grid' ? 'selected' : ''}>Pictures</option><option value="tree" ${SP.view === 'tree' ? 'selected' : ''}>Tree</option></select></label>
    <label title="${SP.here ? 'Only the style the open place is built in: ' + esc(SP.here) : 'The open place has no style the game uses (or no place is open)'}"><input type="checkbox" id="sp-fits" ${SP.fits ? 'checked' : ''} ${SP.here ? '' : 'disabled'}> Only what fits here${SP.here ? ' (' + esc(SP.here) + ')' : ''}</label></div>`;
  let d;
  if (!SP.data[SP.cur]) main.innerHTML = bar + '<div class="msg">Loading…</div>';
  try { d = await spTheme(SP.cur); } catch (e){ main.innerHTML = bar + `<div class="msg">${esc(e.message)}</div>`; spBar(main); return; }
  if (!spWin()) return;
  const keepQ = document.activeElement && document.activeElement.id === 'sp-q' ? document.activeElement.selectionStart : null;
  main.innerHTML = bar + `<div class="sp-line">${esc(d.line)}. ${SP.cur === '*' ? '' : `Learnt from ${fmtN(d.places)} of the game's places.`}
      The badge is how many of them have it: <span class="sp-badge staple" style="position:static">40%</span> a staple, <span class="sp-badge" style="position:static">4%</span> now and then.
      ${d.examples && d.examples.length ? `<span class="lnk" data-spshow="${esc(d.examples[0][0])}" title="Open ${esc(d.examples[0][1])}, one of the game's own places in this style">Show me a place in this style</span>` : ''}</div>` +
    (SP.view === 'tree' ? spTreeHtml(d) : spGridHtml(d));
  spBar(main);
  if (keepQ != null){ const q = $('#sp-q'); q.focus(); q.setSelectionRange(keepQ, keepQ); }
  v3ThumbScan(main);
}
function spBar(main){
  const q = main.querySelector('#sp-q');
  let t; q.oninput = () => { clearTimeout(t); t = setTimeout(() => { SP.q = q.value; spRender(); }, 180); };
  main.querySelector('#sp-view').onchange = e => { SP.view = e.target.value; spKeep(); spRender(); };
  const f = main.querySelector('#sp-fits');
  f.onchange = () => { SP.fits = f.checked; if (SP.fits && SP.here) SP.cur = SP.here; spKeep(); spRender(); };
}

// what the search keeps: name or id words
function spMatch(it){
  const q = SP.q.trim().toLowerCase(); if (!q) return true;
  const s = ((it.name || '') + ' ' + it.id + ' ' + (it.grp || '')).toLowerCase();
  return q.split(/\s+/).every(w => s.includes(w));
}
function spSecs(d){
  // [section, label, title, groups] with the search applied (sets: matched by their label and members)
  return SP_SECS.map(([k, label, title]) => {
    if (k === 'Sets'){
      const q = SP.q.trim().toLowerCase();
      const sets = (d.sets || []).map((s, n) => Object.assign({n_: n}, s)).filter(s => !q || (s.label + ' ' + s.items.map(i => i.id).join(' ')).toLowerCase().includes(q));
      return [k, label, title, sets];
    }
    const groups = (d.sections[k] || []).map(g => ({group: g.group, items: g.items.filter(spMatch)})).filter(g => g.items.length);
    return [k, label, title, groups];
  });
}
function spBadge(it){
  const p = Math.round(100 * (it.share || 0));
  return `<b class="sp-badge${it.share >= 0.25 ? ' staple' : ''}" title="${SP.cur === '*' ? 'In ' + p + '% of all the places learnt from' : 'In ' + it.places + ' of the ' + esc(SP.cur) + ' places learnt from (' + p + '%)'}">${p < 1 ? '<1' : p}%</b>`;
}
function spTileHtml(it){
  return `<div class="tile" draggable="true" data-pid="${esc(it.id)}" data-pname="${esc(it.name || it.id)}" data-ptype="${esc(it.type || '')}" data-spid="${esc(it.id)}">${thumbImg(it.id, it.type, 96)}<span>${esc(it.name || it.id)}</span>${spBadge(it)}</div>`;
}
function spGridHtml(d){
  let any = false;
  const h = spSecs(d).map(([k, label, title, groups]) => {
    if (!groups.length) return '';
    any = true;
    const n = k === 'Sets' ? groups.length : groups.reduce((a, g) => a + spFold(g.items).length, 0);
    const body = k === 'Sets'
      ? `<div class="sp-sets">${groups.map(spSetHtml).join('')}</div>`
      : groups.map(g => `<div class="sp-grp">${esc(g.group)}</div><div class="sp-grid">${spFold(g.items).map(spTileHtml).join('')}</div>`).join('');
    return `<details class="sp-sec" data-spsec="${k}" ${SP.open[k] !== false ? 'open' : ''}><summary title="${esc(title)}">${label}<small>${n}</small></summary>${body}</details>`;
  }).join('');
  return any ? h : `<div class="msg">${SP.q ? 'Nothing in this style matches "' + esc(SP.q) + '".' : 'Nothing learnt for this style.'}</div>`;
}
// (one tile per model: the records that share a mesh, the twenty bags of salt rice, fold under the first)
function spFold(items){ return SP.q ? items : groupByMesh(items, it => it.mesh).map(g => g[0]); }
function spSetHtml(s){
  const its = s.items.slice(0, 7);
  return `<div class="sp-set" draggable="true" data-spset="${s.n_}" title="Click, then click where it goes (the wheel or R turns it); or drag it into the view. One Undo takes it back.">
    <div class="sp-strip">${its.map(i => thumbImg(i.id, i.type, i === its[0] ? 72 : 48)).join('')}</div>
    <b>${esc(s.label)}</b><div class="msg">${s.items.length} things · seen in ${s.n} place${s.n === 1 ? '' : 's'} · <span class="lnk" data-spshow="${esc(s.cell)}" data-spshowid="${esc(s.items[0].id)}" title="Open ${esc(s.place || s.cell)}, where the game stands this one">show me</span></div></div>`;
}
function spTreeHtml(d){
  const row = it => `<div class="sp-row" draggable="true" data-pid="${esc(it.id)}" data-pname="${esc(it.name || it.id)}" data-ptype="${esc(it.type || '')}" data-spid="${esc(it.id)}">${thumbImg(it.id, it.type, 48)}<span>${esc(it.name || it.id)} <small>${esc(it.id)} · ${Math.round(100 * (it.share || 0))}%</small></span></div>`;
  const h = spSecs(d).map(([k, label, title, groups]) => {
    if (!groups.length) return '';
    if (k === 'Sets') return `<details ${SP.q ? 'open' : ''}><summary>${label} (${groups.length})</summary>${groups.map(s => `<div class="sp-row" draggable="true" data-spset="${s.n_}">${thumbImg(s.items[0].id, s.items[0].type, 48)}<span>${esc(s.label)} <small>${s.items.length} things · ${s.n} places</small></span></div>`).join('')}</details>`;
    return `<details ${SP.q ? 'open' : ''}><summary title="${esc(title)}">${label}</summary>${groups.map(g => {
      const folded = groupByMesh(g.items, it => it.mesh);
      return `<details ${SP.q ? 'open' : ''}><summary>${esc(g.group)} (${g.items.length})</summary>${folded.map(gr => gr.length < 2 ? row(gr[0])
        : `<details><summary style="padding-left:0">${row(gr[0])}</summary>${gr.slice(1).map(row).join('')}</details>`).join('')}</details>`;
    }).join('')}</details>`;
  }).join('');
  return `<div class="sp-tree">${h || '<div class="msg">Nothing matches.</div>'}</div>`;
}

// ---------------------------------------------------------------- clicks, drags, the card
function spItem(id){
  const d = SP.data[SP.cur]; if (!d) return null;
  const low = id.toLowerCase();
  for (const sec of Object.values(d.sections)) for (const g of sec) for (const it of g.items) if (it.id.toLowerCase() === low) return it;
  return null;
}
function spSet(n){ const d = SP.data[SP.cur]; return d && d.sets[+n]; }
function spPlaceSet(s){
  if (!W.key) return toast('Open a place on the World map first.', true);
  startGroupPlace(s.items.map(i => Object.assign({}, i)), s.label.toLowerCase());
}
async function spShow(ck, id){
  try {
    await worldOpen(ck);
    if (id){
      const c = W.cells[ck], r = c && c.refs.find(x => x.id.toLowerCase() === id.toLowerCase());
      if (r){ selectRef(ck, r.k); centerOn(r); toast('Here is one in the game\'s own ' + (W.info && W.info.name || 'place') + '. Edits here change the game\'s place in your mod.'); return; }
    }
    toast('Opened ' + (W.info && W.info.name || ck) + ', one of the game\'s own places in this style.');
  } catch (e){ toast(e.message, true); }
}
function spBind(el){
  el.addEventListener('click', e => {
    const tab = e.target.closest('[data-sptab]');
    if (tab){ SP.cur = tab.dataset.sptab; SP.q = ''; spKeep(); spRender(); return; }
    const sh = e.target.closest('[data-spshow]');
    if (sh){ e.stopPropagation(); spShow(sh.dataset.spshow, sh.dataset.spshowid); return; }
    const st = e.target.closest('[data-spset]');
    if (st){ const s = spSet(st.dataset.spset); if (s) spPlaceSet(s); return; }
    // (a piece: the World map's own click handler starts placing it, as from the Place panel)
  });
  el.addEventListener('toggle', e => {
    const d = e.target.closest && e.target.closest('[data-spsec]'); if (!d) return;
    SP.open[d.dataset.spsec] = d.open; spKeep();
    if (d.open) v3ThumbScan(d);
  }, true);
  el.addEventListener('contextmenu', e => {
    const t = e.target.closest('[data-spid], [data-spset]'); if (!t) return;
    e.preventDefault(); e.stopPropagation();
    const pt = {x: e.clientX, y: e.clientY};
    if (t.dataset.spset != null){
      const s = spSet(t.dataset.spset); if (!s) return;
      pnlMenu(pt, [{label: '🧩 Place this set (click where it goes)', act: () => spPlaceSet(s)},
        ...(s.places || []).map(([ck, name]) => ({label: '👁 Show me in the game: ' + name, act: () => spShow(ck, s.items[0].id)}))]);
      return;
    }
    const it = spItem(t.dataset.spid); if (!it) return;
    pnlMenu(pt, [{label: '✚ Place it (click where it goes)', act: () => setMode('place', {id: it.id, name: it.name || it.id, type: it.type})},
      ...(it.at || []).map(([ck, name]) => ({label: '👁 Show me in the game: ' + name, act: () => spShow(ck, it.id)})),
      {label: '🔎 Find it on the Browse page', act: () => { showView('browse'); const q = $('#q'); if (q){ q.value = it.id; if (typeof runSearch === 'function') runSearch(); } }}]);
  });
  // the card: what the game stands next to it, puts on it, joins to it
  let t = null, cur = null;
  el.addEventListener('mouseover', e => {
    const tile = e.target.closest('[data-spid]');
    if (!tile){ return; }
    if (tile === cur) return;
    cur = tile; clearTimeout(t);
    t = setTimeout(() => { if (cur === tile && tile.isConnected && !window.wsDrag) spCard(tile); }, 380);
  });
  el.addEventListener('mouseout', e => {
    const tile = e.target.closest('[data-spid]');
    if (tile && !(e.relatedTarget && tile.contains(e.relatedTarget))){ cur = null; clearTimeout(t); setTimeout(() => { if (!cur) spCardHide(); }, 60); }
  });
  el.addEventListener('dragstart', e => {
    spCardHide();
    const s = e.target.closest && e.target.closest('[data-spset]'); if (!s) return;
    e.stopPropagation();
    e.dataTransfer.setData('text/x-mw-set', s.dataset.spset); e.dataTransfer.effectAllowed = 'copy';
    SP.dragSet = spSet(s.dataset.spset);
  });
  el.addEventListener('dragend', () => { SP.dragSet = null; });
}
function spCardHide(){ const c = $('#sp-card'); if (c) c.style.display = 'none'; }
function spCard(tile){
  const it = spItem(tile.dataset.spid); if (!it) return;
  let c = $('#sp-card');
  if (!c){ c = document.createElement('div'); c.id = 'sp-card'; c.className = 'sp-card'; document.body.appendChild(c); }
  const p = Math.round(100 * (it.share || 0));
  const goes = (it.goes || []).slice(0, 8);
  c.innerHTML = `${thumbImg(it.id, it.type, 120)}<h4>${esc(it.name || it.id)}</h4><div class="msg">${esc(it.id)} · ${esc(S.typeLabels[it.type] || it.type)} · ${esc(it.grp)}</div>
    <div style="margin-top:4px">${SP.cur === '*' ? `In ${p}% of the game's places, of every style.` : `In <b>${it.places}</b> of the ${esc(SP.cur)} places learnt from (${p}%)${it.lift ? `, ${it.lift >= 10 ? 'ten' : Math.round(it.lift)} times as often as an average style's` : ''}.`}
    ${it.also && it.also.length ? `<br>Also goes with: ${it.also.map(esc).join(', ')}.` : ''}</div>
    ${goes.length ? `<div class="sp-goes"><span></span><b>Goes with</b>${goes.map(([o, name, type, n, how]) => `${thumbImg(o, type, 48)}<span>${esc(name || o)}<small>${SP_HOW[how] || how} · seen ${n}×</small></span>`).join('')}</div>` : '<div class="msg" style="clear:both;margin-top:6px">Nothing the game stands with it often enough to say.</div>'}
    <div class="msg" style="clear:both;margin-top:6px">Click to place, or drag into the view. Right-click: show me one in the game.</div>`;
  const r = tile.getBoundingClientRect();
  c.style.display = 'block';
  const x = r.right + 8 + 300 < innerWidth ? r.right + 8 : Math.max(8, r.left - 308);
  c.style.left = x + 'px';
  c.style.top = Math.max(8, Math.min(innerHeight - c.offsetHeight - 8, r.top - 20)) + 'px';
  v3ThumbScan(c);
}

// a set dropped into the view or onto the map: set down whole there (group placing, one Undo)
(function(){
  const box = vwBox(); if (!box) return;
  box.addEventListener('dragover', e => {
    if (!e.dataTransfer.types.includes('text/x-mw-set') || e.target.closest('.owin')) return;
    e.preventDefault(); e.dataTransfer.dropEffect = 'copy';
  });
  box.addEventListener('drop', e => {
    if (!e.dataTransfer.types.includes('text/x-mw-set') || e.target.closest('.owin')) return;
    e.preventDefault(); e.stopPropagation();
    const s = SP.dragSet || spSet(e.dataTransfer.getData('text/x-mw-set')); if (!s || !W.key) return;
    let x, y, z = null;
    if (typeof V3 !== 'undefined' && V3.on){
      const h = v3Pick(e, true);
      if (!h || !h.world) return toast('Drop it onto the ground, a floor or another object.', true);
      [x, y, z] = h.world;
    } else {
      const r = cv.getBoundingClientRect();
      [x, y] = toWorld(e.clientX - r.left, e.clientY - r.top);
    }
    W.groupPlace = {items: s.items.map(i => Object.assign({}, i)), label: s.label.toLowerCase(), yaw: 0};
    placeGroupAt(x, y, z).finally(() => { if (W.mode !== 'group') W.groupPlace = null; });
  }, true);
})();

// the window follows the place: the ◆ mark and "Only what fits here" go by the place open now
setInterval(() => { if (spWin() && SP.themes && SP.hereKey !== W.key) spRender(); }, 1500);
window.addEventListener('keydown', e => { if (e.key === 'Escape') spCardHide(); });

// ---------------------------------------------------------------- the ways in
// the 3D toolbar's 🎨 Style (drawn in world3d.js) and the Place panel's 🎨 Style palette (index.html)
document.addEventListener('click', e => {
  const b = e.target.closest && e.target.closest('#w-stylepal, #v3tools [data-v3="style"]'); if (!b) return;
  spOpen();
});
CF_ACT.push({id: 'stylepal', label: 'Style palette: building pieces, furniture and decor by style', keys: [], world: true, run: () => spOpen()});
