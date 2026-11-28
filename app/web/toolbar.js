// The buttons over the World map (Map / 3D / Panels, and the 3D tools) in groups you can drag about by
// their grip. A group you've put somewhere stays there; near the right or bottom edge it keeps to that
// edge when the side panels change size. "Arrange automatically" puts them all back in a row.
// Since 2.9.20 they are docked by default: one bar of icons across the top of the view, as an editor has it
// (the user's pick from a preview, 2026-11-27); right-click it to float the groups again (TB.float).
const TB = (() => { let t = {}; try { t = JSON.parse(localStorage.getItem('ws-toolbar') || '{}') || {}; } catch (e){} t.pos = t.pos || {}; return t; })();
const TB_PAD = 6;

function tbSave(){ try { localStorage.setItem('ws-toolbar', JSON.stringify(TB)); } catch (e){} }
function tbGrip(){ return '<span class="tb-grip" title="Drag to move these buttons. Right-click to arrange them.">⋮⋮</span>'; }

function tbCss(){
  if ($('#tb-css')) return;
  const c = document.createElement('style'); c.id = 'tb-css';
  c.textContent = `
  .v3grp{display:flex;gap:6px;align-items:center;flex-wrap:nowrap}
  .v3grp.tb-placed,.viewsw.tb-placed{position:absolute;z-index:4}
  .v3grp:has(.v3viewmenu[style*="block"]){position:relative;z-index:9}
  .v3grp.tb-placed:has(.v3viewmenu[style*="block"]){position:absolute}
  .tb-grip{cursor:grab;color:var(--faint);font-size:11px;line-height:1;letter-spacing:-2px;padding:6px 4px 6px 2px;user-select:none;align-self:stretch;display:flex;align-items:center;
    background:color-mix(in srgb,var(--panel) 87%,transparent);border:1px solid var(--line2);border-radius:6px}
  .tb-grip:hover{color:var(--gold2);border-color:var(--goldline)}
  .viewsw .tb-grip{border:0;border-radius:0;border-right:1px solid var(--line2)}
  .tb-dragging .tb-grip{cursor:grabbing}
  #world.tb-locked .tb-grip{display:none}
  .vbar{display:none}
  #world.tb-dock{--tbh:${TB_BAR_H}px}
  #world.tb-dock.tb-words{--tbh:${TB_BAR_H_WORDS}px}
  #world.tb-dock .vbar{position:absolute;left:0;right:0;top:0;height:var(--tbh);display:flex;align-items:center;gap:4px;padding:0 6px;z-index:5;
    background:var(--panel);border-bottom:1px solid var(--line);white-space:nowrap;overflow:hidden}
  #world.tb-dock #map{top:var(--tbh);height:calc(100% - var(--tbh))}
  #world.tb-dock #v3wrap{top:var(--tbh)}
  #world.tb-dock .tb-grip{display:none}
  #world.tb-dock .vbar .viewsw{position:static;flex:none;z-index:auto}
  #world.tb-dock .vbar .viewsw button{background:var(--panel2);padding:3px 11px;font-size:12px}
  #world.tb-dock .vbar .viewsw button.on{background:var(--btn-primary)}
  #world.tb-dock .vbar .v3tools{position:static;flex:1 1 auto;min-width:0;flex-wrap:nowrap;gap:0;pointer-events:auto;overflow:hidden}
  #world.tb-dock .vbar .v3grp{gap:1px;padding:0 4px;border-left:1px solid var(--line2);flex:none}
  #world.tb-dock .vbar .v3grp[data-grp="look"]{margin-left:auto}
  #world.tb-dock .vbar .btn.sm,#world.tb-dock .vbar-r button{min-width:28px;height:28px;padding:0 5px;display:inline-flex;align-items:center;justify-content:center;gap:4px;
    background:none;border:1px solid transparent;border-radius:5px;color:var(--muted);font-size:12px;cursor:pointer}
  #world.tb-dock .vbar .btn.sm:hover,#world.tb-dock .vbar-r button:hover{background:var(--hover);color:var(--text)}
  #world.tb-dock .vbar .btn.sm.primary,#world.tb-dock .vbar-r button.on{background:var(--sel);border-color:var(--goldline);color:var(--gold2)}
  #world.tb-dock .vbar .wi{width:17px;height:17px;margin:0}
  #world.tb-dock .vbar .tl{display:none}
  #world.tb-dock.tb-words .vbar .btn.sm,#world.tb-dock.tb-words .vbar-r button{flex-direction:column;height:44px;gap:2px;min-width:36px;padding:0 4px}
  #world.tb-dock.tb-words .vbar .tl{display:block;font-size:10px;line-height:1;white-space:nowrap}
  #world.tb-dock .vbar .v3snapnow{font-size:11.5px;color:var(--text)}
  #world.tb-dock .vbar .v3viewwrap:has(> [data-v3="snapmenu"]){display:none}
  #world.tb-dock .vbar [data-v3="pivotmenu"] .v3snapnow{display:none}
  #world.tb-dock .vbar .tb-over{display:none!important}
  #world:not(.tb-dock) .v3dock{display:none}
  .v3q{display:inline-flex;align-items:center;gap:3px;height:26px;padding:0 2px 0 6px;margin:0 1px;border:1px solid var(--line2);border-radius:5px;background:var(--deep);color:var(--faint)}
  .v3q .wi{width:14px!important;height:14px!important}
  .v3q select{background:transparent;border:0;color:var(--text);font:11.5px var(--mono);padding:0;cursor:pointer;width:auto;max-width:58px;min-width:0}
  .v3q select option{background:var(--panel)}
  #world.tb-dock .vbar-r{display:flex;gap:1px;align-items:center;flex:none;padding-left:5px;border-left:1px solid var(--line2);margin-left:auto}
  #world.tb-dock .v3tools[style*="flex"] ~ .vbar-r{margin-left:0}`;
  document.head.appendChild(c);
}

