// Windows over the 3D view for the Workshop's other tools: the Create forms (a new place, NPC, container,
// item, note, spell), the leveled list editor, the item and spell editor, the character editor and a
// character's dialogue. The page itself is lifted into a window that floats over the World map, the
// way the object window does (objwin.js), so it is the same form with the same code; closing the window
// puts the page back where it was, unsaved edits and all. Each window can be dragged by its title bar
// and sized from its corner, comes to the front when clicked, remembers where it was left, and closes
// with Esc. "✚ Create here…" on the view's right-click menu opens a Create form with the clicked spot as
// where the new thing goes.
const VW = {wins: {}, pos: {}, want: null, inWin: false, nav: false};
try { VW.pos = JSON.parse(localStorage.getItem('ws-vwin-pos') || '{}') || {}; } catch (e){}

// the pages that can be a window: their title, and what showView would draw for them
const VW_HOST = {
  createv: {title: () => CR.kind && CR_CARDS[CR.kind] ? CR_CARDS[CR.kind][0] + ' ' + CR_CARDS[CR.kind][1] : '✚ Create', render: () => renderCreate(), w: 1000},
  lists: {title: () => '🎲 ' + (LV.id ? 'Leveled list ' + LV.id : 'Random loot or spawn list'), render: () => renderLists(), w: 980},
  itemed: {title: () => '✎ ' + (IE.data ? (IE.data.name || IE.data.id) : 'Edit an item, spell or enchantment'), render: () => renderItemEd(), w: 900},
  chars: {title: () => '👤 ' + (C.data ? (C.data.name || C.data.id) : 'Characters'), render: () => renderChars(), w: 1000},
  dialog: {title: () => '💬 Dialogue', render: () => renderDialog(), w: 1040},
};

function vwCss(){
  if (typeof owCss === 'function') owCss();          // (the object window's look: title bar, border, shadow)
  if ($('#vw-css')) return;
  const c = document.createElement('style'); c.id = 'vw-css';
  c.textContent = `
  .vwin{resize:both;min-width:360px;min-height:220px}
  .vwbody{position:relative;flex:1;min-height:0}
  .vwbody > .view{display:grid !important;position:absolute;inset:0;overflow:auto}
  .vwbody > #createv,.vwbody > #itemed{display:block !important}
  .vwbody #createwrap{max-width:none;padding:6px 18px 30px}
  .vwbody #createwrap > h1,.vwbody #createwrap > .lead,.vwbody #createwrap > .cgroups{display:none}
  .vwbody #createwrap .cform{margin-top:6px}
  .vwbody #itemed > .wrap{max-width:none;padding:6px 18px 30px}
  .vwbody .pp-btn{display:none}
  .owhead .vwpage{font-size:12px;color:var(--muted);cursor:pointer;white-space:nowrap}
  .owhead .vwpage:hover{color:var(--gold2)}`;
  document.head.appendChild(c);
}

const vwHosting = v => !!(VW.wins[v] && VW.wins[v].el.isConnected);
function vwBox(){ return $('#world .mapwrap'); }

