// Tool panels: every tool is a panel you can move, resize, fold, close, dock on the left, right or
// bottom, tab together with others, and open more than once (some). How they are laid out is kept,
// with ready-made layouts and your own.
//
// A "space" is one page's set of panels (the World map's, say): docks round its middle part and a
// layer above it for floating panels. Panel types say how to draw themselves into their body; the
// bodies stay the same element while panels move about, so what's in them (scroll, typing) survives.
const PNL = {spaces: {}};

function pnlCss(){
  if ($('#pnl-css')) return;
  const c = document.createElement('style'); c.id = 'pnl-css';
  c.textContent = `
  .pspace{position:absolute;inset:0;min-height:0}
  .pspace:not(.view),.view.pspace.on{display:flex}
  .pcenter{flex:1;display:flex;flex-direction:column;min-width:min(300px, 34%);min-height:0}
  .pcenter > .pmain{flex:1;min-height:0;position:relative}
  .pdock{display:flex;min-width:0;min-height:0;background:var(--panel);position:relative}
  .pdock[data-dock=left],.pdock[data-dock=right]{flex-direction:column}
  .pdock[data-dock=left]{border-right:1px solid var(--line)}
  .pdock[data-dock=right]{border-left:1px solid var(--line)}
  .pdock[data-dock=bottom]{flex-direction:row;border-top:1px solid var(--line)}
  .pdock:empty{display:none}
  .pfloat{position:absolute;inset:0;pointer-events:none;z-index:40}
  .pgroup{display:flex;flex-direction:column;min-width:0;min-height:0;background:var(--panel);position:relative}
  .pdock .pgroup{flex:1 1 0}
  .pdock[data-dock=left] .pgroup + .pgroup,.pdock[data-dock=right] .pgroup + .pgroup{border-top:1px solid var(--line)}
  .pdock[data-dock=bottom] .pgroup + .pgroup{border-left:1px solid var(--line)}
  .pfloat .pgroup{position:absolute;pointer-events:auto;border:1px solid var(--line2);border-radius:10px;box-shadow:0 14px 44px #000b;overflow:hidden}
  .pgroup.folded .pbodies{display:none}
  .pfloat .pgroup.folded{height:auto!important}
  .phead{display:flex;align-items:stretch;gap:2px;background:var(--bg2-b);border-bottom:1px solid var(--line);min-height:32px;cursor:grab;user-select:none;flex:none}
  .pfloat .phead{background:var(--bg3-b)}
  .ptabs{display:flex;flex:1;min-width:0;overflow-x:auto;overflow-y:hidden;scrollbar-width:none}
  .ptabs::-webkit-scrollbar{display:none}
  .ptabs.more-r{-webkit-mask-image:linear-gradient(90deg,#000 calc(100% - 28px),transparent);mask-image:linear-gradient(90deg,#000 calc(100% - 28px),transparent)}
  .ptabs.more-l{-webkit-mask-image:linear-gradient(90deg,transparent,#000 28px);mask-image:linear-gradient(90deg,transparent,#000 28px)}
  .ptabs.more-l.more-r{-webkit-mask-image:linear-gradient(90deg,transparent,#000 28px,#000 calc(100% - 28px),transparent);mask-image:linear-gradient(90deg,transparent,#000 28px,#000 calc(100% - 28px),transparent)}
  .ptab{background:none;border:0;border-bottom:2px solid transparent;color:var(--faint);padding:6px 7px 5px;cursor:pointer;font:inherit;font-size:12.5px;white-space:nowrap;display:flex;align-items:center;gap:4px;flex:none;max-width:150px;overflow:hidden}
  .ptab span{display:block;flex:0 1 auto;min-width:0}
  .ptab b,.ptab i{flex:none}
  .ptab.on{flex:none;max-width:200px}
  .ptab span{overflow:hidden;text-overflow:ellipsis}
  .ptab:hover{color:var(--muted)}
  .ptab.on{color:var(--gold2);border-bottom-color:var(--gold)}
  .ptab b{font-weight:600;font-size:11px;color:var(--faint)}
  .ptab i{font-style:normal;opacity:0;padding:0 2px;border-radius:4px;font-size:11px}
  .ptab:hover i{opacity:.7}.ptab i:hover{opacity:1;background:#ffffff18}
  .pbtns{display:flex;align-items:center;gap:1px;padding-right:4px;flex:none}
  .pbtns button{background:none;border:0;color:var(--faint);cursor:pointer;font-size:13px;width:24px;height:24px;border-radius:5px;line-height:1}
  .pbtns button:hover{background:#ffffff14;color:var(--text)}
  .pbodies{flex:1;min-height:0;position:relative}
  .pbody{position:absolute;inset:0;overflow:auto;display:none}
  .pbody.on{display:block}
  .prs{position:absolute;z-index:3}
  .prs.e{right:-3px;top:8px;bottom:8px;width:7px;cursor:ew-resize}.prs.w{left:-3px;top:8px;bottom:8px;width:7px;cursor:ew-resize}
  .prs.s{bottom:-3px;left:8px;right:8px;height:7px;cursor:ns-resize}.prs.n{top:-3px;left:8px;right:8px;height:7px;cursor:ns-resize}
  .prs.se{right:-3px;bottom:-3px;width:14px;height:14px;cursor:nwse-resize}.prs.sw{left:-3px;bottom:-3px;width:14px;height:14px;cursor:nesw-resize}
  .psplit{flex:none;background:transparent;z-index:5;position:relative}
  .psplit:hover,.psplit.drag{background:var(--gold)}
  .pdock > .psplit.v{z-index:50}
  .pdock > .psplit.v::after{content:'';position:absolute;left:50%;top:50%;width:3px;height:28px;margin:-14px 0 0 -1.5px;border-radius:2px;background:var(--line2);opacity:.8}
  .psplit.v{width:5px;margin:0 -2px;cursor:ew-resize}.psplit.h{height:5px;margin:-2px 0;cursor:ns-resize}
  .pdrop{position:absolute;pointer-events:none;background:#d9b26a33;border:2px dashed var(--gold);border-radius:8px;z-index:60;display:none}
  .pdragging .pgroup *{pointer-events:none}
  .pdragging .pfloat .pgroup.moving{opacity:.85}
  .pmenu{position:fixed;z-index:200;background:var(--panel);border:1px solid var(--line2);border-radius:8px;box-shadow:0 12px 40px #000c;padding:4px;min-width:200px}
  .pmenu button{display:block;width:100%;text-align:left;background:none;border:0;color:var(--text);padding:6px 10px;border-radius:5px;cursor:pointer;font:inherit;font-size:13px}
  .pmenu button:hover{background:#ffffff12}
  .pmenu hr{border:0;border-top:1px solid var(--line);margin:4px 0}
  .pmenu .on::before{content:'✓ ';color:var(--gold2)}`;
  document.head.appendChild(c);
}

