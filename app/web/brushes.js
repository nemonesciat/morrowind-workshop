// ---------- Your own scatter brushes ----------
// Any objects in your load order (from mods too) on a brush of your own, each with how often it comes
// up and the sizes it can be. Kept beside the Workshop's settings so they work in every mod, and
// shared as a small .json file. The Scatter tool shows them next to the region's own sets (★).
const BR = {editing: null};

function brCss(){
  if ($('#br-css')) return;
  const c = document.createElement('style'); c.id = 'br-css';
  c.textContent = `
  .br-items{display:flex;flex-direction:column;gap:4px;margin:6px 0;max-height:260px;overflow:auto}
  .br-item{display:grid;grid-template-columns:1fr auto;gap:2px 6px;align-items:center;padding:5px 6px;border:1px solid var(--line);border-radius:6px;background:var(--panel2);font-size:12px}
  .br-item .nm{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text-b)} .br-item .nm small{color:var(--muted-b);margin-left:4px}
  .br-item .ctl{grid-column:1 / -1;display:flex;gap:6px;align-items:center;color:var(--muted-b)}
  .br-item .ctl input[type=range]{width:80px} .br-item .ctl input[type=number]{width:52px}
  .br-bar{display:flex;gap:4px;flex-wrap:wrap;margin:6px 0}`;
  document.head.appendChild(c);
}

// the brush editor, in the Scatter panel, for one of your brushes
function brEditor(box, set){
  brCss();
  const id = set.key.slice(3);
  const b = BR.editing && BR.editing.id === id ? BR.editing : {id, name: set.label, items: set.items.map(it => ({...it}))};
  BR.editing = b;
  box.insertAdjacentHTML('beforeend', `
    <div class="v3lrow" style="gap:4px"><input class="inp" id="br-name" value="${esc(b.name)}" style="flex:1" title="The brush's name"></div>
    <div class="dd" style="margin:6px 0"><input class="inp" id="br-add" placeholder="+ Add something: search by name or ID (mods too)" autocomplete="off"><div class="ddlist" id="br-add-l"></div></div>
    ${b.items.length ? '' : '<div class="faint">Empty for now. Add things with the search above, or select something on the map and use "Add to brush".</div>'}
    <div class="br-items">${b.items.map((it, n) => `<div class="br-item" data-bi="${n}">
      <span class="nm" title="${esc(it.id)}">${esc(it.name || it.id)}<small>${esc(it.name ? it.id : '')}</small></span>
      <button class="btn sm" data-brx="${n}" title="Take it off the brush">✕</button>
      <span class="ctl">How often <input type="range" min="1" max="10" step="1" value="${Math.round(it.weight || 1)}" data-brw="${n}">
        size <input class="inp" type="number" min="0.5" max="2" step="0.05" value="${it.smin}" data-brs0="${n}" title="Smallest">–<input class="inp" type="number" min="0.5" max="2" step="0.05" value="${it.smax}" data-brs1="${n}" title="Biggest"></span></div>`).join('')}</div>
    <div class="br-bar"><button class="btn sm" id="br-export" title="Save this brush as a file to share">⤓ Share</button>
      <button class="btn sm" id="br-import" title="Add brushes from a shared file">⤒ Add from file</button>
      <button class="btn sm" id="br-del" style="color:#ff8a6a">Delete brush</button></div>
    <div class="faint">Sizes and how deep things sit in the ground start from how the game uses them outdoors. Brushes are kept for every mod you make.</div>`);
  const save = async () => {
    try { const r = await post('/api/brushes/save', {brush: b}); BR.editing = {...r}; V3.scatSets = null; } catch (e){ toast(e.message, true); }
  };
  const later = (() => { let t; return () => { clearTimeout(t); t = setTimeout(save, 500); }; })();
  $('#br-name').onchange = async () => { b.name = $('#br-name').value.trim() || 'My brush'; await save(); v3ScatterPanel(); };
  ddSearch('br-add', 'STAT,ACTI,CONT,LIGH,MISC,INGR', async r => {
    if (b.items.some(i => i.id.toLowerCase() === r.id.toLowerCase())) return toast('It is on this brush already.');
    const d = await api('/api/brushes/item?id=' + encodeURIComponent(r.id));
    b.items.push({...d, id: r.id, name: r.name || d.name, weight: 5});
    await save(); v3ScatterPanel();
  }, true);
  box.querySelectorAll('[data-brx]').forEach(x => x.onclick = async () => { b.items.splice(+x.dataset.brx, 1); await save(); v3ScatterPanel(); });
  box.querySelectorAll('[data-brw]').forEach(x => x.oninput = () => { b.items[+x.dataset.brw].weight = +x.value; later(); });
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