// ---------------------------------------------------------------- open, close, where it sits
function vwOpen(v){
  const H = VW_HOST[v]; if (!H) return null;
  vwCss();
  if (vwHosting(v)){ vwFront(VW.wins[v].el); return VW.wins[v]; }
  const page = $('#' + v), box = vwBox(); if (!page || !box) return null;
  const el = document.createElement('div'); el.className = 'owin vwin'; el.dataset.vw = v;
  el.setAttribute('data-ownkeys', '');       // (keys typed here are the form's, not the 3D view's shortcuts)
  el.innerHTML = `<div class="owhead"><span class="owtitle"></span>
      <span class="vwpage" title="Close the window and show this on its own page">⤢ As a page</span>
      <button class="btn sm" data-vwclose title="Close (Esc). Nothing is lost: what's half done stays as it is.">✕</button></div>
    <div class="vwbody"></div>`;
  box.appendChild(el);
  const w = {v, el, home: page.parentNode};
  VW.wins[v] = w;
  el.querySelector('.vwbody').appendChild(page);
  el.querySelector('[data-vwclose]').onclick = () => vwClose(v);
  el.querySelector('.vwpage').onclick = () => { vwClose(v); VW.nav = true; try { showView(v); } finally { VW.nav = false; } };
  // (a click in here that opens another of these pages opens it as a window too)
  el.addEventListener('click', () => { VW.inWin = true; setTimeout(() => VW.inWin = false, 0); }, true);
  el.addEventListener('pointerdown', () => vwFront(el), true);
  el.addEventListener('keydown', e => { if (e.key !== 'Escape') e.stopPropagation(); });
  vwDrag(el, v);
  const p = VW.pos[v] || {};
  const n = Object.keys(VW.wins).length - 1;
  el.style.width = Math.min(p.w || H.w, box.clientWidth - 24) + 'px';
  el.style.height = Math.min(p.h || 640, box.clientHeight - 24) + 'px';
  w.pos = p.x != null ? {x: p.x, y: p.y} : {x: 16 + n * 28, y: 52 + n * 28};
  vwPlace(w);
  vwFront(el);
  // (the size it's dragged to by its corner is kept too; not a size it was squeezed to by a small view)
  if (typeof ResizeObserver !== 'undefined'){
    let down = false;
    el.addEventListener('pointerdown', () => { down = true; window.addEventListener('pointerup', () => { down = false; }, {once: true}); });
    new ResizeObserver(() => { if (down && el.isConnected && el.offsetWidth) vwKeep(v, {w: el.offsetWidth, h: el.offsetHeight}); }).observe(el);
  }
  return w;
}
function vwClose(v){
  const w = VW.wins[v]; if (!w) return;
  delete VW.wins[v];
  const page = $('#' + v);
  if (page && w.home) w.home.appendChild(page);      // (back among the pages; which one shows is showView's business)
  w.el.remove();
  if (v === 'createv') CR.at = null;
  if (typeof PL !== 'undefined' && PL && PL.paint && v === 'createv') PL.paint = null;
}
function vwKeep(v, o){ VW.pos[v] = Object.assign(VW.pos[v] || {}, o); try { localStorage.setItem('ws-vwin-pos', JSON.stringify(VW.pos)); } catch (e){} }
function vwPlace(w){
  const el = w.el, box = vwBox(); if (!el || !box || !box.clientWidth) return;
  const bw = box.clientWidth, bh = box.clientHeight;
  if (el.offsetWidth > bw - 8) el.style.width = (bw - 8) + 'px';
  if (el.offsetHeight > bh - 8) el.style.height = (bh - 8) + 'px';
  const x = Math.max(0, Math.min(bw - el.offsetWidth, w.pos.x)), y = Math.max(0, Math.min(Math.max(0, bh - el.offsetHeight), w.pos.y));
  el.style.left = x + 'px'; el.style.top = y + 'px';
}
function vwDrag(el, v){
  const head = el.querySelector('.owhead'); let D = null;
  head.addEventListener('pointerdown', e => {
    if (e.button !== 0 || e.target.closest('button, input, label, .vwpage')) return;
    const r = el.getBoundingClientRect(); D = {dx: e.clientX - r.left, dy: e.clientY - r.top};
    head.setPointerCapture(e.pointerId);
  });
  head.addEventListener('pointermove', e => {
    if (!D) return;
    const box = vwBox().getBoundingClientRect(), w = VW.wins[v]; if (!w) return;
    w.pos = {x: e.clientX - box.left - D.dx, y: e.clientY - box.top - D.dy}; vwPlace(w);
  });
  head.addEventListener('pointerup', () => { if (D){ D = null; const w = VW.wins[v]; if (w) vwKeep(v, {x: w.pos.x, y: w.pos.y}); } });
}
// the window clicked comes to the front (the object window takes part too)
function vwFront(el){
  const all = [...vwBox().querySelectorAll(':scope > .owin')].sort((a, b) => (+getComputedStyle(a).zIndex || 0) - (+getComputedStyle(b).zIndex || 0));
  all.splice(all.indexOf(el), 1); all.push(el);
  all.forEach((x, n) => x.style.zIndex = 41 + n);
}
function vwTop(){
  if (!cfWorldOn()) return null;
  const all = [...vwBox().querySelectorAll(':scope > .owin')].filter(x => x.style.display !== 'none' && x.offsetWidth);
  return all.sort((a, b) => (+getComputedStyle(b).zIndex || 0) - (+getComputedStyle(a).zIndex || 0))[0] || null;
}
function vwTitle(v){
  const w = VW.wins[v]; if (!w) return;
  let t = ''; try { t = VW_HOST[v].title(); } catch (e){}
  w.el.querySelector('.owtitle').textContent = t;
}
// what showView would draw for the page, drawn in its window instead (the World map stays the page)
function vwRender(v){
  const w = vwOpen(v); if (!w) return;
  if (typeof ppInit === 'function') ppInit(v);
  try { const r = VW_HOST[v].render(); if (r && r.then) r.then(() => vwTitle(v)).catch(e => toast(e.message, true)); }
  catch (e){ reportClientError('Window "' + v + '": ' + (e.stack || e), 'vwRender'); }
  document.querySelectorAll('nav button').forEach(b => b.classList.toggle('on', b.dataset.view === 'world'));
  vwTitle(v);
}
// do something that shows one of these pages, with the page coming up as a window over the view
function vwRun(v, fn){
  if (!cfWorldOn()) showView('world');
  VW.want = v;
  try { return fn(); } finally { VW.want = null; }
}