// ---------------------------------------------------------------- spaces
// root: the page's element; main: the element in the middle (the map); opts: {presets: {name: layout}, start: preset name, onResize}
PNL.space = function(name, root, main, opts){
  pnlCss();
  const sp = {name, root, opts: opts || {}, types: {}, inst: {}, layout: null, n: 0};
  root.classList.add('pspace');
  const left = document.createElement('div'); left.className = 'pdock'; left.dataset.dock = 'left';
  const right = document.createElement('div'); right.className = 'pdock'; right.dataset.dock = 'right';
  const bottom = document.createElement('div'); bottom.className = 'pdock'; bottom.dataset.dock = 'bottom';
  const center = document.createElement('div'); center.className = 'pcenter';
  const fl = document.createElement('div'); fl.className = 'pfloat';
  const drop = document.createElement('div'); drop.className = 'pdrop';
  main.classList.add('pmain');
  root.insertBefore(left, root.firstChild);
  root.insertBefore(center, left.nextSibling);
  center.appendChild(main); center.appendChild(bottom);
  root.appendChild(right); root.appendChild(fl); root.appendChild(drop);
  sp.els = {left, right, bottom, center, float: fl, drop, main};
  PNL.spaces[name] = sp;
  if (window.ResizeObserver){
    let pend = false;
    new ResizeObserver(() => { if (pend) return; pend = true; requestAnimationFrame(() => { pend = false; if (sp.opts.onResize) sp.opts.onResize(); }); }).observe(main);
  }
  window.addEventListener('resize', () => pnlClampFloats(sp));
  return sp;
};

PNL.define = function(space, type, def){
  PNL.spaces[space].types[type] = Object.assign({multi: false, home: 'right'}, def);
};

// the layout kept from last time (or the first preset), once the panel types are defined
PNL.start = function(space){
  const sp = PNL.spaces[space];
  let saved = null;
  try { saved = JSON.parse(localStorage.getItem('ws-panels-' + space) || 'null'); } catch (e){}
  if (saved && saved.layout){
    sp.n = saved.n || 0;
    for (const [id, st] of Object.entries(saved.extra || {})) pnlMake(sp, id, st);
    sp.layout = pnlValid(sp, saved.layout);
  } else sp.layout = pnlCopy(sp.opts.presets[sp.opts.start]);
  pnlDraw(sp);
};

function pnlCopy(o){ return JSON.parse(JSON.stringify(o)); }

