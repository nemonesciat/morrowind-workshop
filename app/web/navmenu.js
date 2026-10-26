// ---------- Right-click a page's button at the top: its main features as a list ----------
// Each entry opens the page and then does what the page's own button or tab does (found by its id, its
// data- attribute or its words), so the list stays in step with the page.

// open the page, then click what's on it once it has drawn (a page fills in after its data arrives)
async function navGo(view, sel, text, missing){
  // (on the World map, a page that can be a window comes up as one over the view, the map staying put)
  if (typeof VW_HOST !== 'undefined' && VW_HOST[view] && typeof cfWorldOn === 'function' && cfWorldOn()) vwRun(view, () => showView(view));
  else showView(view);
  for (let n = 0; n < 40; n++){
    const box = document.getElementById(view) || document;
    let el = sel ? box.querySelector(sel) || document.querySelector(sel) : null;
    if (!el && text) el = [...box.querySelectorAll('button, .drow, .ccard')].find(b => b.offsetParent !== null && b.textContent.includes(text));
    if (el){ if (el.matches('input, textarea')){ el.focus(); el.select(); } else el.click(); return; }
    await new Promise(r => setTimeout(r, 100));
  }
  toast(missing || `"${text || sel}" isn't there on this page just now.`, true);
}
// a kind of thing to make, picked straight away (the cards' own onclick does the same): over the 3D view
// Create comes up as a window with no cards to click, and the user saw '"[data-ck="ruin"]" isn't there'
function navCreate(k){
  // (a page that can be a window comes up as one over the World map's view, as navGo has it)
  const open = view => (typeof VW_HOST !== 'undefined' && VW_HOST[view] && typeof cfWorldOn === 'function' && cfWorldOn()) ? vwRun(view, () => showView(view)) : showView(view);
  // (the cards that open a page of their own, as bindForm's)
  if (k === 'forge' && typeof forgeShow === 'function') return forgeShow();
  if (k === 'givespell' && typeof sgShow === 'function') return sgShow();
  if (k === 'merge' && typeof mergeModal === 'function') return mergeModal();
  if (k === 'lists'){ LV.id = null; LV.data = null; return open('lists'); }
  if (k === 'effect'){ MX.form = null; return open('myeff'); }
  if (k === 'itemed'){ IE.id = null; IE.data = null; return open('itemed'); }
  CR.kind = k; CR.items = []; CR.idEdited = false;
  open('createv');
  if (typeof renderCreate === 'function') renderCreate();
}
function navType(tag){
  showView('browse'); S.types = tag ? [tag] : []; buildSide(); runSearch();
}
function navWorld(text){
  if (!W.key){ showView('world'); toast('Open a place on the World map first.', true); return; }
  navGo('world', null, text);
}