function tbArea(){ return $('#world .mapwrap'); }
const TB_BAR_H = 36, TB_BAR_H_WORDS = 52;                                  // (the docked bar's height: sizeMap leaves it to the bar)
function tbDocked(){ return !TB.float; }
// (how much of the view's top the docked bar takes: sizeMap leaves it to the bar)
function tbBarH(){ return !tbDocked() ? 0 : TB.words ? TB_BAR_H_WORDS : TB_BAR_H; }
// the docked bar: Map | 3D, then the 3D tools, then Panels, Show, the lock and ⛶ at the right; floating, each back
// where it was (the switch holds Panels, Show, the lock and ⛶)
function tbDock(){
  const A = tbArea(), sw = $('#viewsw'), t3 = $('#v3tools'); if (!A || !sw || !t3) return;
  let bar = $('#vbar');
  if (!bar){
    bar = document.createElement('div'); bar.id = 'vbar'; bar.className = 'vbar';
    bar.innerHTML = '<div class="vbar-r" id="vbar-r"></div>';
    A.insertBefore(bar, A.firstChild);
    bar.addEventListener('contextmenu', tbMenu);
  }
  const right = $('#vbar-r'), tail = ['w-panels', 'w-show', 'w-lockb', 'w-full'].map(id => document.getElementById(id)).filter(Boolean);
  const dock = tbDocked();
  $('#world').classList.toggle('tb-dock', dock);
  if (dock){
    if (sw.parentNode !== bar) bar.insertBefore(sw, right);
    if (t3.parentNode !== bar) bar.insertBefore(t3, right);
    for (const b of tail) if (b.parentNode !== right) right.appendChild(b);
  } else {
    if (sw.parentNode !== A) A.insertBefore(sw, bar.nextSibling);
    if (t3.parentNode !== A) A.insertBefore(t3, sw.nextSibling);
    for (const b of tail) if (b.parentNode !== sw) sw.appendChild(b);
  }
}
function tbGroups(){
  const sw = $('#viewsw'), t = $('#v3tools');
  return [sw, ...(t ? t.querySelectorAll('.v3grp') : [])].filter(Boolean);
}
function tbKey(g){ return g.id === 'viewsw' ? 'switch' : g.dataset.grp; }