// (a kept layout naming panels that don't exist any more: those left out)
function pnlValid(sp, L){
  const ok = id => !!(sp.types[id.split('~')[0]] && (id.indexOf('~') < 0 || sp.inst[id]));
  const fix = g => { g.tabs = g.tabs.filter(ok); if (!g.tabs.includes(g.on)) g.on = g.tabs[0]; return g.tabs.length; };
  for (const d of ['left', 'right', 'bottom']){ L[d] = L[d] || {size: d === 'bottom' ? 220 : 320, groups: []}; L[d].groups = L[d].groups.filter(fix); }
  L.floats = (L.floats || []).filter(fix);
  return L;
}

function pnlSave(sp){
  const extra = {};
  for (const [id, it] of Object.entries(sp.inst)) if (id.indexOf('~') >= 0 && pnlWhere(sp, id)) extra[id] = it.state || {};
  try { localStorage.setItem('ws-panels-' + sp.name, JSON.stringify({layout: sp.layout, n: sp.n, extra})); } catch (e){}
}

function pnlMake(sp, id, state){
  if (sp.inst[id]) return sp.inst[id];
  const t = sp.types[id.split('~')[0]]; if (!t) return null;
  const body = document.createElement('div');
  body.className = 'pbody ' + (t.cls || '');
  body.dataset.pbody = id;   // (not data-pid: the World map uses that for tiles to place)
  const it = sp.inst[id] = {id, type: id.split('~')[0], el: body, state: state || {}, badge: ''};
  if (t.init) t.init(it);
  return it;
}

// where a panel is: {group, list, where ('left'|'right'|'bottom'|'float'), index} or null (closed)
function pnlWhere(sp, id){
  const L = sp.layout; if (!L) return null;
  for (const d of ['left', 'right', 'bottom']) for (let i = 0; i < L[d].groups.length; i++) if (L[d].groups[i].tabs.includes(id)) return {group: L[d].groups[i], list: L[d].groups, where: d, index: i};
  for (let i = 0; i < L.floats.length; i++) if (L.floats[i].tabs.includes(id)) return {group: L.floats[i], list: L.floats, where: 'float', index: i};
  return null;
}

// ---------------------------------------------------------------- drawing
function pnlTitle(sp, id){
  const it = sp.inst[id], t = sp.types[it.type];
  const title = (t.titleFor && t.titleFor(it)) || t.title;
  return (t.icon ? t.icon + ' ' : '') + title;
}

function pnlDraw(sp){
  const L = sp.layout, E = sp.els;
  for (const d of ['left', 'right', 'bottom']){
    const dock = E[d];
    dock.innerHTML = '';
    const gs = L[d].groups;
    if (!gs.length){ dock.style.width = dock.style.height = ''; continue; }
    // (on a small screen the docks give way, so the middle keeps some room: .pcenter's own minimum width
    // makes the docks shrink; a fixed 36% cap with both docks open undid a wider record on every redraw)
    if (d === 'bottom') dock.style.height = `min(${L[d].size}px, 45%)`; else dock.style.width = `min(${L[d].size}px, 60%)`;
    gs.forEach((g, i) => {
      if (i) dock.appendChild(pnlSplitter(sp, d, i));
      const el = pnlGroupEl(sp, g, d);
      el.style.flexGrow = g.grow || 1;
      dock.appendChild(el);
    });
    // the edge between the dock and the middle, to make it wider or narrower
    const edge = document.createElement('div');
    edge.className = 'psplit ' + (d === 'bottom' ? 'h' : 'v');
    edge.style.position = 'absolute';
    // (a wide edge, over the list's scrollbar beside it: a 5 px one was hard to find, "no way to expand the middle")
    if (d === 'left'){ Object.assign(edge.style, {right: '-5px', top: 0, bottom: 0, margin: 0, width: '9px'}); }
    if (d === 'right'){ Object.assign(edge.style, {left: '-5px', top: 0, bottom: 0, margin: 0, width: '9px'}); }
    if (d === 'bottom'){ Object.assign(edge.style, {top: '-3px', left: 0, right: 0, margin: 0}); }
    edge.onpointerdown = e => pnlDockResize(sp, d, e, edge);
    dock.appendChild(edge);
  }
  E.float.innerHTML = '';
  L.floats.forEach(g => {
    const el = pnlGroupEl(sp, g, 'float');
    Object.assign(el.style, {left: g.x + 'px', top: g.y + 'px', width: g.w + 'px', height: g.h + 'px'});
    for (const k of ['n', 'e', 's', 'w', 'se', 'sw']){
      const h = document.createElement('div'); h.className = 'prs ' + k;
      h.onpointerdown = e => pnlFloatResize(sp, g, el, k, e);
      el.appendChild(h);
    }
    E.float.appendChild(el);
  });
  pnlClampFloats(sp);
  // bodies of closed panels are left out of the page (their drawing finds nothing to draw into)
  for (const it of Object.values(sp.inst)) if (!pnlWhere(sp, it.id) && it.el.parentNode) it.el.remove();
  pnlSave(sp);
  if (sp.opts.onLayout) sp.opts.onLayout();
}