const NAV_MENU = {
  browse: () => [
    {label: 'Everything', act: () => navType('')}, '-',
    ...[['NPC_', 'People (NPCs)'], ['CREA', 'Creatures'], ['WEAP', 'Weapons'], ['ARMO', 'Armor'], ['CLOT', 'Clothing'],
        ['BOOK', 'Books and scrolls'], ['SPEL', 'Spells'], ['ALCH', 'Potions'], ['CELL', 'Places (cells)'], ['SCPT', 'Scripts']]
      .map(([t, l]) => ({label: l, act: () => navType(t)})), '-',
    {label: 'Search everything (/)', act: () => { $('#q').focus(); $('#q').select(); }}],
  world: () => [
    {label: '🪑 Auto-furnish rooms…', act: () => navWorld('Auto-furnish')},
    {label: '👥 Populate this place…', act: () => W.key ? (showView('world'), poOpen(W.key, null)) : navWorld('')},
    {label: '＋ Create new here…', act: () => navWorld('Create new')},
    {label: '🔧 Find gaps…', act: () => navWorld('Find gaps')},
    {label: '🩺 Check this place…', act: () => navWorld('Check this place')}, '-',
    {label: '▶ Play here (pick a spot)', act: () => { showView('world'); cfRun('play'); }},
    {label: 'Switch between the flat map and 3D', act: () => { showView('world'); cfRun('view3d'); }},
    {label: '▤ Panels and layouts…', act: () => { showView('world'); cfRun('panels'); }}],
  // (the Create page's own groups of cards, so a new card is on the list as soon as it is on the page)
  createv: () => CR_GROUPS.flatMap((g, n) => [...(n ? ['-'] : []),
    ...g[1].filter(k => CR_CARDS[k]).map(k => ({label: CR_CARDS[k][0] + ' ' + CR_CARDS[k][1], act: () => navCreate(k)}))]),
  library: () => [
    {label: 'Add models, pictures or sounds…', act: () => navGo('library', '#lib-pick')},
    {label: 'Add a folder…', act: () => navGo('library', '#lib-pickdir')}, '-',
    {label: '🗂 Browse packs…', act: () => navGo('library', '#lib-browse')},
    {label: '⤓ Make a pack…', act: () => navGo('library', '#lib-mkpack')},
    {label: '⤒ Open a pack…', act: () => navGo('library', '#lib-oppack')}],
  chars: () => [
    {label: '+ New character', act: () => navGo('chars', '#c-new')},
    {label: 'Open a character…', act: () => navGo('chars', '#c-find')}, '-',
    ...[['faction', '🏛 Factions'], ['class', '🎓 Classes'], ['race', '🧝 Races'], ['birthsign', '✨ Birthsigns']].map(([k, l]) => ({label: l, act: () => ruShow(k)}))],
  dialog: () => [
    {label: '+ New quest', act: () => navGo('dialog', '#d-newquest')},
    {label: '+ New topic', act: () => navGo('dialog', '#d-newtopic')},
    {label: 'Open a character\'s conversation…', act: () => navGo('dialog', '#d-npc')}, '-',
    ...[['mine', 'Lines in my mod'], ['4', 'Quests'], ['0', 'Topics'], ['2', 'Greetings']].map(([k, l]) => ({label: l, act: () => navGo('dialog', `[data-dk="${k}"]`)}))],
  scripts: () => [
    {label: '+ New script', act: () => navGo('scripts', '#s-new')},
    {label: 'Open a script…', act: () => navGo('scripts', '#s-find')}, '-',
    {label: '🌐 Global variables', act: () => ruShow('global')},
    {label: '⚙ Game settings', act: () => ruShow('gmst')}],
  rules: () => RU_TABS.map(([k, l]) => ({label: l, act: () => ruShow(k)})),
  mymod: () => [
    {label: '📦 Get ready to share', act: () => navGo('mymod', '#mm-release')},
    {label: '💾 Save as…', act: () => navGo('mymod', '#mm-saveas')},
    {label: '📁 Show folder', act: () => navGo('mymod', '#mm-folder')}, '-',
    {label: '🗂 Your mods…', act: () => navGo('mymod', '#mm-mods')},
    {label: 'Switch or start another mod', act: () => navGo('mymod', '#mm-switch')},
    {label: '📂 Open an .esp as your mod…', act: () => navGo('mymod', '#mm-adopt')},
    {label: '⊕ Merge another mod into this one…', act: () => navGo('mymod', '#mm-merge')}],
  health: () => [['all', 'Everything'], ['error', 'Needs fixing'], ['warning', 'Worth a look'], ['info', 'Good to know']]
    .map(([k, l]) => ({label: l, act: () => navGo('health', `[data-hf="${k}"]`)})),
  plugins: () => [
    {label: 'Save load order', act: () => navGo('plugins', '#lo-save')},
    {label: 'Fix master order', act: () => navGo('plugins', '#lo-fix', null, 'Every master already loads before what needs it: nothing to fix.')},
    {label: 'Undo my changes to the order', act: () => navGo('plugins', '#lo-revert')}],
};

document.querySelectorAll('nav button[data-view]').forEach(b => b.addEventListener('contextmenu', e => {
  const f = NAV_MENU[b.dataset.view]; if (!f) return;
  e.preventDefault();
  const items = f().concat(typeof vwNavItems === 'function' ? vwNavItems(b.dataset.view) : []).filter(it => it === '-' || it.label);
  pnlMenu({x: e.clientX, y: e.clientY}, items);
}));
