// The buttons over the World map (Map / 3D / Panels, and the 3D tools) in groups you can drag about by
// their grip. A group you've put somewhere stays there; near the right or bottom edge it keeps to that
// edge when the side panels change size. "Arrange automatically" puts them all back in a row.
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
  #world.tb-locked .tb-grip{display:none}`;
  document.head.appendChild(c);
}

function tbArea(){ return $('#world .mapwrap'); }
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
  const A = tbArea(); if (!A || !A.clientWidth) return;        // (another page is showing: done when it's back)
  for (const g of tbGroups()){
    const p = TB.pos[tbKey(g)];
    if (p) tbPlace(g, p); else tbFree(g);
    if (!g.dataset.tbBound){ g.dataset.tbBound = '1'; g.addEventListener('contextmenu', tbMenu); }
  }
}

function tbAuto(){ TB.pos = {}; tbSave(); tbApply(); toast('Buttons arranged in a row again.'); }

function tbMenu(e){
  if (e.target.closest('select, input')) return;
  e.preventDefault(); e.stopPropagation();
  const g = e.currentTarget, k = tbKey(g), items = [];
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