function pnlGroupEl(sp, g, where){
  const el = document.createElement('div');
  el.className = 'pgroup' + (g.fold ? ' folded' : '');
  g.tabs.forEach(id => pnlMake(sp, id));
  el.innerHTML = `<div class="phead"><div class="ptabs">${g.tabs.map(id => `<button class="ptab ${id === g.on ? 'on' : ''}" data-ptab="${esc(id)}" title="Drag the tab to move this panel; drag the bar to move them all"><span>${esc(pnlTitle(sp, id))}</span>${sp.inst[id].badge ? `<b>${esc(sp.inst[id].badge)}</b>` : ''}<i data-pclose="${esc(id)}" title="Close">✕</i></button>`).join('')}</div>
    <span class="pbtns"><button data-pact="fold" title="${g.fold ? 'Open it up' : 'Fold it away (only the title stays)'}">${g.fold ? '▢' : '▁'}</button><button data-pact="menu" title="Dock it, float it, open another…">⋮</button></span></div><div class="pbodies"></div>`;
  const bodies = el.querySelector('.pbodies');
  g.tabs.forEach(id => { const b = sp.inst[id].el; b.classList.toggle('on', id === g.on); bodies.appendChild(b); });
  const head = el.querySelector('.phead');
  head.onpointerdown = e => {
    if (e.button !== 0) return;
    const close = e.target.closest('[data-pclose]');
    if (close){ e.stopPropagation(); return; }
    if (e.target.closest('.pbtns')) return;
    pnlBringFront(sp, g);
    const tab = e.target.closest('[data-ptab]');
    pnlDragStart(sp, g, tab ? tab.dataset.ptab : null, e, el, where);
  };
  head.querySelectorAll('[data-pclose]').forEach(x => x.onclick = e => { e.stopPropagation(); PNL.close(sp.name, x.dataset.pclose); });
  head.querySelector('[data-pact=fold]').onclick = () => { g.fold = !g.fold; pnlDraw(sp); };
  head.querySelector('[data-pact=menu]').onclick = e => pnlGroupMenu(sp, g, where, e.currentTarget);
  // many tabs: the wheel scrolls along them, and the one in front stays in sight
  const strip = head.querySelector('.ptabs');
  strip.onwheel = e => { if (strip.scrollWidth > strip.clientWidth){ strip.scrollLeft += e.deltaY || e.deltaX; e.preventDefault(); } };
  // (a soft fade at an edge says there are more tabs that way)
  const edges = () => { const more = strip.scrollWidth > strip.clientWidth + 1; strip.classList.toggle('more-l', more && strip.scrollLeft > 1); strip.classList.toggle('more-r', more && strip.scrollLeft + strip.clientWidth < strip.scrollWidth - 1); };
  strip.onscroll = edges;
  requestAnimationFrame(() => { const on = strip.querySelector('.ptab.on'); if (on && strip.scrollWidth > strip.clientWidth) strip.scrollLeft = Math.max(0, on.offsetLeft - 30); edges(); });
  head.ondblclick = e => { if (!e.target.closest('.pbtns') && where === 'float'){ g.fold = !g.fold; pnlDraw(sp); } };
  if (where === 'float') el.onpointerdown = () => pnlBringFront(sp, g, el);
  return el;
}

function pnlBringFront(sp, g, el){
  const L = sp.layout, i = L.floats.indexOf(g);
  if (i < 0 || i === L.floats.length - 1) return;
  L.floats.splice(i, 1); L.floats.push(g);
  if (el && el.parentNode) el.parentNode.appendChild(el);
  pnlSave(sp);
}

function pnlClampFloats(sp){
  const r = sp.root.getBoundingClientRect();
  if (!r.width) return;
  for (const g of sp.layout ? sp.layout.floats : []){
    g.w = Math.min(Math.max(220, g.w), r.width); g.h = Math.min(Math.max(120, g.h), r.height);
    if (g.x < 0) g.x = r.width - g.w + g.x;           // (a layout's "this far from the right")
    g.x = Math.min(Math.max(0, g.x), Math.max(0, r.width - 120)); g.y = Math.min(Math.max(0, g.y), Math.max(0, r.height - 34));
  }
  sp.els.float.querySelectorAll('.pgroup').forEach((el, i) => {
    const g = sp.layout.floats[i]; if (!g) return;
    Object.assign(el.style, {left: g.x + 'px', top: g.y + 'px', width: g.w + 'px', height: g.h + 'px'});
  });
}

