// Windows over the 3D view for the Workshop's other tools: the Create forms (a new place, NPC, container,
// item, note, spell), the leveled list editor, the item and spell editor, the character editor and a
// character's dialogue. The page itself is lifted into a window that floats over the World map, the
// way the object window does (objwin.js), so it is the same form with the same code; closing the window
// puts the page back where it was, unsaved edits and all. Each window can be dragged by its title bar
// and sized from its corner, comes to the front when clicked, remembers where it was left, and closes
// with Esc. "✚ Create here…" on the view's right-click menu opens a Create form with the clicked spot as
// where the new thing goes. The other pages at the top (Browse, Scripts, Rules, Library, My mod, Health
// check, Load order) are windows too: on the World map their buttons open them over it, several at once,
// so the map never has to be left (Shift+click, or right-click → "Open as a page", for the page itself).
const VW = {wins: {}, pos: {}, want: null, inWin: false, nav: false};
try { VW.pos = JSON.parse(localStorage.getItem('ws-vwin-pos') || '{}') || {}; } catch (e){}

// the pages that can be a window: their title, and what showView would draw for them
const VW_HOST = {
  createv: {title: () => CR.kind && CR_CARDS[CR.kind] ? CR_CARDS[CR.kind][0] + ' ' + CR_CARDS[CR.kind][1] : '✚ Create', render: () => renderCreate(), w: 1000},
  lists: {title: () => '🎲 ' + (LV.id ? 'Leveled list ' + LV.id : 'Random loot or spawn list'), render: () => renderLists(), w: 980},
  itemed: {title: () => '✎ ' + (IE.data ? (IE.data.name || IE.data.id) : 'Edit an item, spell or enchantment'), render: () => renderItemEd(), w: 900},
  chars: {title: () => '👤 ' + (C.data ? (C.data.name || C.data.id) : 'Characters'), render: () => renderChars(), w: 1000},
  dialog: {title: () => '💬 Dialogue', render: () => renderDialog(), w: 1040},
  // (the rest of the pages at the top, and the pages they lead to: each one the page itself, in a window)
  browse: {title: () => '🔎 Browse' + (S.q ? ': "' + S.q + '"' : '') + (S.cur ? ' · ' + (S.cur.name || S.cur.id) : ''), render: () => {}, w: 1180},
  scripts: {title: () => '⟨⟩ ' + (SC.id ? 'Script ' + SC.id : 'Scripts'), render: () => renderScripts(), w: 1060},
  rules: {title: () => { const t = (typeof RU_TABS !== 'undefined' && RU_TABS.find(x => x[0] === RU.tab)) || ['', '📘 Rules']; return t[1] + (RU.id ? ' · ' + RU.id : ''); }, render: () => renderRules(), w: 1040},
  library: {title: () => '🖼 Library', render: () => renderLibrary(), w: 980},
  mymod: {title: () => '📦 My mod' + (S.summary && S.summary.project ? ': ' + S.summary.project.name : ''), render: () => renderMyMod(), w: 900},
  release: {title: () => '📦 Get ready to share', render: () => renderRelease(), w: 980},
  myeff: {title: () => '🪄 Magic effects', render: () => renderMyEffects(), w: 980},
  health: {title: () => '🩺 Health check', render: () => {}, w: 920},
  plugins: {title: () => '☰ Load order', render: () => {}, w: 920},
  guide: {title: () => 'Home', render: () => renderGuide(), w: 900},
  settings: {title: () => '⚙ Settings', render: () => renderSettings(), w: 860},
};
// the pages at the top, by name (for the menus and Ctrl+K)
const VW_NAMES = {browse: 'Browse', createv: 'Create', library: 'Library', chars: 'Characters', dialog: 'Dialogue', scripts: 'Scripts',
  rules: 'Rules', mymod: 'My mod', health: 'Health check', plugins: 'Load order'};
// on the World map, the buttons at the top open their page as a window over it (Shift+click: as a page)
function vwPref(){ try { return localStorage.getItem('ws-vwin-pages') !== '0'; } catch (e){ return true; } }
function vwSetPref(on){ try { localStorage.setItem('ws-vwin-pages', on ? '1' : '0'); } catch (e){} toast(on ? 'On the World map, the pages at the top now open as windows over it (Shift+click: as a page).' : 'The pages at the top open as pages again (right-click one: "Open as a window").'); }

