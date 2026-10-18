// The other pages as panels too (see panels.js). Browse: the categories and the record are panels,
// and any record can be pinned into a panel of its own, to compare several side by side. Dialogue,
// Characters, Lists, Rules and Scripts: the list on the left is a panel (move it, float it, make it
// wider, or close it for more room). On every one of them: a Notes panel for your own notes.
const PP = {pages: {
  dialog: {side: 'dside', main: 'dmain', title: 'Topics and quests'},
  chars: {side: 'cside', main: 'cmain', title: 'Characters'},
  lists: {side: 'lside', main: 'lmain', title: 'Lists'},
  rules: {side: 'rside', main: 'rmain', title: 'Rules'},
  scripts: {side: 'sside', main: 'smain', title: 'Scripts'},
}};

function ppCss(){
  if ($('#pp-css')) return;
  const c = document.createElement('style'); c.id = 'pp-css';
  c.textContent = `
  .pbody > .dside,.pbody > .side,.pbody > .detail{min-height:100%;box-sizing:border-box;border-right:0;overflow:visible}
  .pbody > .detail{padding:16px 20px 50px}
  .pbody > .side,.pbody > .dside{display:block}
  .pbody > .detail{position:static;display:block;inset:auto}
  .pcenter{position:relative}
  .pp-btn{position:absolute;bottom:10px;right:16px;z-index:30;background:var(--panel2);border:1px solid var(--line2);border-radius:7px;color:var(--muted);font-size:12px;padding:3px 9px;cursor:pointer;opacity:.75}
  .pp-btn:hover{opacity:1;color:var(--text);border-color:var(--gold)}
  .pp-tab{position:absolute;left:0;top:50%;transform:translateY(-50%);z-index:30;writing-mode:vertical-rl;background:var(--panel2);border:1px solid var(--line2);border-left:0;border-radius:0 7px 7px 0;color:var(--muted);font-size:12px;padding:10px 4px;cursor:pointer}
  .pp-tab:hover{color:var(--gold2)}
  .pp-notes{width:100%;height:calc(100% - 4px);box-sizing:border-box;resize:none;background:transparent;border:0;color:var(--text);font:inherit;font-size:13.5px;line-height:1.55;padding:12px 14px;outline:none}
  .pp-pinbar{display:flex;gap:6px;padding:8px 12px;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--panel);z-index:2}`;
  document.head.appendChild(c);
}

// a Notes panel (any number of them), kept in this browser
function ppNotes(space){
  PNL.define(space, 'notes', {title: 'Notes', icon: '🗒', home: 'float', multi: true, w: 320, h: 300,
    titleFor: it => it.state.title || 'Notes',
    render: it => {
      const k = 'ws-notes-' + space + '-' + it.id;
      let v = ''; try { v = localStorage.getItem(k) || ''; } catch (e){}
      it.el.innerHTML = `<textarea class="pp-notes" placeholder="Your notes: what's left to do, IDs to remember…">${esc(v)}</textarea>`;
      const t = it.el.querySelector('textarea');
      t.oninput = () => { try { localStorage.setItem(k, t.value); } catch (e){}
        const first = t.value.trim().split('\n')[0].slice(0, 24); if ((it.state.title || '') !== first){ it.state.title = first; PNL.retitle(space, it.id); } };
    }});
}

// panels kept from last time (pinned records, notes) draw themselves once the page has its panels
function ppRestore(space){
  const sp = PNL.spaces[space];
  for (const it of Object.values(sp.inst)){ const t = sp.types[it.type]; if (it.id.indexOf('~') >= 0 && t.render) t.render(it); }
}

// the small buttons on a page: the Panels menu, and a tab to bring back a list you closed
function ppButtons(space, sideId, label){
  const sp = PNL.spaces[space], c = sp.els.center;
  if (!c.querySelector('.pp-btn')){
    const b = document.createElement('button'); b.className = 'pp-btn'; b.textContent = '▤ Panels'; b.title = 'Open, close and arrange this page\'s panels';
    b.onclick = e => { e.stopPropagation(); PNL.windowsMenu(space, b); };
    c.appendChild(b);
  }
  sp.opts.onLayout = () => {
    let t = c.querySelector('.pp-tab');
    if (PNL.isOpen(space, sideId)){ if (t) t.remove(); return; }
    if (!t){ t = document.createElement('button'); t.className = 'pp-tab'; t.textContent = '▸ ' + label; t.title = 'Show the list again'; t.onclick = () => PNL.show(space, sideId); c.appendChild(t); }
  };
  sp.opts.onLayout();
}

function ppInit(view){
  if (typeof PNL === 'undefined' || PNL.spaces[view]) return;
  ppCss();
  if (view === 'browse') return ppBrowse();
  const P = PP.pages[view]; if (!P) return;
  const side = $('#' + P.side), main = $('#' + P.main); if (!side || !main) return;
  const L = (w, floats) => ({left: {size: w, groups: [{tabs: ['side'], on: 'side', grow: 1}]}, right: {size: 320, groups: []}, bottom: {size: 220, groups: []}, floats: floats || []});
  PNL.space(view, $('#' + view), main, {presets: {Standard: L(290), Wide: L(420), 'List floating': {left: {size: 290, groups: []}, right: {size: 320, groups: []}, bottom: {size: 220, groups: []},
    floats: [{tabs: ['side'], on: 'side', x: 16, y: 16, w: 300, h: 520}]}}, start: 'Standard'});
  PNL.define(view, 'side', {title: P.title, cls: 'ppside', home: 'left', init: it => it.el.appendChild(side)});
  ppNotes(view);
  PNL.start(view);
  ppRestore(view);
  ppButtons(view, 'side', P.title);
}