// ---------------------------------------------------------------- moving and docking
function pnlDragStart(sp, g, tabId, e, el, where){
  const sx = e.clientX, sy = e.clientY, R = sp.root.getBoundingClientRect();
  let moving = null, drop = null;
  const up = () => {
    window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up);
    sp.root.classList.remove('pdragging'); sp.els.drop.style.display = 'none';
    if (!moving){
      // a click on a tab: show that panel
      if (tabId && g.on !== tabId){ g.on = tabId; pnlDraw(sp); const t = sp.types[sp.inst[tabId].type]; if (t.onShow) t.onShow(sp.inst[tabId]); }
      return;
    }
    if (drop) pnlDropInto(sp, moving, drop);
    pnlDraw(sp);
  };
  const move = ev => {
    const dx = ev.clientX - sx, dy = ev.clientY - sy;
    if (!moving){
      if (Math.abs(dx) + Math.abs(dy) < 6) return;
      // what moves: the tab on its own (from a group of several), or the whole group, which floats
      const r = el.getBoundingClientRect();
      const w = where === 'float' ? g.w : Math.min(Math.max(260, r.width), 420), h = where === 'float' ? g.h : Math.min(Math.max(220, r.height), 520);
      if (tabId && g.tabs.length > 1){
        g.tabs = g.tabs.filter(t => t !== tabId); if (g.on === tabId) g.on = g.tabs[0];
        moving = {tabs: [tabId], on: tabId, x: ev.clientX - R.left - 60, y: ev.clientY - R.top - 14, w, h};
        sp.layout.floats.push(moving);
      } else if (where !== 'float'){
        const W_ = pnlWhere(sp, g.tabs[0]); W_.list.splice(W_.index, 1);
        moving = Object.assign(g, {x: ev.clientX - R.left - 60, y: ev.clientY - R.top - 14, w, h, fold: false});
        sp.layout.floats.push(moving);
      } else moving = g;
      moving._ox = ev.clientX - R.left - moving.x; moving._oy = ev.clientY - R.top - moving.y;
      pnlDraw(sp);
      sp.root.classList.add('pdragging');
    }
    moving.x = ev.clientX - R.left - moving._ox; moving.y = ev.clientY - R.top - moving._oy;
    const fe = sp.els.float.children[sp.layout.floats.indexOf(moving)];
    if (fe){ fe.style.left = moving.x + 'px'; fe.style.top = moving.y + 'px'; fe.classList.add('moving'); }
    drop = pnlDropAt(sp, moving, ev.clientX, ev.clientY);
  };
  window.addEventListener('pointermove', move); window.addEventListener('pointerup', up);
}

// where a moving panel would go if let go here: a dock's edge, or another panel's tabs (to join them)
function pnlDropAt(sp, moving, cx, cy){
  const R = sp.root.getBoundingClientRect(), D = sp.els.drop, x = cx - R.left, y = cy - R.top, edge = 48;
  const show = (l, t, w, h) => Object.assign(D.style, {display: 'block', left: l + 'px', top: t + 'px', width: w + 'px', height: h + 'px'});
  // onto another group's title bar
  const heads = [...sp.root.querySelectorAll('.pgroup')].filter(el => !el.classList.contains('moving'));
  for (const el of heads){
    const h = el.querySelector('.phead').getBoundingClientRect();
    if (cx >= h.left && cx <= h.right && cy >= h.top && cy <= h.bottom){
      const g = pnlGroupOf(sp, el);
      if (g && g !== moving){ const r = el.getBoundingClientRect(); show(r.left - R.left, r.top - R.top, r.width, r.height); return {join: g}; }
    }
  }
  const L = sp.layout;
  if (x < edge){ show(0, 0, Math.max(L.left.size, 260), R.height); return {dock: 'left'}; }
  if (x > R.width - edge){ show(R.width - Math.max(L.right.size, 260), 0, Math.max(L.right.size, 260), R.height); return {dock: 'right'}; }
  if (y > R.height - edge){ const c = sp.els.center.getBoundingClientRect(); show(c.left - R.left, R.height - Math.max(L.bottom.size, 180), c.width, Math.max(L.bottom.size, 180)); return {dock: 'bottom'}; }
  D.style.display = 'none';
  return null;
}

function pnlGroupOf(sp, el){
  const L = sp.layout;
  if (el.parentNode === sp.els.float) return L.floats[[...sp.els.float.children].indexOf(el)];
  for (const d of ['left', 'right', 'bottom']){
    if (el.parentNode === sp.els[d]) return L[d].groups[[...sp.els[d].children].filter(c => c.classList.contains('pgroup')).indexOf(el)];
  }
  return null;
}

function pnlDropInto(sp, moving, drop){
  const L = sp.layout;
  L.floats.splice(L.floats.indexOf(moving), 1);
  delete moving._ox; delete moving._oy;
  if (drop.join){
    drop.join.tabs.push(...moving.tabs); drop.join.on = moving.on; drop.join.fold = false;
  } else {
    const d = L[drop.dock];
    d.groups.push({tabs: moving.tabs, on: moving.on, grow: 1});
    if (!d.size || d.groups.length === 1) d.size = d.size || (drop.dock === 'bottom' ? 220 : 320);
  }
}