// a group at a spot in the map area (x, y from its top left corner), kept inside it
function tbPut(g, x, y){
  const A = tbArea(); if (!A) return;
  g.classList.add('tb-placed');
  const w = g.offsetWidth, h = g.offsetHeight;
  x = Math.max(TB_PAD, Math.min(A.clientWidth - w - TB_PAD, x));
  y = Math.max(TB_PAD, Math.min(A.clientHeight - h - TB_PAD, y));
  // (the 3D tools sit inside their own strip: from its corner)
  const host = g.offsetParent && g.offsetParent !== A ? g.offsetParent : null;
  g.style.left = (x - (host ? host.offsetLeft : 0)) + 'px';
  g.style.top = (y - (host ? host.offsetTop : 0)) + 'px';
  return [x, y];
}
function tbPlace(g, p){
  const A = tbArea(); if (!A) return;
  g.classList.add('tb-placed');
  const w = g.offsetWidth, h = g.offsetHeight;
  tbPut(g, p.ax === 'r' ? A.clientWidth - p.x - w : p.x, p.ay === 'b' ? A.clientHeight - p.y - h : p.y);
}
function tbFree(g){ g.classList.remove('tb-placed'); g.style.left = g.style.top = ''; }

function tbApply(){
  tbCss();
  const sw = $('#viewsw');
  if (sw && !sw.querySelector('.tb-grip')) sw.insertAdjacentHTML('afterbegin', tbGrip());
  $('#world').classList.toggle('tb-locked', !!TB.locked);
  $('#world').classList.toggle('tb-words', !!TB.words);
  const docked0 = $('#world').classList.contains('tb-dock') + '|' + (TB.wordsDrawn || false);
  TB.wordsDrawn = !!TB.words;
  tbDock();
  // (docking or floating changes the room the map has: it is sized again)
  if (docked0 !== tbDocked() + '|' + !!TB.words && typeof sizeMap === 'function' && $('#world').classList.contains('on')){ sizeMap(); drawMap(); if (typeof V3 !== 'undefined' && V3.on) v3Resize(); }
  if (tbDocked()){ for (const g of tbGroups()) tbFree(g); tbFit(); return; }
  const A = tbArea(); if (!A || !A.clientWidth) return;        // (another page is showing: done when it's back)
  // (the 3D buttons start just past the Map / 3D switch, however wide it is: it grew a full view button)
  const t3 = $('#v3tools');
  if (t3 && sw && sw.offsetWidth) t3.style.left = (sw.classList.contains('tb-placed') ? 12 : sw.offsetLeft + sw.offsetWidth + 10) + 'px';
  for (const g of tbGroups()){
    const p = TB.pos[tbKey(g)];
    if (p) tbPlace(g, p); else tbFree(g);
    if (!g.dataset.tbBound){ g.dataset.tbBound = '1'; g.addEventListener('contextmenu', tbMenu); }
  }
}