// (a page in a window drops the page's own margins, 22 over and 60 under it: they made a window scroll on into
// empty space when all of it fitted, the user's Dungeon window)
function vwCss(){
  if (typeof owCss === 'function') owCss();          // (the object window's look: title bar, border, shadow)
  if ($('#vw-css')) return;
  const c = document.createElement('style'); c.id = 'vw-css';
  c.textContent = `
  #world .mapwrap{isolation:isolate}
  .vwin{resize:both;min-width:360px;min-height:220px;outline:none}
  .vwbody{position:relative;flex:1;min-height:0}
  .vwbody > .view{display:grid !important;position:absolute;inset:0;overflow:auto}
  /* (a page laid out in panels is a row of docks, as on its own page: as a grid, Browse's Record dock sat in
     its old third column, half empty, and its edge dragged the wrong way) */
  .vwbody > .view.pspace{display:flex !important;overflow:hidden}
  .vwbody > #createv,.vwbody > #itemed,.vwbody > #myeff,.vwbody > #library,.vwbody > #mymod,.vwbody > #release,.vwbody > #health,.vwbody > #plugins,.vwbody > #guide,.vwbody > #settings{display:block !important}
  .vwbody > .view > .wrap{padding:8px 20px 30px}
  .vwbody > .view{padding-top:0 !important;padding-bottom:0 !important}
  .vwbody #createwrap{padding-bottom:10px !important}
  .vwbody > #browse{overflow:hidden}
  nav button.vwopen{box-shadow:inset 0 -2px 0 var(--gold)}
  .vwbody #createwrap{max-width:none;padding:6px 18px 30px}
  .vwbody #createwrap > h1,.vwbody #createwrap > .lead,.vwbody #createwrap:has(.cform) > .cgroups{display:none}
  .vwbody #createwrap .cform{margin-top:6px}
  .vwbody #itemed > .wrap{max-width:none;padding:6px 18px 30px}
  .vwbody .pp-btn{display:none}
  .owhead .vwpage{font-size:12px;color:var(--muted);cursor:pointer;white-space:nowrap}
  .owhead .vwpage:hover{color:var(--gold2)}`;
  document.head.appendChild(c);
}