function pnlFloatResize(sp, g, el, k, e){
  e.stopPropagation(); e.preventDefault();
  const sx = e.clientX, sy = e.clientY, o = {x: g.x, y: g.y, w: g.w, h: g.h};
  const move = ev => {
    const dx = ev.clientX - sx, dy = ev.clientY - sy;
    if (k.includes('e')) g.w = Math.max(220, o.w + dx);
    if (k.includes('s')) g.h = Math.max(120, o.h + dy);
    if (k.includes('w')){ g.w = Math.max(220, o.w - dx); g.x = o.x + o.w - g.w; }
    if (k === 'n'){ g.h = Math.max(120, o.h - dy); g.y = o.y + o.h - g.h; }
    Object.assign(el.style, {left: g.x + 'px', top: g.y + 'px', width: g.w + 'px', height: g.h + 'px'});
  };
  const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); pnlSave(sp); };
  window.addEventListener('pointermove', move); window.addEventListener('pointerup', up);
}

function pnlDockResize(sp, d, e, edge){
  e.preventDefault();
  const L = sp.layout[d], DR = sp.els[d].getBoundingClientRect(), s0 = Math.round(d === 'bottom' ? DR.height : DR.width), sx = e.clientX, sy = e.clientY, R = sp.root.getBoundingClientRect();
  edge.classList.add('drag');
  const move = ev => {
    const delta = d === 'left' ? ev.clientX - sx : d === 'right' ? sx - ev.clientX : sy - ev.clientY;
    // (the middle keeps 300 across whatever the other side holds: the left dock widened over a 38% record
    // squeezed the Browse list to nothing and its rows ran over the record, the user's video)
    const other = d === 'left' ? sp.els.right : d === 'right' ? sp.els.left : null;
    const ow = other && sp.layout[d === 'left' ? 'right' : 'left'].groups.length ? other.getBoundingClientRect().width : 0;
    const max = d === 'bottom' ? R.height * 0.7 : Math.max(220, Math.min(R.width * 0.6, R.width - ow - 300));
    L.size = Math.round(Math.min(max, Math.max(d === 'bottom' ? 110 : 220, s0 + delta)));
    if (d === 'bottom') sp.els[d].style.height = L.size + 'px'; else sp.els[d].style.width = L.size + 'px';
  };
  // (let go: back to giving way when the room shrinks, as pnlDraw sets it: a window made narrower afterwards
  // still leaves the middle some room)
  const up = () => { edge.classList.remove('drag'); window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up);
    if (d === 'bottom') sp.els[d].style.height = `min(${L.size}px, 45%)`; else sp.els[d].style.width = `min(${L.size}px, 60%)`;
    pnlSave(sp); };
  window.addEventListener('pointermove', move); window.addEventListener('pointerup', up);
}

// between two groups in a dock: how the room is shared
function pnlSplitter(sp, d, i){
  const s = document.createElement('div');
  s.className = 'psplit ' + (d === 'bottom' ? 'v' : 'h');
  s.onpointerdown = e => {
    e.preventDefault();
    const gs = sp.layout[d].groups, a = gs[i - 1], b = gs[i];
    const els = [...sp.els[d].children].filter(c => c.classList.contains('pgroup'));
    const ea = els[i - 1], eb = els[i];
    const horiz = d === 'bottom';
    const sa = horiz ? ea.offsetWidth : ea.offsetHeight, sb = horiz ? eb.offsetWidth : eb.offsetHeight, tot = (a.grow || 1) + (b.grow || 1);
    const start = horiz ? e.clientX : e.clientY;
    s.classList.add('drag');
    const move = ev => {
      const delta = (horiz ? ev.clientX : ev.clientY) - start;
      const na = Math.max(60, sa + delta), nb = Math.max(60, sb - delta);
      a.grow = tot * na / (na + nb); b.grow = tot * nb / (na + nb);
      ea.style.flexGrow = a.grow; eb.style.flexGrow = b.grow;
    };
    const up = () => { s.classList.remove('drag'); window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); pnlSave(sp); };
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up);
  };
  return s;
}