// showView: a page that's a window (or asked for as one, from a window or from vwRun) is drawn there;
// going to it with the buttons at the top puts it back on its own page
(function(){
  const orig = showView;
  showView = function(v){
    if (VW_HOST[v] && !VW.nav && cfWorldOn() && (vwHosting(v) || VW.want === v || VW.inWin)){ vwRender(v); return; }
    if (VW.wins[v]) vwClose(v);
    return orig(v);
  };
  const nav = document.querySelector('nav');
  if (nav) nav.addEventListener('click', () => { VW.nav = true; setTimeout(() => VW.nav = false, 0); }, true);
})();
// Esc closes the window in front (an open list or menu first; the object window looks after itself)
window.addEventListener('keydown', e => {
  if (e.key !== 'Escape') return;
  const top = vwTop(); if (!top || !top.classList.contains('vwin')) return;
  if (document.querySelector('.modal-bg, .pmenu')) return;
  e.preventDefault(); e.stopPropagation();
  const open = top.querySelector('.ddlist[style*="block"]');
  if (open){ open.style.display = 'none'; return; }
  vwClose(top.dataset.vw);
}, true);
window.addEventListener('resize', () => Object.values(VW.wins).forEach(vwPlace));
// (titles follow what the window shows: the character or item loaded after it opened)
setInterval(() => { for (const v of Object.keys(VW.wins)) vwTitle(v); }, 1000);