// (docked: a bar too long for the view puts its least used buttons, one by one, into ⋯ rather than wrap or cut off)
const TB_OVER = ['help', 'home', 'extend', 'land', 'quests', 'style', 'create', 'physics', 'floor', 'tilt', 'rest', 'pieces', 'space', 'light', 'show'];
function tbFit(){
  const t3 = $('#v3tools'); if (!t3) return;
  t3.querySelectorAll('.tb-over').forEach(b => b.classList.remove('tb-over'));
  let more = $('#vbar-more');
  if (more) more.style.display = 'none';
  if (!tbDocked() || t3.style.display === 'none' || !t3.clientWidth) return;
  if (t3.scrollWidth <= t3.clientWidth + 1) return;
  const look = t3.querySelector('[data-grp="look"]'); if (!look) return;
  if (!more){
    more = document.createElement('button'); more.id = 'vbar-more'; more.className = 'btn sm'; more.title = 'More tools'; more.textContent = '⋯';
    more.onclick = e => {
      e.stopPropagation();
      const r = more.getBoundingClientRect();
      pnlMenu({x: r.left, y: r.bottom + 2}, [...t3.querySelectorAll('.tb-over')].map(b => ({
        label: (b.querySelector('.tl') ? b.querySelector('.tl').textContent.trim() : '') || (b.title || b.textContent).replace(/\s*[(:].*$/, '').trim() || b.textContent.trim(), act: () => b.click()})));
    };
  }
  if (more.parentNode !== look) look.appendChild(more);
  more.style.display = '';
  for (const k of TB_OVER){
    if (t3.scrollWidth <= t3.clientWidth + 1) break;
    const b = t3.querySelector(`[data-v3="${k}"]`); if (b) b.classList.add('tb-over');
  }
}
// (the two choices, from the bar's right-click, View in the menu row and Settings: docked or floating, words or not)
function tbSet(k, v){
  TB[k] = !!v; tbSave(); tbApply();
  if (typeof V3 !== 'undefined' && V3.on && typeof v3Tools === 'function') v3Tools();
  toast(k === 'float' ? (v ? 'The buttons float: drag a group by its grip ⋮⋮.' : 'The buttons are one bar over the view.') : (v ? 'Words beside the icons.' : 'Icons only: point at one for its name.'));
}
function tbAuto(){ TB.pos = {}; tbSave(); tbApply(); toast('Buttons arranged in a row again.'); }

function tbMenu(e){
  if (e.target.closest('select, input')) return;
  e.preventDefault(); e.stopPropagation();
  const g = e.currentTarget, k = g.id === 'vbar' ? null : tbKey(g), items = [];
  items.push({label: tbDocked() ? 'Float the buttons: groups to drag about the view' : 'Dock the buttons in one bar over the view',
    act: () => tbSet('float', tbDocked())});
  if (tbDocked()){
    items.push({label: TB.words ? 'Icons only' : 'Icons and words', act: () => tbSet('words', !TB.words)});
    return pnlMenu({x: e.clientX, y: e.clientY}, items);
  }
  if (TB.pos[k]) items.push({label: 'Put these back in the row', act: () => { delete TB.pos[k]; tbSave(); tbApply(); }});
  items.push({label: 'Arrange all automatically', act: tbAuto});
  items.push({label: TB.locked ? 'Unlock: show the grips to move them' : 'Lock them where they are (hide the grips)', act: () => { TB.locked = !TB.locked; tbSave(); tbApply(); }});
  pnlMenu({x: e.clientX, y: e.clientY}, items);
}

// dragging a group by its grip
document.addEventListener('mousedown', e => {
  const grip = e.button === 0 && e.target.closest && e.target.closest('.tb-grip'); if (!grip) return;
  const g = grip.closest('.v3grp, .viewsw'), A = tbArea(); if (!g || !A) return;
  e.preventDefault(); e.stopPropagation();
  const ar = A.getBoundingClientRect(), gr = g.getBoundingClientRect();
  const D = {g, sx: e.clientX, sy: e.clientY, x: gr.left - ar.left, y: gr.top - ar.top, at: null};
  document.body.classList.add('tb-dragging');
  const move = ev => {
    if (!(ev.buttons & 1)) return up();
    D.at = tbPut(g, D.x + ev.clientX - D.sx, D.y + ev.clientY - D.sy);
  };
  const up = () => {
    window.removeEventListener('mousemove', move, true); window.removeEventListener('mouseup', up, true);
    document.body.classList.remove('tb-dragging');
    if (!D.at) return;
    // kept from the nearer edge, so it stays put on that side when the view gets wider or narrower
    const [x, y] = D.at, w = g.offsetWidth, h = g.offsetHeight, W_ = A.clientWidth, H_ = A.clientHeight;
    const right = x + w / 2 > W_ / 2, bottom = y + h / 2 > H_ / 2;
    TB.pos[tbKey(g)] = {ax: right ? 'r' : 'l', x: Math.max(0, Math.round(right ? W_ - x - w : x)), ay: bottom ? 'b' : 't', y: Math.max(0, Math.round(bottom ? H_ - y - h : y))};
    tbSave();
  };
  window.addEventListener('mousemove', move, true); window.addEventListener('mouseup', up, true);
}, true);

// the view changing size (side panels, the window): the groups follow their edge and stay inside
(function(){
  const A = tbArea(); if (!A || typeof ResizeObserver === 'undefined') return;
  let raf = 0;
  new ResizeObserver(() => { if (!raf) raf = requestAnimationFrame(() => { raf = 0; tbApply(); }); }).observe(A);
})();
tbApply();

CF_ACT.push({id: 'tbauto', label: 'Arrange the buttons over the map automatically', keys: [], world: true, run: tbAuto},
  {id: 'tblock', label: 'Lock / unlock the buttons over the map', keys: [], world: true, run: () => { TB.locked = !TB.locked; tbSave(); tbApply(); toast(TB.locked ? 'Buttons locked where they are.' : 'Drag a grip ⋮⋮ to move the buttons.'); }});


// ---------------------------------------------------------------- tips for the buttons over the view and at the top
// The browser's own tip is small, slow, grey and missing on some controls (a list box shows none); these show
// quickly, in the theme, with the name, the key and what it does (the user, 2026-11-27: "hovering opens a small
// obscured text bar that's difficult to read, and some of the buttons don't display a tip at all").
// [name, what it does, the key's action (its keys are read, so your own show)]; no "what" = the button's own
// title, for buttons whose tip says how they are now (Game light, World axes, Lock walls, Undo…)
const TB_TIP = {
  translate: ['Move', 'Drag the arrows to move what\'s selected.', 'move'], rotate: ['Turn', 'Drag the rings to turn what\'s selected.', 'rotate'],
  tilt: ['Tilt', 'Lean what\'s selected forwards or sideways.'], scale: ['Scale', 'Drag a handle to make it bigger or smaller, as the game sizes things (×0.5 to ×2).', 'scalehandles'],
  pivotmenu: ['Pivot point', 'What several selected things turn, tilt and size about.'], space: ['World axes', ''],
  'q-grid': ['Move steps', 'Moves go in steps of this many units. Off: freely.'], 'q-angle': ['Turn steps', 'Turns go in steps of this angle. Off: freely.'],
  pieces: ['Snap to pieces', 'Line walls and floors up with the pieces beside them as you move them.'], rest: ['Land on surfaces', 'After a move, rest it on what\'s below.'],
  floor: ['Drop down', 'Set what\'s selected down on what\'s below.', 'drop'], physics: ['Physics', 'Let loose things fall and be pushed; keep the result or put them back.'],
  create: ['Create', 'Make something new: a place, a person, an item, a spell…'], style: ['Style palette', 'Building pieces, furniture and decor by style.'],
  quests: ['Quests', 'The quest maker: quests where they happen. Right-click a person, a thing or the ground for quest steps.'],
  land: ['Ground', 'Shape and paint the ground.'], extend: ['Extend', 'Build out piece by piece from the open edges.'],
  light: ['Game light', ''], view: ['View', 'Camera views (top, isometric, flat), the grid, wireframe, field of view, fog and how far you see.'],
  show: ['Show', ''], lock: ['Lock walls', ''], home: ['Start view', 'Back to where the view started.'], help: ['Controls', 'How the mouse and keys work in the 3D view.'],
  'w-panels': ['Panels', 'Open, close and arrange the tools; ready-made layouts.'], 'w-show': ['Show', ''], 'w-lockb': ['Lock walls', ''],
  'w-full': ['Full view', 'Only the map or 3D, its buttons and windows. Again: everything back.', 'fullview'], 'vbar-more': ['More tools', 'The tools there\'s no room for on the bar.'],
  'map-0': ['Map', 'The flat map, seen from above.'], 'map-1': ['3D', 'See and build the place in 3D, as in the game.'],
  undobtn: ['Undo', '', 'undo'], redobtn: ['Redo', '', 'redo'], groupbtn: ['Group', ''], reload: ['Reload', 'Read openmw.cfg and every plugin again.'],
};
function tbTipKey(el){
  return el.dataset.v3 || el.id || (el.dataset.view3d != null ? 'map-' + el.dataset.view3d : '') || (el.querySelector && el.querySelector('[data-q]') ? 'q-' + el.querySelector('[data-q]').dataset.q : '');
}
function tbTipHtml(el, own){
  const T = TB_TIP[tbTipKey(el)];
  const word = el.querySelector && el.querySelector('.tl') ? el.querySelector('.tl').textContent.trim() : '';
  let name = T ? T[0] : (word || (el.closest('nav') ? el.textContent.trim() : ''));
  let what = T && T[1] ? T[1] : own;
  // (a title that starts with the name says it again: "Undo: Placed a chair (Ctrl+Z)" shows as Undo, then the rest)
  if (name && what && what.toLowerCase().startsWith(name.toLowerCase()) && !/[a-z]/i.test(what.charAt(name.length))) what = what.slice(name.length).replace(/^[\s:,.—-]+/, '');
  let key = '';
  if (T && T[2] && typeof CF_ACT !== 'undefined' && typeof cfKeysOf === 'function'){ const a = CF_ACT.find(x => x.id === T[2]); if (a) key = cfKeysOf(a).join(' or '); }
  const m = !key && what && what.match(/\s*\(([^()]{1,14})\)\s*$/);
  if (m && /^(?:[A-Z][a-z]*\+)*(?:[A-Z0-9]|F\d+|End|Del|Home|Num \d)$/.test(m[1])){ key = m[1]; what = what.slice(0, m.index); }
  if (!name && !what) return '';
  return `${name ? `<b>${esc(name)}</b>` : ''}${key ? `<kbd>${esc(key)}</kbd>` : ''}${what ? `<div>${esc(what)}</div>` : ''}`;
}
(function(){
  const c = document.createElement('style');
  c.textContent = `.wstip{position:fixed;z-index:10000;max-width:280px;padding:7px 10px;border-radius:8px;background:var(--panel2);border:1px solid var(--goldline);
    color:var(--text);font:13px/1.4 var(--font-body,Inter,"Segoe UI",sans-serif);box-shadow:0 8px 26px #000a;pointer-events:none;opacity:0;transition:opacity .12s}
  .wstip.on{opacity:1}
  .wstip b{color:var(--gold2);font-weight:600}
  .wstip kbd{margin-left:8px;font:11px var(--mono);color:var(--text);background:var(--deep);border:1px solid var(--line2);border-radius:4px;padding:0 5px}
  .wstip div{color:var(--muted);margin-top:2px;font-size:12.5px}
  .th-calm .wstip{transition:none}`;
  document.head.appendChild(c);
  const tip = document.createElement('div'); tip.className = 'wstip'; document.body.appendChild(tip);
  let at = null, t = 0;
  const AREA = '#vbar, #v3tools, #viewsw, .mbar, header nav';
  const hide = () => { clearTimeout(t); at = null; tip.classList.remove('on'); };
  document.addEventListener('mouseover', e => {
    const area = e.target.closest && e.target.closest(AREA); if (!area){ if (at) hide(); return; }
    const el = e.target.closest('button, .v3q, select'); if (!el || !area.contains(el) || el === at) return;
    const host = el.tagName === 'SELECT' && el.closest('.v3q') ? el.closest('.v3q') : el;
    if (host === at) return;
    hide(); at = host;
    // (the browser's tip kept aside, so the two don't show at once; code that sets the title again is read next time)
    if (host.title){ host.dataset.wtip = host.title; host.removeAttribute('title'); }
    if (host.closest('.omwmenu, .v3viewmenu')) return;        // (inside an open menu the lines say it already)
    t = setTimeout(() => {
      const h = tbTipHtml(host, host.dataset.wtip || ''); if (!h || at !== host || !host.isConnected) return;
      tip.innerHTML = h; tip.classList.add('on');
      const r = host.getBoundingClientRect(), w = tip.offsetWidth, hh = tip.offsetHeight;
      let x = Math.max(6, Math.min(innerWidth - w - 6, r.left + r.width / 2 - w / 2)), y = r.bottom + 6;
      if (y + hh > innerHeight - 6) y = r.top - hh - 6;
      tip.style.left = x + 'px'; tip.style.top = y + 'px';
    }, 280);
  });
  document.addEventListener('mousedown', hide, true);
  document.addEventListener('wheel', hide, {passive: true, capture: true});
  window.addEventListener('blur', hide);
})();