// ---------------------------------------------------------------- menus
function pnlMenu(anchor, items){
  document.querySelectorAll('.pmenu').forEach(m => m.remove());
  const m = document.createElement('div'); m.className = 'pmenu';
  m.innerHTML = items.map((it, n) => it === '-' ? '<hr>' : `<button data-pm="${n}" class="${it.on ? 'on' : ''}" ${it.disabled ? 'disabled style="opacity:.45"' : ''}>${esc(it.label)}</button>`).join('');
  document.body.appendChild(m);
  // (anchor: an element to open under, or a spot {x, y} such as where the mouse was right-clicked)
  const r = anchor.getBoundingClientRect ? anchor.getBoundingClientRect() : {left: anchor.x, top: anchor.y, bottom: anchor.y};
  const left = Math.min(window.innerWidth - m.offsetWidth - 8, r.left), top = r.bottom + m.offsetHeight > window.innerHeight ? Math.max(8, r.top - m.offsetHeight) : r.bottom + 4;
  Object.assign(m.style, {left: Math.max(8, left) + 'px', top: top + 'px'});
  m.onclick = e => { const b = e.target.closest('[data-pm]'); if (!b) return; const it = items[+b.dataset.pm]; m.remove(); if (it.act) it.act(); };
  setTimeout(() => document.addEventListener('pointerdown', function off(e){ if (!m.contains(e.target)){ m.remove(); document.removeEventListener('pointerdown', off); } }), 0);
  const esc_ = e => { if (e.key === 'Escape'){ m.remove(); document.removeEventListener('keydown', esc_, true); } };
  document.addEventListener('keydown', esc_, true);
  return m;
}

function pnlGroupMenu(sp, g, where, anchor){
  const id = g.on, it = sp.inst[id], t = sp.types[it.type];
  const items = [];
  if (where !== 'float') items.push({label: 'Float it', act: () => pnlMoveGroup(sp, g, 'float')});
  for (const d of ['left', 'right', 'bottom']) if (where !== d) items.push({label: 'Dock it ' + {left: 'on the left', right: 'on the right', bottom: 'at the bottom'}[d], act: () => pnlMoveGroup(sp, g, d)});
  if (t.multi) items.push('-', {label: 'Open another ' + t.title, act: () => PNL.open(sp.name, it.type, t.cloneState ? t.cloneState(it) : {})});
  if (t.menu) items.push('-', ...t.menu(it));
  items.push('-', {label: 'Close ' + pnlTitle(sp, id), act: () => PNL.close(sp.name, id)});
  if (g.tabs.length > 1) items.push({label: 'Close all of these', act: () => g.tabs.slice().forEach(x => PNL.close(sp.name, x))});
  pnlMenu(anchor, items);
}

function pnlMoveGroup(sp, g, to){
  const w = pnlWhere(sp, g.tabs[0]); if (!w) return;
  w.list.splice(w.index, 1);
  const L = sp.layout, R = sp.root.getBoundingClientRect();
  if (to === 'float') L.floats.push({tabs: g.tabs, on: g.on, x: R.width / 2 - 170, y: 60, w: 340, h: Math.min(520, R.height - 100)});
  else { L[to].groups.push({tabs: g.tabs, on: g.on, grow: 1}); if (!L[to].size) L[to].size = to === 'bottom' ? 220 : 320; }
  pnlDraw(sp);
}

// ---------------------------------------------------------------- what pages use
// show a panel (opening it where it lives, or where it was last), in front and unfolded
PNL.show = function(space, id){
  const sp = PNL.spaces[space]; if (!sp || !sp.layout) return null;
  let w = pnlWhere(sp, id);
  const fresh = !sp.inst[id];
  const it = pnlMake(sp, id); if (!it) return null;
  if (fresh && id.indexOf('~') < 0 && sp.types[it.type].render) sp.types[it.type].render(it);
  if (!w){
    const t = sp.types[it.type], L = sp.layout, R = sp.root.getBoundingClientRect();
    if (t.home === 'float' || !['left', 'right', 'bottom'].includes(t.home)){
      const n = L.floats.length;
      L.floats.push({tabs: [id], on: id, x: Math.max(20, R.width / 2 - 180 + n * 24), y: 60 + n * 24, w: t.w || 360, h: Math.min(t.h || 480, R.height - 80)});
    } else {
      const d = L[t.home];
      if (d.groups.length) { d.groups[0].tabs.push(id); d.groups[0].on = id; }
      else { d.groups.push({tabs: [id], on: id, grow: 1}); d.size = d.size || (t.home === 'bottom' ? 220 : 320); }
    }
  } else { w.group.on = id; w.group.fold = false; if (w.where === 'float') pnlBringFront(sp, w.group); }
  pnlDraw(sp);
  const t = sp.types[it.type]; if (t.onShow) t.onShow(it);
  return it;
};

PNL.open = function(space, type, state){
  const sp = PNL.spaces[space];
  sp.n += 1;
  const id = type + '~' + sp.n;
  pnlMake(sp, id, state);
  const t = sp.types[type];
  if (t.render) t.render(sp.inst[id]);
  return PNL.show(space, id);
};

