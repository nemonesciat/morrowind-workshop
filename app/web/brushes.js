// ---------- Your own scatter brushes ----------
// Any objects in your load order (from mods too) on a brush of your own, each with how often it comes
// up and the sizes it can be. Kept beside the Workshop's settings so they work in every mod, and
// shared as a small .json file. The Scatter tool shows them next to the region's own sets (★).
const BR = {editing: null, sel: -1};
// (pictures or a list, for the things on a brush and what the search finds; PIN2 on Discord: "change the list to a grid
// like this as an option", the style palette's pictures beside the Scatter tool's list of DLT_Trees_ names)
try { BR.view = localStorage.getItem('ws-brview') || 'list'; } catch (e){ BR.view = 'list'; }
function brViewSel(){
  return `<select class="inp br-view" title="Pictures, or a list"><option value="grid" ${BR.view === 'grid' ? 'selected' : ''}>▦</option><option value="list" ${BR.view === 'list' ? 'selected' : ''}>☰</option></select>`;
}
function brViewHook(box, redraw){
  box.querySelectorAll('.br-view').forEach(v => v.onchange = () => { BR.view = v.value; try { localStorage.setItem('ws-brview', BR.view); } catch (e) {} redraw(); });
}

function brCss(){
  if ($('#br-css')) return;
  const c = document.createElement('style'); c.id = 'br-css';
  // (a row is two lines that fit the panel's width: picture, name, share and ✕; then how often and its sizes. The
  // first of these, one line of slider and two number boxes with spinners, ran off the panel's side, PIN2's report)
  c.textContent = `
  .br-items{display:flex;flex-direction:column;gap:4px;margin:2px 0;max-height:300px;overflow-y:auto;overflow-x:hidden}
  .br-item{display:grid;grid-template-columns:30px minmax(0,1fr) auto auto;gap:3px 6px;align-items:center;padding:4px 5px;border:1px solid var(--line);border-radius:6px;background:var(--panel2);font-size:12px}
  .br-item img.thumb{width:30px;height:30px;border-radius:4px;object-fit:contain;background:var(--panel)}
  .br-item .nm{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text-b)}
  .br-item .pc{color:var(--muted-b);font-size:11px;min-width:28px;text-align:right}
  .br-item .x{padding:0 6px;line-height:18px}
  .br-item .ctl{grid-column:1 / -1;display:flex;gap:5px;align-items:center;color:var(--muted-b);font-size:11.5px;min-width:0}
  #v3land .br-item .ctl input[type=range]{flex:1;min-width:40px;width:auto}
  .br-item .ctl input[type=number]{width:38px;padding:1px 3px;font-size:11.5px;text-align:center;-moz-appearance:textfield}
  .br-item .ctl input[type=number]::-webkit-inner-spin-button,.br-item .ctl input[type=number]::-webkit-outer-spin-button{-webkit-appearance:none;margin:0}
  .br-bar{display:flex;gap:4px;align-items:center;margin:2px 0}
  .br-bar .del{margin-left:auto;color:#ff8a6a}
  .br-add{display:flex;gap:4px;align-items:center}
  .br-add .dd{flex:1;min-width:0}
  select.br-view{width:auto;padding:1px 3px;flex:none}
  .br-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(64px,1fr));gap:4px;margin:3px 0;max-height:300px;overflow-y:auto;overflow-x:hidden}
  .br-tile{position:relative;display:flex;flex-direction:column;align-items:center;gap:2px;padding:3px;border:1px solid var(--line);border-radius:6px;background:var(--panel2);cursor:pointer;font-size:10.5px;min-width:0}
  .br-tile:hover{border-color:var(--accent)}
  .br-tile.sel{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent) inset}
  .br-tile.off{opacity:.4}
  .br-tile img.thumb{width:100%;height:auto;aspect-ratio:1;border-radius:4px;object-fit:contain;background:var(--panel)}
  .br-tile span{width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-align:center;color:var(--text-b)}
  .br-tile .pc{position:absolute;top:2px;left:2px;padding:0 3px;border-radius:3px;background:rgba(0,0,0,.6);color:#fff;font-size:10px;font-weight:normal}
  .br-tile .on{position:absolute;top:2px;right:2px;padding:0 3px;border-radius:3px;background:#5d8a3a;color:#fff;font-size:10px}`;
  document.head.appendChild(c);
}