// (the windows stack among themselves inside the map, so a dialog, menu or message opened from one, such as
// "+ New quest", comes up over all of them and dims them with the map, instead of hiding under the window)
vwCss();

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
  VW.wins[v] = w; vwNavMark();
  el.querySelector('.vwbody').appendChild(page);
  el.querySelector('[data-vwclose]').onclick = () => vwClose(v);
  el.querySelector('.vwpage').onclick = () => { vwClose(v); VW.nav = true; try { showView(v); } finally { VW.nav = false; } };
  // (a click in here that opens another of these pages opens it as a window too)
  el.addEventListener('click', () => { VW.inWin = true; setTimeout(() => VW.inWin = false, 0); }, true);
  // (a click in here takes the keys from the 3D view: arrows go through Browse's results, W isn't flying)
  el.tabIndex = -1;
  el.addEventListener('pointerdown', e => { vwFront(el); if (!e.target.closest('input, textarea, select, button, [contenteditable], [tabindex]:not(.vwin)')) setTimeout(() => { if (!el.contains(document.activeElement)) el.focus({preventScroll: true}); }, 0); }, true);
  el.addEventListener('keydown', e => { if (e.key !== 'Escape'){ if (v === 'browse') vwBrowseKey(e); e.stopPropagation(); } });
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
    // (a Create form comes up whole when there's room for it over the map: the window grows to it, never
    // shrinks, so a size it's dragged to stays; the Dungeon form wanted scrolling in a window it nearly fitted)
    const inner = page.firstElementChild;
    // (in the next frame: sized from inside the observer, the browser reported a "ResizeObserver loop")
    if (v === 'createv' && inner) new ResizeObserver(() => requestAnimationFrame(() => {
      if (down || !el.isConnected) return;
      const body = el.querySelector('.vwbody'), need = el.offsetHeight - body.clientHeight + page.scrollHeight;
      const room = box.clientHeight - (parseFloat(el.style.top) || 0) - 12;
      if (need > el.offsetHeight) el.style.height = Math.min(need, Math.max(el.offsetHeight, room)) + 'px';
    })).observe(inner);
  }
  return w;
}
function vwClose(v){
  const w = VW.wins[v]; if (!w) return;
  delete VW.wins[v];
  const page = $('#' + v);
  if (page && w.home) w.home.appendChild(page);      // (back among the pages; which one shows is showView's business)
  w.el.remove(); vwNavMark();
  if (v === 'createv') CR.at = null;
  if (typeof PL !== 'undefined' && PL && PL.paint && v === 'createv') PL.paint = null;
}
// the buttons at the top whose page is open in a window get a line under them (their size stays as it is)
const VW_NAVOF = {itemed: 'createv', lists: 'createv', myeff: 'createv', release: 'mymod'};
function vwNavMark(){
  const open = new Set(Object.keys(VW.wins).map(v => VW_NAVOF[v] || v));
  document.querySelectorAll('nav button[data-view]').forEach(b => b.classList.toggle('vwopen', open.has(b.dataset.view)));
}
// Browse in a window: ↑ ↓ go through the results, Alt+← → back and forward (as on the page)
function vwBrowseKey(e){
  if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName) || S.editing) return;
  if (e.altKey && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')){ e.preventDefault(); goHist(e.key === 'ArrowLeft' ? -1 : 1); return; }
  if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
  const n = S.rows.findIndex(r => r.i === S.sel) + (e.key === 'ArrowDown' ? 1 : -1);
  if (S.rows[n]){ e.preventDefault(); openRecord(S.rows[n].i, true); document.querySelector(`.row[data-i="${S.rows[n].i}"]`)?.scrollIntoView({block: 'nearest'}); }
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

// showView: on the World map, a page is drawn in a window over it (when it already is one, when asked for
// as one from a window or vwRun, or always, while "pages as windows" is on); Shift+click on the buttons at
// the top, or "⤢ As a page", puts it back on its own page
(function(){
  const orig = showView;
  showView = function(v){
    if (VW_HOST[v] && !VW.nav && cfWorldOn() && (vwHosting(v) || VW.want === v || VW.inWin || vwPref())){ vwRender(v); return; }
    if (VW.wins[v]) vwClose(v);
    return orig(v);
  };
  const nav = document.querySelector('nav');
  if (nav) nav.addEventListener('click', e => { VW.nav = e.shiftKey || !vwPref(); setTimeout(() => VW.nav = false, 0); }, true);
})();
// Esc closes the window in front (an open list or menu first; the object window looks after itself)
window.addEventListener('keydown', e => {
  if (e.key !== 'Escape') return;
  const top = vwTop(); if (!top || !top.classList.contains('vwin')) return;
  if (document.querySelector('.modal-bg, .pmenu')) return;
  if (document.activeElement === $('#q')) return;          // (Esc in the search box at the top empties it)
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
    '-', {label: 'Change something that exists', disabled: true, head: true}, it('itemed')];
  // (the prefab workbench: a building put together from the game's pieces of a style, then set down in one go;
  // bench.js. It took Plan a prefab's place, 2026-10-27: "doesn't look anything like what I drew")
  if (typeof benchOpen === 'function') items.splice(2, 0, {label: '🔨 Prefab workbench (build from the game\'s pieces)', act: () => benchOpen()});
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
for (const k of ['build', 'npc', 'container', 'item', 'book', 'spell', 'effect', 'lists', 'itemed'])
  CF_ACT.push({id: 'vwcreate-' + k, label: 'Create in a window: ' + CR_CARDS[k][1], keys: [], world: true, run: () => vwCreate(k, null)});
CF_ACT.push({id: 'vwcreate', label: 'Create… (a window over the World map)', keys: [], world: true,
  run: () => { const b = $('#v3tools [data-v3="create"]') || $('#w-create'); const r = b ? b.getBoundingClientRect() : {left: 300, bottom: 160}; vwCreateMenu({x: r.left, y: r.bottom + 4}, null); }});
// each page at the top, as a window (Ctrl+K), and the switch for the buttons at the top
for (const v of Object.keys(VW_NAMES)) CF_ACT.push({id: 'vwpage-' + v, label: 'Open ' + VW_NAMES[v] + ' in a window over the World map', keys: [], run: () => vwRun(v, () => showView(v))});
CF_ACT.push({id: 'vwpref', label: 'Pages at the top open as windows over the World map (on/off)', keys: [], run: () => vwSetPref(!vwPref())});
// (the right-click menu on a button at the top ends with these: navmenu.js)
function vwNavItems(v){
  if (!VW_HOST[v]) return [];
  const asPage = () => { if (VW.wins[v]) vwClose(v); VW.nav = true; try { showView(v); } finally { VW.nav = false; } };
  return ['-', {label: '⧉ Open as a window over the World map', act: () => vwRun(v, () => showView(v))},
    {label: '⤢ Open as a page', act: asPage},
    {label: (vwPref() ? '☑' : '☐') + ' On the World map, the pages here open as windows', act: () => vwSetPref(!vwPref())}];
}
// the Place panel's "✚ Create new…" and the 3D toolbar's "✚ Create" (both drawn in index.html / world3d.js)
document.addEventListener('click', e => {
  const b = e.target.closest && e.target.closest('#w-create, #v3tools [data-v3="create"]'); if (!b) return;
  const r = b.getBoundingClientRect();
  vwCreateMenu({x: r.left, y: r.bottom + 4}, null);
});