// ---------------------------------------------------------------- Create, over the view
// the spot under a right-click, as the Create forms' "where it goes"
function vwSpot(at){
  if (!at || !W.key) return null;
  const z = typeof V3 !== 'undefined' && V3.on && at[2] != null ? at[2] : null;
  return {cell: W.ext ? cellKeyAt(at[0], at[1]) : W.key, x: at[0], y: at[1], z, rz: 0, cut: W.ext ? null : W.cut, surface: z != null};
}
async function vwCreate(kind, at){
  if (!cfWorldOn()) showView('world');
  if (kind === 'merge'){ mergeModal(); return; }
  if (kind === 'lists'){ LV.id = null; LV.data = null; vwRun('lists', () => showView('lists')); return; }
  if (kind === 'effect'){ MX.form = null; vwRun('myeff', () => showView('myeff')); return; }
  if (kind === 'itemed'){ IE.id = null; IE.data = null; vwRun('itemed', () => showView('itemed')); return; }
  CR.kind = kind; CR.items = []; CR.idEdited = false; CR.at = at || null;
  vwOpen('createv');
  vwRun('createv', () => showView('createv'));
}
// the cards, as a menu
function vwCreateMenu(pt, at){
  const spot = vwSpot(at);
  const where = spot ? ' here' : '';
  const it = k => ({label: `${CR_CARDS[k][0]} ${CR_CARDS[k][1]}${['npc', 'container', 'item', 'book'].includes(k) ? where : k === 'build' && spot ? ' (a door from here)' : ''}`, act: () => vwCreate(k, spot)});
  const items = [{label: 'Make something new', disabled: true, head: true}, ...['build', 'npc', 'container', 'item', 'book', 'spell', 'effect', 'lists'].map(it),
    '-', {label: 'Change something that exists', disabled: true, head: true}, it('itemed'), it('merge')];
  const m = pnlMenu(pt, items);
  m.querySelectorAll('button').forEach((b, n) => { const x = items.filter(y => y !== '-')[n]; if (x && x.head) b.className = 'phd'; });
  return m;
}
// what was made from a window: it opens there, and the view stays
async function vwCreated(kind, r, label){
  vwClose('createv');
  if (kind === 'build'){
    toast((CR.bmode === 'copy' ? 'Copied it as "' : 'Built "') + label + '". ' + (LINK.connected ? 'You can walk into it in game right away.' : 'Furnish it here, then try it with Play here.'));
    await worldOpen(r.key);
    return;
  }
  if (kind === 'ruin' && r && r.key){
    toast(`Made "${label}": ${r.tunnels} tunnel pieces, ${ruinHalls(r.kind, r.halls)}${r.people ? `, ${r.people} ${r.people === 1 ? 'person' : 'people'} living in it` : ''}. Right-click in it for 🎲 Make this again.`);
    await worldOpen(r.key);
    return;
  }
  if (r && r.placed && r.placed.cell){
    const ck = r.placed.cell;
    toast('Created and placed ' + (label || r.id) + '. New things appear in game after restarting it with Play here.');
    if (W.cells[ck] && W.cells[ck].exists) await worldReloadCell(ck); else await worldOpen(ck);
    if (typeof V3 !== 'undefined' && V3.on) v3Refresh();
    if (r.placed.ref && findRef(ck, r.placed.ref)){ selectRef(ck, r.placed.ref); owOpen(ck, r.placed.ref); }
    return;
  }
  if (kind === 'npc' && r.id){ toast('Created ' + label + '. Fine-tune them here, then place them from the World map.'); vwRun('chars', () => cOpen(r.id)); return; }
  if (['spell', 'item', 'book'].includes(kind) && r.id){
    toast(`Created ${label}` + (r.given ? `, ${kind === 'spell' ? 'known by' : 'given to'} ${r.given}` : '') + (kind === 'spell' && r.cost ? ` (${r.cost} magicka)` : '') + '.');
    vwRun('itemed', () => ieShow(r.id));
    return;
  }
  toast('Created ' + label + '. Click where it goes (Esc: not now).');
  setMode('place', {id: r.id, name: label});
}

// ---------------------------------------------------------------- the ways in
// the right-click menu on the view: "✚ Create here…"
CF_MENU_MORE.push((e, hit, at) => {
  if (W.mode === 'paths') return [];
  if (hit && W.multi.size > 1 && inMulti(hit[0], hit[1].k)) return [];
  const spot = at || (hit && hit[1] && hit[1].p) || null, pt = {x: e.clientX, y: e.clientY};
  return [{label: '✚ Create here…', title: 'A new place, person, container, item, note, spell or list, made in a window over the view', act: () => setTimeout(() => vwCreateMenu(pt, spot), 0)}];
});
// the Ctrl+K command list: each card
for (const k of ['build', 'npc', 'container', 'item', 'book', 'spell', 'effect', 'lists', 'itemed', 'merge'])
  CF_ACT.push({id: 'vwcreate-' + k, label: 'Create in a window: ' + CR_CARDS[k][1], keys: [], world: true, run: () => vwCreate(k, null)});
CF_ACT.push({id: 'vwcreate', label: 'Create… (a window over the World map)', keys: [], world: true,
  run: () => { const b = $('#v3tools [data-v3="create"]') || $('#w-create'); const r = b ? b.getBoundingClientRect() : {left: 300, bottom: 160}; vwCreateMenu({x: r.left, y: r.bottom + 4}, null); }});
// the Place panel's "✚ Create new…" and the 3D toolbar's "✚ Create" (both drawn in index.html / world3d.js)
document.addEventListener('click', e => {
  const b = e.target.closest && e.target.closest('#w-create, #v3tools [data-v3="create"]'); if (!b) return;
  const r = b.getBoundingClientRect();
  vwCreateMenu({x: r.left, y: r.bottom + 4}, null);
});
