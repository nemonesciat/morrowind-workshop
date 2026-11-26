// ---------- A thing's card: everything about one placed thing, in the same card as a person's ----------
// (the user, 2026-11-26: "we are trying to make all creative functions in the world easily accessible to a builder";
// "other sheets that things in the world could need. doors? regular objects with scripts?") The card a person or a
// container has, for every placed thing, under the view or ⧉ in a window, with tabs by what it is:
//   📋 Details   the object window's form (record and placement: name, model, script, the type's own fields, where
//                it stands, owner, lock, key, trap; for a door where it leads), Save as one Undo  (objwin.js)
//   🚪 Leads to  a door's ways              ⚡ Does   what it does when used, opened or read; traps; secret ways
//   🎨 Look      model, textures, sound, swap  🪄 Dress / 🧱 Build  for furniture and building pieces
//   📦 Contents  a container's               📅 Day   a creature's week (as a person's)
// The action tabs are the right-click menu's own entries for that thing (ctxmenu.js groups), so whatever the menu
// can do the card can, and anything added to the menu later shows on the card by itself.
const TC = {opening: false};
const TC_GROUPS = [
  ['door', '🚪', 'Leads to', ['This door']],
  ['does', '⚡', 'Does', ['What it does', 'Secret entrance']],
  ['look', '🎨', 'Look', ['Looks and sound', 'Replace and select']],
  ['dress', '🪄', 'Dress', ['Dress it']],
  ['build', '🧱', 'Build', ['Build']],
];
const TC_ICON = {DOOR: '🚪', CONT: '📦', LIGH: '🕯', BOOK: '📖', ACTI: '⚙', CREA: '🐾', STAT: '🧱', MISC: '📦', WEAP: '🗡', ARMO: '🛡',
  CLOT: '👤', ALCH: '🧪', INGR: '🌿', APPA: '⚙', LOCK: '🔓', PROB: '🗝', REPA: '⚒', NPC_: '🧍'};
function tcIcon(type){ return TC_ICON[type] || '🗂'; }

// the right-click menu's entries for this thing, gathered without showing the menu
function tcItems(cell, r){
  if (typeof cfMenuAt !== 'function' || typeof cmMenu !== 'function') return [];
  let got = [];
  const m0 = window.cmMenu;
  window.cmMenu = (_pt, items) => { got = items || []; return null; };
  TC.opening = true;
  try { cfMenuAt({clientX: 0, clientY: 0, preventDefault(){}, stopPropagation(){}}, [cell, r], r.p, null); }
  catch (e){ /* (a menu builder that needs a real mouse event: its entries just aren't on the card) */ }
  finally { window.cmMenu = m0; TC.opening = false; }
  const flat = [];
  const walk = list => { for (const it of list || []){ if (!it || it === '-' || typeof it !== 'object') continue; if (it.items) walk(it.items); else if (it.act && it.label) flat.push(it); } };
  walk(got);
  return flat;
}
function tcTabsFor(type, items, first){
  const tabs = first ? [first] : [];
  tabs.push(['details', '📋', 'Details']);
  if (type === 'CREA') tabs.push(['day', '📅', 'Day']);
  for (const [k, e, t, groups] of TC_GROUPS){
    if (items.some(it => groups.includes(cmGroupOf(it)))) tabs.push([k, e, t]);
  }
  return tabs;
}

// open the card of a placed thing (a person's and a container's go to theirs, with the same tabs added)
async function tcOpen(cell, k, tab, quiet){
  if (TC.opening) return;
  const r = typeof findRef === 'function' && findRef(cell, k);
  if (!r){ if (!quiet) toast('That object isn\'t here any more.', true); return; }
  if (typeof needProject === 'function' && !await needProject()) return;
  if (r.type === 'NPC_') return pcOpen(r.id, tab === 'details' ? 'details' : null, {ref: {cell, k}});
  if (r.type === 'CONT') return pcOpenCont(r.id, {cell, k}, tab);
  TC.opening = true;
  try {
    if (!(W.sel && W.sel.cell === cell && W.sel.k === k) && typeof selectRef === 'function') selectRef(cell, k);
  } finally { TC.opening = false; }
  if (typeof QM !== 'undefined' && QM.dock && typeof qmClose === 'function') qmClose();
  PCD.kind = 'thing'; PCD.id = r.id; PCD.ref = {cell, k}; PCD.sel = null; PCD.job = null; PCD.week = PCD.week && PCD.week.id === r.id ? PCD.week : null;
  PCD.d = {id: r.id, name: r.name || r.id, type: r.type, copies: 0};
  PCD.tabs = tcTabsFor(r.type, tcItems(cell, r));
  PCD.tab = PCD.tabs.some(t => t[0] === tab) ? tab : (PCD.tabs.some(t => t[0] === PCD.tab) ? PCD.tab : 'details');
  pcDock();
  pcRender();
}

// an action tab: the menu's entries in its groups, as buttons (gathered again each time, so they say what is now)
function tcGroupPane(key){
  const g = TC_GROUPS.find(x => x[0] === key); if (!g || !PCD.ref) return '';
  const r = findRef(PCD.ref.cell, PCD.ref.k); if (!r) return '<div class="msg">That object isn\'t here any more.</div>';
  PCD.items = tcItems(PCD.ref.cell, r).filter(it => g[3].includes(cmGroupOf(it)));
  const lead = key === 'door' && r.to ? `<div class="pc-row" style="margin-bottom:6px"><span class="msg">Leads to</span><b>${esc(r.to.cell || r.to.label || 'outdoors')}</b></div>` : '';
  return lead + (PCD.items.length ? `<div style="display:flex;flex-wrap:wrap;gap:6px">${PCD.items.map((it, n) => `<button class="btn" data-tcact="${n}" title="${esc(it.title || '')}">${esc(it.label)}</button>`).join('')}</div>`
    : '<div class="msg">Nothing here for this thing.</div>');
}
function tcGroupBind(b){
  b.querySelectorAll('[data-tcact]').forEach(x => x.onclick = async () => {
    const it = PCD.items[+x.dataset.tcact]; if (!it) return;
    try { await it.act(); } catch (e){ toast(e.message, true); }
    setTimeout(() => { if (PCD.kind && $('#pc-dock') && $('#pc-dock').style.display !== 'none' && TC_GROUPS.some(g => g[0] === PCD.tab)) pcRender(); }, 600);
  });
}

// 📋 Details: the object window's form, built into the card (and moved back in, edits and all, when the tab is back)
function tcDetailsPane(){ return '<div id="pc-ow"></div>'; }
function tcDetailsBind(b){
  const host = b.querySelector('#pc-ow'); if (!host || !PCD.ref || typeof owOpenRaw !== 'function') return;
  const {cell, k} = PCD.ref;
  if (OW.el && OW.host && OW.cell === cell && OW.k === k){ OW.host = host; host.appendChild(OW.el); return; }
  OW.host = host;
  if (OW.el && !OW.el.isConnected && typeof owDirty === 'function' && owDirty()){ OW.el = null; }
  else if (OW.el) OW.el.remove(), OW.el = null;
  OW.embedding = true;
  try { owOpenRaw(cell, k, true); } finally { OW.embedding = false; }
}