PNL.close = function(space, id){
  const sp = PNL.spaces[space], w = pnlWhere(sp, id); if (!w) return;
  w.group.tabs = w.group.tabs.filter(t => t !== id);
  if (w.group.on === id) w.group.on = w.group.tabs[0];
  if (!w.group.tabs.length) w.list.splice(w.list.indexOf(w.group), 1);
  const it = sp.inst[id];
  if (id.indexOf('~') >= 0){ it.el.remove(); delete sp.inst[id]; }
  pnlDraw(sp);
  const t = it && sp.types[it.type]; if (t && t.onClose) t.onClose(it);
};

PNL.isOpen = (space, id) => !!pnlWhere(PNL.spaces[space], id);
PNL.isShown = (space, id) => { const w = pnlWhere(PNL.spaces[space], id); return !!(w && w.group.on === id && !w.group.fold); };
PNL.body = (space, id) => { const sp = PNL.spaces[space]; const it = sp && pnlMake(sp, id); return it ? it.el : null; };
PNL.all = (space, type) => Object.values(PNL.spaces[space].inst).filter(it => it.type === type);

// a tab's little number (how many objects, a dot for a selection), and its title
PNL.badge = function(space, id, text){
  const sp = PNL.spaces[space], it = sp && sp.inst[id]; if (!it || it.badge === (text || '')) return;
  it.badge = text || '';
  const tab = sp.root.querySelector(`[data-ptab="${CSS.escape(id)}"]`);
  if (tab){ const b = tab.querySelector('b'); if (b) b.textContent = it.badge; else if (it.badge) tab.querySelector('span').insertAdjacentHTML('afterend', `<b>${esc(it.badge)}</b>`); }
};
PNL.retitle = function(space, id){
  const sp = PNL.spaces[space], tab = sp && sp.root.querySelector(`[data-ptab="${CSS.escape(id)}"] span`);
  if (tab) tab.textContent = pnlTitle(sp, id);
};

// layouts: a ready-made one, your own (kept by name), or back to the start
PNL.layouts = function(space){
  let mine = {};
  try { mine = JSON.parse(localStorage.getItem('ws-layouts-' + space) || '{}'); } catch (e){}
  return mine;
};
PNL.useLayout = function(space, L){
  const sp = PNL.spaces[space];
  sp.layout = pnlValid(sp, pnlCopy(L));
  pnlDraw(sp);
  for (const id of Object.keys(sp.inst)){ const t = sp.types[sp.inst[id].type]; if (PNL.isShown(space, id) && t.onShow) t.onShow(sp.inst[id]); }
};
PNL.saveLayout = function(space, name){
  const mine = PNL.layouts(space); mine[name] = pnlCopy(PNL.spaces[space].layout);
  try { localStorage.setItem('ws-layouts-' + space, JSON.stringify(mine)); } catch (e){}
};
PNL.deleteLayout = function(space, name){
  const mine = PNL.layouts(space); delete mine[name];
  try { localStorage.setItem('ws-layouts-' + space, JSON.stringify(mine)); } catch (e){}
};

// the menu of every panel there is, and the layouts (for a "Windows" button)
PNL.windowsMenu = function(space, anchor){
  const sp = PNL.spaces[space];
  const items = Object.entries(sp.types).filter(([_k, t]) => !t.hidden).map(([k, t]) => {
    const open = Object.keys(sp.inst).some(id => (id === k || id.startsWith(k + '~')) && pnlWhere(sp, id));
    return {label: (t.icon ? t.icon + ' ' : '') + t.title, on: open, act: () => PNL.isOpen(space, k) && !t.multi ? PNL.close(space, k) : (open && t.multi ? PNL.open(space, k, {}) : PNL.show(space, k))};
  });
  items.push('-');
  for (const [name, L] of Object.entries(sp.opts.presets)) items.push({label: 'Layout: ' + name, act: () => PNL.useLayout(space, L)});
  const mine = PNL.layouts(space);
  for (const [name, L] of Object.entries(mine)) items.push({label: 'My layout: ' + name, act: () => PNL.useLayout(space, L)});
  items.push('-', {label: 'Save this layout…', act: async () => { const n = await askText('A name for this layout:', 'My layout'); if (n && n.trim()){ PNL.saveLayout(space, n.trim().slice(0, 40)); toast('Saved the layout "' + n.trim() + '".'); } }});
  if (Object.keys(mine).length) items.push({label: 'Forget one of my layouts…', act: async () => { const n = await askText('Which one? (' + Object.keys(mine).join(', ') + ')', ''); if (n && mine[n.trim()]){ PNL.deleteLayout(space, n.trim()); toast('Forgot "' + n.trim() + '".'); } }});
  items.push({label: 'Back to the starting layout', act: () => PNL.useLayout(space, sp.opts.presets[sp.opts.start])});
  return pnlMenu(anchor, items);
};