// the brush editor, in the Scatter panel, for one of your brushes
function brEditor(box, set){
  brCss();
  const $ = s => box.querySelector(s);              // (this editor's own fields, wherever its box is)
  const id = set.key.slice(3);
  const b = BR.editing && BR.editing.id === id ? BR.editing : {id, name: set.label, items: set.items.map(it => ({...it}))};
  BR.editing = b;
  const tot = b.items.reduce((t, it) => t + (it.weight || 1), 0) || 1;
  const pc = it => Math.round(100 * (it.weight || 1) / tot) + '%';
  box.insertAdjacentHTML('beforeend', `
    <input class="inp" id="br-name" value="${esc(b.name)}" placeholder="Brush name" title="The brush's name. Brushes are kept for every mod you make.">
    <div class="br-add"><div class="dd"><input class="inp" id="br-add" placeholder="+ Add: name or ID" title="Search everything in your load order, mods too" autocomplete="off"><div class="ddlist" id="br-add-l"></div></div>${brViewSel()}</div>
    <div class="br-grid" id="br-found" style="display:none"></div>
    ${b.items.length ? '' : '<div class="faint">Empty. Add things above, or right-click one on the map → Add to brush.</div>'}
    ${BR.view === 'grid' && b.items.length ? `<div class="br-grid">${b.items.map((it, n) => `<div class="br-tile ${n === BR.sel ? 'sel' : ''}" data-brt="${n}" title="${esc(it.name || it.id)} (${esc(it.id)}). Click for how often and its sizes">${thumbImg(it.id, '', 96)}<span>${esc(it.name || it.id)}</span><b class="pc" data-brp="${n}">${pc(it)}</b></div>`).join('')}</div>` : ''}
    <div class="br-items">${b.items.map((it, n) => BR.view === 'grid' && n !== BR.sel ? '' : `<div class="br-item" data-bi="${n}">
      ${thumbImg(it.id, '', 48, 'sm')}
      <span class="nm" title="${esc(it.id)}">${esc(it.name || it.id)}</span>
      <span class="pc" data-brp="${n}" title="Its share of what this brush scatters">${pc(it)}</span>
      <button class="btn sm x" data-brx="${n}" title="Take it off the brush">✕</button>
      <span class="ctl"><span title="How often it comes up, against the others on this brush">Often</span><input type="range" min="1" max="10" step="1" value="${Math.round(it.weight || 1)}" data-brw="${n}" title="How often it comes up">
        <span title="Sizes it can be, smallest to biggest. They start from how the game sizes it outdoors">Size</span><input class="inp" type="number" min="0.5" max="2" step="0.05" value="${(+it.smin).toFixed(2)}" data-brs0="${n}" title="Smallest">–<input class="inp" type="number" min="0.5" max="2" step="0.05" value="${(+it.smax).toFixed(2)}" data-brs1="${n}" title="Biggest"></span></div>`).join('')}</div>
    <div class="br-bar"><button class="btn sm" id="br-export" title="Save this brush as a file to share">⤓ Share</button>
      <button class="btn sm" id="br-import" title="Add brushes from a shared file">⤒ From file</button>
      <button class="btn sm del" id="br-del" title="Delete this brush. What you scattered with it stays.">🗑</button></div>`);
  if (typeof v3ThumbScan === 'function') v3ThumbScan(box);
  const save = async () => {
    try { const r = await post('/api/brushes/save', {brush: b}); BR.editing = {...r}; V3.scatSets = null; } catch (e){ toast(e.message, true); }
  };
  const later = (() => { let t; return () => { clearTimeout(t); t = setTimeout(save, 500); }; })();
  $('#br-name').onchange = async () => { b.name = $('#br-name').value.trim() || 'My brush'; await save(); v3ScatterPanel(); };
  const add = async r => {
    if (b.items.some(i => i.id.toLowerCase() === r.id.toLowerCase())) return toast('It is on this brush already.');
    const d = await api('/api/brushes/item?id=' + encodeURIComponent(r.id));
    b.items.push({...d, id: r.id, name: r.name || d.name, weight: 5});
    await save(); v3ScatterPanel();
  };
  brViewHook(box, () => v3ScatterPanel());
  if (BR.view === 'grid'){
    // (what the search finds as pictures under the box, most used first; click one to put it on the brush)
    const inp = $('#br-add'), found = $('#br-found');
    let t, seq = 0;
    // (the search stays as it was when the panel is drawn again, so a few things can be added one after another)
    inp.oninput = () => { clearTimeout(t); t = setTimeout(async () => {
      const q = BR.q = inp.value.trim(), my = ++seq;
      if (!q){ found.style.display = 'none'; return; }
      let r;
      try { r = await api('/api/search?' + new URLSearchParams({q, types: 'STAT,ACTI,CONT,LIGH,MISC,INGR', limit: 60, sort: 'uses'})); } catch (e){ return; }
      if (my !== seq) return;
      const has = new Set(b.items.map(i => i.id.toLowerCase()));
      found.innerHTML = r.rows.map((x, n) => `<div class="br-tile" data-brf="${n}" title="${esc(x.name || x.id)} (${esc(x.id)}): click to add it">${thumbImg(x.id, x.type, 96)}<span>${esc(x.name || x.id)}</span>${has.has(x.id.toLowerCase()) ? '<b class="on">✓</b>' : ''}</div>`).join('') || '<div class="faint">No matches</div>';
      found.style.display = 'grid';
      v3ThumbScan(found);
      found.querySelectorAll('[data-brf]').forEach(d => d.onclick = () => add(r.rows[+d.dataset.brf]));
    }, 200); };
    if (BR.q){ inp.value = BR.q; inp.oninput(); }
    box.querySelectorAll('[data-brt]').forEach(x => x.onclick = () => { BR.sel = BR.sel === +x.dataset.brt ? -1 : +x.dataset.brt; v3ScatterPanel(); });
  } else ddSearch('br-add', 'STAT,ACTI,CONT,LIGH,MISC,INGR', add, true);
  box.querySelectorAll('[data-brx]').forEach(x => x.onclick = async () => { b.items.splice(+x.dataset.brx, 1); BR.sel = -1; await save(); v3ScatterPanel(); });
  box.querySelectorAll('[data-brw]').forEach(x => x.oninput = () => {
    b.items[+x.dataset.brw].weight = +x.value;
    const t = b.items.reduce((t, it) => t + (it.weight || 1), 0) || 1;
    box.querySelectorAll('[data-brp]').forEach(e => e.textContent = Math.round(100 * (b.items[+e.dataset.brp].weight || 1) / t) + '%');
    later();
  });
  box.querySelectorAll('[data-brs0]').forEach(x => x.onchange = () => { const it = b.items[+x.dataset.brs0]; it.smin = +x.value; if (it.smax < it.smin) it.smax = it.smin; later(); });
  box.querySelectorAll('[data-brs1]').forEach(x => x.onchange = () => { const it = b.items[+x.dataset.brs1]; it.smax = +x.value; if (it.smin > it.smax) it.smin = it.smax; later(); });
  $('#br-del').onclick = async () => {
    if (!confirm(`Delete the brush "${b.name}"? What you already scattered with it stays.`)) return;
    await post('/api/brushes/delete', {id: b.id}); BR.editing = null; V3.scatSets = null; V3.land.scatSet = null; v3ScatterPanel();
  };
  $('#br-export').onclick = () => brExport([b]);
  $('#br-import').onclick = brImport;
}