// ---------------------------------------------------------------- Browse
function ppBrowse(){
  const root = $('#browse'), list = root.querySelector('.list');
  const W40 = Math.max(380, Math.round(window.innerWidth * 0.38));
  const L = (cats, rec) => ({left: {size: 230, groups: cats ? [{tabs: ['cats'], on: 'cats', grow: 1}] : []}, right: {size: W40, groups: rec ? [{tabs: ['detail'], on: 'detail', grow: 1}] : []},
    bottom: {size: 240, groups: []}, floats: []});
  PNL.space('browse', root, list, {presets: {Standard: L(true, true), 'Record and list': L(false, true),
    'Compare records': {left: {size: 230, groups: [{tabs: ['cats'], on: 'cats', grow: 1}]}, right: {size: W40, groups: [{tabs: ['detail'], on: 'detail', grow: 1}]}, bottom: {size: 300, groups: []}, floats: []}}, start: 'Standard'});
  PNL.define('browse', 'cats', {title: 'Categories', home: 'left', init: it => it.el.appendChild($('#side'))});
  PNL.define('browse', 'detail', {title: 'Record', init: it => it.el.appendChild($('#detail'))});
  // a record pinned in its own panel: what it looked like when pinned (↻ looks again)
  PNL.define('browse', 'rec', {title: 'Record', icon: '📌', hidden: true, multi: true, home: 'float', w: 400, h: 520,
    titleFor: it => it.state.name || 'Record', render: ppRenderPin});
  ppNotes('browse');
  PNL.start('browse');
  const later = () => S.summary ? ppRestore('browse') : setTimeout(later, 500);    // (once the records are loaded)
  later();
  ppButtons('browse', 'detail', 'Record');
}

function ppPin(){
  const d = S.cur; if (!d) return;
  const it = PNL.open('browse', 'rec', {i: S.sel, name: d.name || d.id});
  ppFillPin(it, $('#detail').innerHTML);
}
function ppFillPin(it, html){
  it.el.innerHTML = `<div class="pp-pinbar"><button class="btn sm" data-pp="open" title="Show it in the Record panel">Open</button><button class="btn sm" data-pp="again" title="Look again (after a change)">↻</button></div><div class="detail" style="padding:12px 16px 40px">${html}</div>`;
  const body = it.el.querySelector('.detail');
  body.querySelectorAll('.navbtns,.actions,.inline,canvas,[data-pin]').forEach(x => x.remove());
  it.el.onclick = e => {
    const a = e.target.closest('[data-pp]');
    if (a){ if (a.dataset.pp === 'open') openRecord(it.state.i, true); else ppRenderPin(it, true); return; }
    const g = e.target.closest('[data-go]'); if (g){ openRecord(+g.dataset.go, true); return; }
    const c = e.target.closest('[data-copy]'); if (c) navigator.clipboard?.writeText(c.dataset.copy);
  };
}
// (drawing a record means using the Record panel for a moment: it is put back as it was right after)
async function ppRenderPin(it, again){
  if (it.el.querySelector('.detail') && !again) return;
  it.el.innerHTML = '<div class="msg" style="padding:14px"><span class="spin"></span></div>';
  try {
    const d = await api('/api/record?i=' + it.state.i);
    const keep = {cur: S.cur, editing: S.editing, copyOpen: S.copyOpen, html: $('#detail').innerHTML};
    S.editing = false; S.copyOpen = false;
    PP.rendering = true; ppRenderDetail(d); PP.rendering = false;
    const html = $('#detail').innerHTML;
    S.cur = keep.cur; S.editing = keep.editing; S.copyOpen = keep.copyOpen;
    if (S.sel != null && !keep.editing) openRecord(S.sel, false); else $('#detail').innerHTML = keep.html;
    it.state.name = d.name || d.id; PNL.retitle('browse', it.id);
    ppFillPin(it, html);
  } catch (e){ it.el.innerHTML = `<div class="msg err" style="padding:14px">${esc(e.message)}</div>`; }
}

// a 📌 button on every record, to pin it
const ppRenderDetail = renderDetail;
renderDetail = function(d){
  ppRenderDetail(d);
  if (PP.rendering) return;
  const top = $('#detail .navbtns');
  if (top && !top.querySelector('[data-pin]')){
    const b = document.createElement('button'); b.dataset.pin = '1'; b.textContent = '📌'; b.title = 'Pin it in its own panel (to compare with others)';
    b.onclick = e => { e.stopPropagation(); ppPin(); };
    top.appendChild(b);
  }
};

// the pages become panels the first time they're shown
const ppShowView = showView;
showView = function(v){ ppInit(v); return ppShowView(v); };
ppInit('browse');

if (typeof CF_ACT !== 'undefined') CF_ACT.push(
  {id: 'pinrec', label: 'Pin the record in its own panel', keys: [], run: () => { if (!$('#browse').classList.contains('on') || !S.cur) return false; ppPin(); }},
  {id: 'pagepanels', label: 'This page\'s panels and layouts', keys: [], run: () => {
    const v = [...document.querySelectorAll('.view.on')].map(x => x.id)[0]; if (!v || !PNL.spaces[v]) return false;
    PNL.windowsMenu(v, PNL.spaces[v].els.center.querySelector('.pp-btn') || $('#w-panels'));
  }},
);
