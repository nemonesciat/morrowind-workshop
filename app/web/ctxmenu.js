// ---------- The right-click menu, sorted: search, a few quick actions, recent ones, then fixed groups ----------
// (the user: "bloated… hard to find… haphazardly arranged… the length is a problem".) Every entry the menu has
// stays; each goes into one group by what it does, always in the same order and with the same name, and a
// group opens its list beside the menu when the mouse is over it. A group of one entry shows that entry
// itself. Typing (the box has the keys as soon as the menu opens) lists every matching entry with its group's
// name, so nothing nested is ever out of reach; Enter runs the first. The quick actions are the two or three
// that thing is right-clicked for most (a door: go where it leads), the recent ones the last you used.
// The groups, in the order the menu shows them: the thing itself first (what only it has: a door's ways, a
// person's words, a piece of furniture's dressing), then what is done to any object (see it, edit it, move
// it, replace it, change its looks, make it a secret way), then the building, then outward (the room, the
// place, the view). Each group lists its entries in the order of its patterns, so the order is by meaning,
// not by which part of the Workshop added them: turn, tilt, scale, set down, settle; copy, paste, duplicate,
// undo, delete.
const CM_GROUPS = [
  ['This door', '🚪', [/^go where it leads/i, /^pick where you arrive…$/i, /^pick where you arrive, in the other view/i, /^make it lead somewhere/i,
    /lead elsewhere in this place/i, /^link (with|to a door)/i, /^open where it leads in a second view/i, /^open where it leads in a second window/i]],
  ['This person', '🧍', [/^dialogue/i, /^edit (character|creature)/i, /^test setup/i]],
  ['Dress it', '🪄', [/^dress (this|again)/i, /^fill with books/i, /^add one thing/i]],
  ['Look and open', '👁', [/^look at/i, /^open its window/i, /^open its record/i, /^edit it in /i, /^pin it/i, /^where it.s used/i]],
  ['Edit', '✎', [/^copy$/i, /^paste/i, /^duplicate/i, /^save as a prefab/i, /record of its own/i, /^undo my changes/i, /^bring back/i, /^delete/i]],
  ['Move and place', '⟳', [/^turn 90°$/i, /^turn 90° the other way/i, /^tilt/i, /^scale/i, /^set it down/i, /^settle (it|them|everything on it)\b/i,
    /^send a copy to the other view/i, /^move it to the other view/i]],
  ['Replace and select', '⇄', [/^swap for/i, /^replace every/i, /^replace them/i, /^select all the/i, /^select it with everything/i,
    /^select everything you can see/i, /^clear the selection/i]],
  ['Looks and sound', '🎨', [/^animations and text keys/i, /^model (&|and) textures/i, /^retexture/i, /^add a sound/i, /^forge a new piece/i, /^into the world/i]],
  ['Secret entrance', '🔐', [/^make (it|this) a hidden door/i, /^make this a door to/i, /^rotating panel/i, /^sliding panel/i, /^make it an activator/i,
    /^make this an ordinary object/i]],
  ['Build', '🧱', [/^fix here/i, /^fix this edge/i, /^add a room through/i, /^extend (from here|by piece)|^leave extend mode/i, /^other pieces that fit/i,
    /^build an interior inside/i, /^fit the ground/i, /^plan a prefab/i, /^make this (place|dungeon) again/i]],
  ['This room', '🪑', [/^furnish the .* again|^furnish the [^.]*\(the game/i, /^furnish the .* as…/i, /^furnish like/i, /^dress everything in/i, /^remove the .*(its pieces|wall closes)/i]],
  ['This place', '🏠', [/^create here/i, /^populate this place/i, /^someone who.d live here/i, /^settle what.s loose/i, /^play here/i, /^find gaps/i,
    /^check this place/i, /^redraw the walking paths/i, /^copy the lighting/i, /^back to/i]],
  ['View', '▤', [/^hide (it|them)/i, /^hide everything else/i, /^show the .* hidden/i, /^put the grid here/i, /^open a second view here/i,
    /^open a second window here/i, /^open the game.s version/i, /^panels and layouts/i, /^all commands/i]],
];
const CM_MORE = ['More', '…'];
// (which group an entry belongs to is tried in this order, the narrow ones first: "Dress everything in the
// room" is the room's, not "Dress it"; "Copy the lighting" the place's, not Edit's Copy)
const CM_TRY = ['This room', 'This place', 'This door', 'This person', 'Dress it', 'Secret entrance', 'Build', 'Looks and sound',
  'Look and open', 'Move and place', 'Replace and select', 'Edit', 'View'];
// what a kind of thing is right-clicked for most, first match wins
const CM_QUICK = {
  DOOR: [/go where it leads/i, /open its window/i, /^look at/i],
  NPC_: [/^dialogue/i, /edit character/i, /open its window/i],
  CREA: [/^dialogue/i, /edit creature/i, /open its window/i],
  furniture: [/dress (this|again)/i, /fill with books/i, /add one thing/i, /settle everything/i],
  item: [/^settle it/i, /^copy$/i, /open its window/i],
  piece: [/^fix here/i, /^add a room through/i, /^other pieces that fit/i],
  group: [/^copy$/i, /settle them/i, /^turn 90°$/i],
  spot: [/^paste/i, /^create here/i, /^settle what/i],
  thing: [/^look at/i, /open its window/i, /^copy$/i],
};
const CM_KEY = 'ws-menu-recent';

function cmBare(label){ return String(label || '').replace(/^[^\w(]+/u, '').trim(); }
// the same entry from one time to the next: "Furnish the Room 2 again (33 things now)" is one entry whatever the count
function cmNorm(label){ return cmBare(label).replace(/\([^)]*\)/g, '').replace(/\d+/g, '#').replace(/\s+/g, ' ').trim().toLowerCase(); }
// [group name, the entry's place in that group's order]
function cmPlace(it){
  const b = cmBare(it.label);
  for (const name of CM_TRY){
    const g = CM_GROUPS.find(x => x[0] === name);
    const i = g[2].findIndex(re => re.test(b));
    if (i >= 0) return [name, i];
  }
  return [CM_MORE[0], 99];
}
function cmGroupOf(it){ return cmPlace(it)[0]; }
function cmRecentGet(){ try { return JSON.parse(localStorage.getItem(CM_KEY) || '[]'); } catch (e) { return []; } }
function cmRecentAdd(label){
  const k = cmNorm(label); if (!k) return;
  const r = [k, ...cmRecentGet().filter(x => x !== k)].slice(0, 8);
  try { localStorage.setItem(CM_KEY, JSON.stringify(r)); } catch (e) {}
}

// items: the flat list (as pnlMenu takes it: {label, act, head, disabled, on} or '-'); ctx: {kind} for the quick actions
let CM_OPEN = null;           // {pt, close, state(): {q, grp}} of the menu showing
function cmMenu(pt, items, ctx){
  // (drawn again at the same spot, when a late answer adds an entry: what was typed and the group open stay)
  const keep = CM_OPEN && CM_OPEN.pt.x === pt.x && CM_OPEN.pt.y === pt.y ? CM_OPEN.state() : null;
  if (CM_OPEN) CM_OPEN.close();
  document.querySelectorAll('.pmenu').forEach(m => m.remove());
  const real = items.filter(it => it && it !== '-' && !it.head && it.label);
  const heads = items.filter(it => it && it.head);
  const title = heads.length ? heads[0].label : '';
  // groups, in their fixed order, each keeping its entries' own order
  const by = new Map();
  real.forEach((it, n) => { const [g, i] = cmPlace(it); it._cmo = i * 1000 + n; if (!by.has(g)) by.set(g, []); by.get(g).push(it); });
  for (const list of by.values()) list.sort((a, b) => a._cmo - b._cmo);
  const order = [...CM_GROUPS.map(g => [g[0], g[1]]), CM_MORE].filter(([n]) => by.has(n));
  // quick: the two or three this kind of thing is right-clicked for most
  const quick = [];
  for (const re of CM_QUICK[(ctx && ctx.kind) || 'thing'] || CM_QUICK.thing){
    const it = real.find(x => !quick.includes(x) && !x.disabled && re.test(cmBare(x.label)));
    if (it) quick.push(it);
  }
  const recent = [];
  for (const k of cmRecentGet()){
    const it = real.find(x => cmNorm(x.label) === k && !quick.includes(x) && !recent.includes(x) && !x.disabled);
    if (it && recent.length < 3) recent.push(it);
  }
  const m = document.createElement('div'); m.className = 'pmenu cmenu';
  const all = [];                                  // (every entry drawn, by index, for the clicks)
  const btn = (it, extra) => { all.push(it); return `<button data-cm="${all.length - 1}" class="${it.on ? 'on' : ''}" ${it.disabled ? 'disabled style="opacity:.45"' : ''} title="${esc(it.title || '')}">${esc(it.label)}${extra || ''}</button>`; };
  const main = () => {
    let h = '';
    if (quick.length) h += quick.map(it => btn(it)).join('');
    if (recent.length) h += '<hr><div class="cmlab">Recent</div>' + recent.map(it => btn(it)).join('');
    if (quick.length || recent.length) h += '<hr>';
    for (const [name, icon] of order){
      const list = by.get(name);
      // (named for what it holds: on an empty spot there's nothing to replace, only to select)
      const shown = name === 'Replace and select' && !list.some(it => /^(swap|replace)/i.test(cmBare(it.label))) ? 'Select' : name;
      if (list.length === 1) h += btn(list[0]);
      else h += `<button class="cmgrp" data-grp="${esc(name)}" data-label="${esc(shown)}"><span class="cmico">${icon}</span>${esc(shown)}<span class="cmarr">›</span></button>`;
    }
    return h;
  };
  m.innerHTML = (title ? `<div class="phd">${esc(title)}</div>` : '') +
    `<input class="inp cmq" placeholder="Find an action (go, tilt, furnish…)" autocomplete="off" spellcheck="false"><div class="cmbody">${main()}</div>`;
  document.body.appendChild(m);
  const body = m.querySelector('.cmbody'), q = m.querySelector('.cmq');
  let sub = null;
  const closeSub = () => { if (sub){ sub.remove(); sub = null; } m.querySelectorAll('.cmgrp.cmon').forEach(b => b.classList.remove('cmon')); };
  const close = () => { closeSub(); m.remove(); document.removeEventListener('pointerdown', off, true); document.removeEventListener('keydown', keys, true); if (CM_OPEN && CM_OPEN.m === m) CM_OPEN = null; };
  const run = it => { if (!it || it.disabled) return; cmRecentAdd(it.label); close(); if (it.act) it.act(); };
  const openSub = b => {
    closeSub();
    const list = by.get(b.dataset.grp) || [];
    b.classList.add('cmon');
    sub = document.createElement('div'); sub.className = 'pmenu cmsub';
    sub.innerHTML = `<div class="phd">${esc(b.dataset.label || b.dataset.grp)}</div>` + list.map(it => btn(it)).join('');
    document.body.appendChild(sub);
    const r = b.getBoundingClientRect(), mr = m.getBoundingClientRect();
    const left = mr.right + sub.offsetWidth + 4 <= innerWidth ? mr.right + 2 : Math.max(8, mr.left - sub.offsetWidth - 2);
    const top = Math.max(8, Math.min(innerHeight - sub.offsetHeight - 8, r.top - 26));
    Object.assign(sub.style, {left: left + 'px', top: top + 'px'});
    sub.onclick = e => { const x = e.target.closest('[data-cm]'); if (x) run(all[+x.dataset.cm]); };
  };
  const bind = () => {
    body.querySelectorAll('.cmgrp').forEach(b => {
      b.onmouseenter = () => openSub(b);
      b.onclick = e => { e.stopPropagation(); openSub(b); };
    });
    body.querySelectorAll('[data-cm]').forEach(b => b.onmouseenter = () => closeSub());
  };
  m.onclick = e => { const x = e.target.closest('[data-cm]'); if (x) run(all[+x.dataset.cm]); };
  // search: every entry that matches, with its group's name
  q.oninput = () => {
    closeSub();
    const s = q.value.trim().toLowerCase();
    if (!s){ all.length = 0; body.innerHTML = main(); bind(); place(); return; }
    all.length = 0;
    const hits = real.filter(it => (cmBare(it.label) + ' ' + cmGroupOf(it)).toLowerCase().includes(s));
    body.innerHTML = hits.map(it => btn(it, `<span class="cmtag">${esc(cmGroupOf(it))}</span>`)).join('') || '<div class="cmlab">No action by that name</div>';
    place();
  };
  const keys = e => {
    if (e.key === 'Escape'){ e.preventDefault(); e.stopPropagation(); if (q.value){ q.value = ''; q.oninput(); } else close(); return; }
    if (e.key === 'Enter' && document.activeElement === q){ e.preventDefault(); const b = body.querySelector('[data-cm]:not([disabled])'); if (b) run(all[+b.dataset.cm]); }
  };
  const off = e => { if (!m.contains(e.target) && !(sub && sub.contains(e.target))) close(); };
  setTimeout(() => document.addEventListener('pointerdown', off, true), 0);
  document.addEventListener('keydown', keys, true);
  const place = () => {
    const left = Math.min(innerWidth - m.offsetWidth - 8, pt.x), top = pt.y + m.offsetHeight + 4 > innerHeight ? Math.max(8, innerHeight - m.offsetHeight - 8) : pt.y + 4;
    Object.assign(m.style, {left: Math.max(8, left) + 'px', top: top + 'px'});
  };
  bind(); place();
  CM_OPEN = {m, pt, close, state: () => ({q: q.value, grp: (m.querySelector('.cmgrp.cmon') || {}).dataset ? m.querySelector('.cmgrp.cmon').dataset.grp : null})};
  if (keep && keep.q){ q.value = keep.q; q.oninput(); }
  else if (keep && keep.grp){ const b = [...body.querySelectorAll('.cmgrp')].find(x => x.dataset.grp === keep.grp); if (b) openSub(b); }
  setTimeout(() => { try { q.focus({preventScroll: true}); } catch (e) {} }, 0);
  return m;
}

(function cmCss(){
  const s = document.createElement('style');
  s.textContent = `.cmenu{width:300px;max-height:none}
  .cmenu .cmq{display:block;width:calc(100% - 8px);margin:2px 4px 6px;height:28px;font-size:13px}
  .cmenu .cmgrp{display:flex;align-items:center;gap:8px}
  .cmenu .cmgrp.cmon{background:#ffffff18}
  .cmenu .cmico{width:18px;text-align:center;opacity:.85}
  .cmenu .cmarr{margin-left:auto;opacity:.6}
  .cmenu .cmlab{font-size:11px;color:var(--faint);padding:2px 10px}
  .cmenu .cmtag{float:right;font-size:11px;color:var(--faint);margin-left:10px}
  .cmsub{min-width:240px;max-width:380px;max-height:calc(100vh - 16px);overflow:auto}`;
  document.head.appendChild(s);
})();