async function brNew(seed){
  const n = ((V3.scatSets && V3.scatSets.sets) || []).filter(s => s.mine).length + 1;
  const items = [];
  if (seed){ const d = await api('/api/brushes/item?id=' + encodeURIComponent(seed.id)); items.push({...d, id: seed.id, name: seed.name || d.name, weight: 5}); }
  const r = await post('/api/brushes/save', {brush: {name: 'My brush ' + n, items}});
  BR.editing = r; V3.scatSets = null;
  if (V3.land) V3.land.scatSet = 'my:' + r.id;      // (none yet when the land tools haven't been opened, as indoors)
  return r;
}

// "Add to brush" for something picked on the map or in search
async function brAddTo(id, name){
  const r = await api('/api/brushes');
  const list = r.brushes;
  let target;
  if (!list.length) target = null;
  else {
    // (a menu of the brushes where the pointer is, not a box to type a number into)
    target = await new Promise(res => {
      const items = [{label: 'Add "' + (name || id) + '" to which brush?', disabled: true, head: true},
        ...list.map(b => ({label: '🌿 ' + b.name, act: () => res(b)})), '-', {label: '＋ A new brush', act: () => res(null)}];
      const m = pnlMenu({x: QOL_PT.x, y: QOL_PT.y}, items);
      m.querySelectorAll('button').forEach((b, n) => { const it = items.filter(x => x !== '-')[n]; if (it && it.head) b.className = 'phd'; });
      // (closed without a choice: nothing happens)
      const gone = new MutationObserver(() => { if (!m.isConnected){ gone.disconnect(); setTimeout(() => res(undefined), 0); } });
      gone.observe(document.body, {childList: true, subtree: true});
    });
    if (target === undefined) return;
  }
  if (!target){ const b = await brNew({id, name}); toast(`Made a new brush, "${b.name}", with ${name || id} on it. Find it under 🌿 Scatter in the 3D view.`); return; }
  if (target.items.some(i => i.id.toLowerCase() === id.toLowerCase())) return toast('It is on that brush already.');
  const d = await api('/api/brushes/item?id=' + encodeURIComponent(id));
  target.items.push({...d, id, name: name || d.name, weight: 5});
  await post('/api/brushes/save', {brush: target});
  if (V3) V3.scatSets = null;
  toast(`Added ${name || id} to "${target.name}".`);
}

function brExport(brushes){
  const data = {format: 'Morrowind Workshop brushes', version: 1,
    brushes: brushes.map(b => ({name: b.name, items: b.items.map(i => ({id: i.id, weight: i.weight, smin: i.smin, smax: i.smax, sink: i.sink}))}))};
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([JSON.stringify(data, null, 1)], {type: 'application/json'}));
  a.download = (brushes.length === 1 ? brushes[0].name : 'brushes').replace(/[^\w\- ]+/g, '_') + '.brush.json';
  a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}
function brImport(){
  const inp = document.createElement('input'); inp.type = 'file'; inp.accept = '.json,application/json';
  inp.onchange = async () => {
    const f = inp.files[0]; if (!f) return;
    let data; try { data = JSON.parse(await f.text()); } catch (e){ return toast('That file isn\'t a brush file.', true); }
    try {
      const r = await post('/api/brushes/import', {data});
      toast(r.added ? `Added ${r.added} brush${r.added === 1 ? '' : 'es'}.` + (r.skipped ? ` ${r.skipped} thing${r.skipped === 1 ? ' was' : 's were'} left out: your load order doesn't have them.` : '') : 'Nothing in that file could be used (your load order has none of its objects).', !r.added);
      V3.scatSets = null; v3ScatterPanel();
    } catch (e){ toast(e.message, true); }
  };
  inp.click();
}
