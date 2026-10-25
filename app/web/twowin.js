// A second window: the same Workshop in another view on the same server (the World map in one, an
// interior in 3D in the other), both live. It opens at a link (help.js openFromLink: cell, 3d, cam), and
// with win=2 in the link it calls itself "Morrowind Workshop: <place>", so the launcher's "show the
// Workshop" still finds the main window (packaging/appwindow.cs closes both when the Workshop quits; a
// second window also closes itself once the server is gone).
// Keeping in step: every edit says which window made it (X-Workshop-Window, see post()), the server counts
// the changes with the places they touched (editing.CHANGES), and each window asks /api/changes every
// second and reloads what another view changed: those places, Undo, and its selection.
const TW = {n: null, project: undefined, busy: false, fails: 0,
            second: new URLSearchParams(location.hash.replace(/^#/, '')).get('win') === '2',
            orig: new URLSearchParams(location.hash.replace(/^#/, '')).get('orig') === '1'};

// the link for a place: where the 3D view looks now (this place), or a door's arrival spot (to); orig: the
// place without your mod (a "before" window, to look at only)
function twLink(key, to, orig){
  const h = new URLSearchParams({cell: key, '3d': '1', win: '2'});
  if (orig) h.set('orig', '1');
  if (to) h.set('cam', [to.x, to.y, (to.z || 0) + 100, to.rz || 0, -0.1].map(v => Math.round(v * 1000) / 1000).join(','));
  else if (key === W.key && V3.on && V3.pos){
    const p = [V3.pos.x + V3.origin[0], V3.pos.y + V3.origin[1], V3.pos.z + V3.origin[2]];
    h.set('cam', [...p.map(v => Math.round(v)), Math.round(V3.yaw * 1000) / 1000, Math.round(V3.pitch * 1000) / 1000].join(','));
  } else if (key === W.key){
    h.set('zoom', W.cam.z); h.set('at', Math.round(W.cam.x) + ',' + Math.round(W.cam.y));
    h.set('3d', W.ext ? '0' : '1');
  }
  return location.origin + location.pathname + '#' + h.toString();
}
// (a window of its own, never a tab: with a size given, Edge's app window opens another app window)
function twOpen(key, to, orig){
  if (!key) return;
  const w = Math.max(900, Math.round(window.outerWidth * 0.8)), hgt = Math.max(640, Math.round(window.outerHeight * 0.85));
  const win = window.open(twLink(key, to, orig), '_blank', `popup=1,width=${w},height=${hgt},left=${window.screenX + 60},top=${window.screenY + 40}`);
  if (!win) toast('The second window was blocked. Allow pop-ups for the Workshop and try again.', true);
}
function twMenuItem(key, to, label){
  return {label: label || '↗ Open in a second window', act: () => twOpen(key, to)};
}
// (for every right-click menu on the map and in 3D: this place in a second view inside the Workshop, or in a
// window of its own, looking from where this one's camera is: the 3D view's eye, or the map's middle and zoom)
function twHereItems(){
  if (!W.key) return [];
  const out = [{label: '⧉ Open a second view here (inside the Workshop)', act: () => twPanelOpen(W.key)}];
  if (TW.embed) out.length = 0;                     // (a view inside the Workshop opens no view of its own)
  out.push(twMenuItem(W.key, null, '↗ Open a second window here (from this view)'));
  return out;
}

// ----- a second view inside the Workshop: the same page in a frame with only its World map / 3D view showing
// (embed=1), floating over the main view or docked beside it. Being the same page, it keeps in step and
// takes part in every cross-window tool exactly as a window of its own does.
TW.embed = new URLSearchParams(location.hash.replace(/^#/, '')).get('embed') === '1';
// (only once the page is up: hidden from the start, the page's start-up never finishes)
if (TW.embed){
  const t = setInterval(() => { if (typeof S !== 'undefined' && S.summary && S.summary.state === 'ready'){ clearInterval(t); document.body.classList.add('embed'); dispatchEvent(new Event('resize')); } }, 200);
}
function twPanelOpen(key, to, orig){
  if (!key) return;
  let p = $('#twpanel');
  if (!p){
    p = document.createElement('div'); p.id = 'twpanel';
    p.innerHTML = `<div class="twp-head"><span class="twp-title">Second view</span>
        <button class="btn sm" data-twp="dock" title="Dock it beside the main view, or float it over it"></button>
        <button class="btn sm" data-twp="window" title="This view in a window of its own (for a second screen)">↗ Window</button>
        <button class="btn sm" data-twp="close" title="Close the second view">✕</button></div>
      <iframe class="twp-frame" title="Second view"></iframe><div class="twp-grip" title="Drag to resize"></div><div class="twp-edge" title="Drag to make it wider or narrower"></div>`;
    document.querySelector('main').appendChild(p);
    p.querySelector('[data-twp="close"]').onclick = twPanelClose;
    p.querySelector('[data-twp="dock"]').onclick = () => twPanelMode(TW.panelMode === 'dock' ? 'float' : 'dock');
    p.querySelector('[data-twp="window"]').onclick = () => {
      const f = p.querySelector('iframe'); let h = '';
      try { h = f.contentWindow.location.hash; } catch (e) {}
      const q = new URLSearchParams(h.replace(/^#/, '')); q.delete('embed');
      twPanelClose();
      const w = Math.max(900, Math.round(window.outerWidth * 0.8)), hgt = Math.max(640, Math.round(window.outerHeight * 0.85));
      if (!window.open(location.origin + location.pathname + '#' + q.toString(), '_blank', `popup=1,width=${w},height=${hgt}`)) toast('The second window was blocked. Allow pop-ups for the Workshop and try again.', true);
    };
    if (typeof cfMovable === 'function') cfMovable(p, '.twp-title', 'twpanel');
    twPanelSizers(p);
  }
  // (the frame's own place, and where it looks: kept in its link as it moves about, for "↗ Window")
  p.querySelector('iframe').src = twLink(key, to, orig) + '&embed=1';
  p.querySelector('.twp-title').textContent = 'Second view' + (orig ? ' (without your mod)' : '');
  let mode = 'float'; try { mode = localStorage.getItem('ws-twpanel-mode') || 'float'; } catch (e) {}
  twPanelMode(mode);
}
function twPanelClose(){
  const p = $('#twpanel'); if (!p) return;
  const f = p.querySelector('iframe'); if (f) f.src = 'about:blank';
  p.remove(); document.querySelector('main').classList.remove('twdock');
  dispatchEvent(new Event('resize'));
}
function twPanelMode(mode){
  const p = $('#twpanel'); if (!p) return;
  TW.panelMode = mode; try { localStorage.setItem('ws-twpanel-mode', mode); } catch (e) {}
  p.classList.toggle('docked', mode === 'dock');
  document.querySelector('main').classList.toggle('twdock', mode === 'dock');
  let w = 0.42; try { w = +localStorage.getItem('ws-twpanel-w') || 0.42; } catch (e) {}
  document.querySelector('main').style.setProperty('--tww', Math.round(w * 100) + '%');
  p.querySelector('[data-twp="dock"]').textContent = mode === 'dock' ? '⧉ Float' : '◨ Dock beside';
  dispatchEvent(new Event('resize'));
}
// (the corner grip resizes it floating; the left edge sets its width docked. The frame takes no pointer
// while either is dragged, or it would swallow the drag)
function twPanelSizers(p){
  const drag = (el, move, done) => el.addEventListener('pointerdown', e => {
    if (e.button !== 0) return;
    e.preventDefault(); p.classList.add('moving');
    const mv = ev => move(ev), up = () => { p.classList.remove('moving'); removeEventListener('pointermove', mv); removeEventListener('pointerup', up); if (done) done(); dispatchEvent(new Event('resize')); };
    addEventListener('pointermove', mv); addEventListener('pointerup', up);
  });
  drag(p.querySelector('.twp-grip'), ev => {
    const r = p.getBoundingClientRect();
    p.style.width = Math.max(320, ev.clientX - r.left) + 'px'; p.style.height = Math.max(220, ev.clientY - r.top) + 'px';
  });
  const main = document.querySelector('main');
  drag(p.querySelector('.twp-edge'), ev => {
    const r = main.getBoundingClientRect(), f = Math.min(0.8, Math.max(0.2, (r.right - ev.clientX) / r.width));
    main.style.setProperty('--tww', Math.round(f * 100) + '%');
    try { localStorage.setItem('ws-twpanel-w', String(f)); } catch (e) {}
  });
}

function twTitle(){
  if (!TW.second) return;
  const t = 'Morrowind Workshop: ' + (W.info ? (W.info.name || W.info.region || W.key) : 'second window') + (TW.orig ? ' (without your mod)' : '');
  if (document.title !== t) document.title = t;
}

async function twPoll(){
  if (TW.busy || !S.summary || S.summary.state !== 'ready') return;
  TW.busy = true;
  try {
    const r = await api('/api/changes?since=' + (TW.n || 0));
    TW.fails = 0;
    if (TW.n == null || TW.project === undefined){ TW.n = r.n; TW.project = r.project; return; }
    // (mid-drag here: wait for the drop, then catch up)
    if ((V3.drag) || W.drag) return;
    const project = r.project !== TW.project, restarted = r.n < TW.n;
    const theirs = r.changes.filter(c => c.by !== WIN_ID);
    TW.n = r.n; TW.project = r.project;
    if (project || restarted || r.all || theirs.some(c => c.cells == null || c.records)){ await refreshAfterEdits(true); return; }
    if (!theirs.length) return;
    const touched = new Set(theirs.flatMap(c => c.cells));
    await afterChange();
    let any = false;
    for (const k of Object.keys(W.cells)) if (touched.has(k)){ await worldReloadCell(k); any = true; }
    if (any){
      if (W.sel && !findRef(W.sel.cell, W.sel.k)) W.sel = null;
      for (const [mk, m] of [...W.multi]) if (!findRef(m.cell, m.k)) W.multi.delete(mk);
      renderWside(); drawMap();
    }
  } catch (e){
    // (the server is gone: the Workshop was quit, so a second window goes with it)
    if (e instanceof TypeError && ++TW.fails >= 5 && TW.second) window.close();
  } finally { TW.busy = false; twTitle(); }
}
setInterval(twPoll, 1000);
addEventListener('hashchange', () => { if (new URLSearchParams(location.hash.replace(/^#/, '')).get('win') === '2') TW.second = true; });

// ----- working across the windows: the windows talk over a BroadcastChannel (the same server, the same
// browser), for what isn't an edit yet: a door picked to link, the clipboard, objects sent over to be placed.
// Each window says it's here every few seconds, so the menus offer these only while another view is open.
TW.peers = new Map();
TW.ch = typeof BroadcastChannel === 'function' ? new BroadcastChannel('ws-windows') : null;
function twSay(m){ if (TW.ch) try { TW.ch.postMessage(Object.assign({from: WIN_ID}, m)); } catch (e){ console.warn(e); } }
// (the other views open now: {at, key, place, orig}, the most recently heard from first)
function twPeerList(){ const now = Date.now(); return [...TW.peers.values()].filter(p => now - p.at < 10000).sort((a, b) => b.at - a.at); }
function twOthers(){ return twPeerList().length; }
function twPlaceName(){ return W.info ? (W.info.name || W.info.region || 'outside') : 'the other view'; }
function twHere(t){ twSay({t, key: W.key, place: W.key ? twPlaceName() : '', interior: !!(W.info && W.info.interior), orig: TW.orig}); }
twHere('hello');
setInterval(() => twHere('here'), 4000);
addEventListener('pagehide', () => twSay({t: 'bye'}));
if (TW.ch) TW.ch.onmessage = e => {
  const m = e.data; if (!m || m.from === WIN_ID) return;
  if (m.t === 'bye'){ TW.peers.delete(m.from); return; }
  const p = TW.peers.get(m.from) || {};
  p.at = Date.now();
  if (m.t === 'hello' || m.t === 'here') Object.assign(p, {key: m.key, place: m.place, interior: m.interior, orig: m.orig});
  TW.peers.set(m.from, p);
  if (m.t === 'hello') twHere('here');
  else if (m.t === 'clip'){ TW.quiet = true; W.clip = m.clip; TW.quiet = false; }
  else if (m.t === 'sel') twOtherSelected(m);
  else if (m.t === 'ask') twAsked(m);
  else if (m.t === 'answer' || m.t === 'ask-end') twAnswered(m);
  else if (m.t === 'doorpick') twDoorPicked(m);
  else if (m.t === 'doorpick-end') twDoorEnd(false);
  else if (m.t === 'send') twReceive(m);
  else if (m.t === 'send-taken' && W.groupPlace && W.groupPlace.tw && W.groupPlace.tw.id === m.id) setMode(null);
};

// one clipboard for all the windows: Copy in one, Paste (Ctrl+V) in another
(function(){
  let clip = W.clip;
  Object.defineProperty(W, 'clip', {configurable: true, enumerable: true, get: () => clip,
    set: v => { clip = v; if (v && !TW.quiet) twSay({t: 'clip', clip: v}); }});
})();

// the items for an object's right-click menu (comfort.js), while another view is open
function twObjectItems(ck, r){
  // (a "before" window takes nothing in; from one, a copy of the game's version can go back into your mod)
  if (!twPeerList().some(p => !p.orig)) return [];
  const out = [{label: '↗ Send a copy to the other view (place it there)', act: () => twSend(false)}];
  if (TW.orig) return out;
  out.push({label: '↗ Move it to the other view (place it there)', act: () => twSend(true)});
  if (r && r.type === 'DOOR'){
    out.unshift({label: '📍 Pick where you arrive, in the other view…', act: () => twDoorArrival(ck, r)});
    if (TW.pending) out.unshift({label: `🔗 Link with ${TW.pending.name} (${TW.pending.place})`, act: () => twLinkDoors(ck, r)});
    else out.unshift({label: '🔗 Link to a door in the other view (then click it there)', act: () => twPickDoor(ck, r)});
  }
  return out;
}
// the items for a place's right-click menu (comfort.js): another view on it, and, with one open, what
// it can do for this one
function twPlaceItems(){
  // (the plain "Open a second window here" is in every right-click menu: twHereItem)
  const out = [];
  if (W.info && !TW.orig) out.push({label: '↗ Open the game\'s version (without your mod) in a second window', act: () => twOpen(W.key, null, true)});
  if (!twOthers()) return out;
  out.push({label: (TW.follow ? '✓ ' : '') + '🧭 Follow doors picked in the other view', act: () => { TW.follow = !TW.follow; toast(TW.follow ? 'Pick a door in the other view and this one goes where it leads.' : 'Not following the other view any more.'); }});
  out.push({label: (TW.syncSel ? '✓ ' : '') + '⇆ Select what the other view selects (same place)', act: () => { TW.syncSel = !TW.syncSel; }});
  const o = twPeerList().find(p => p.key && p.key !== W.key && !p.orig);
  if (o && W.info && W.info.interior && o.interior){
    out.push({label: `💡 Copy the lighting and fog of ${o.place}`, act: () => twCopyLighting(o)});
    out.push({label: `🪑 Furnish like ${o.place}…`, act: () => twFurnishLike(o)});
  }
  return out;
}

// ----- doors: pick one here, click one in the other view, and they lead to each other (doors.link_pair)
function twBar(html, cancel){
  setBanner(html ? `<span>${html}</span> <button class="btn sm" id="tw-cancel">Cancel</button>` : '');
  const b = $('#tw-cancel');
  if (b) b.onclick = e => { e.stopPropagation(); if (cancel) cancel(); else { twSay({t: 'doorpick-end'}); twDoorEnd(true); } };
}
function twPickDoor(ck, r){
  TW.picked = {cell: ck, k: r.k, name: r.name || r.id, place: twPlaceName()};
  twSay(Object.assign({t: 'doorpick'}, TW.picked));
  twBar(`🔗 Now click a door in the other view: it and <b>${esc(TW.picked.name)}</b> will lead to each other. Esc cancels.`);
}
function twDoorPicked(m){
  TW.pending = {cell: m.cell, k: m.k, name: m.name, place: m.place};
  twBar(`🔗 Click a door here to link it with <b>${esc(m.name)}</b> in ${esc(m.place)}: each will lead to the other. Esc cancels.`);
  toast(`Linking doors: click a door here to link it with ${m.name} in ${m.place}.`);
}
function twDoorEnd(said){
  const was = TW.pending || TW.picked;
  TW.pending = null; TW.picked = null;
  if ($('#tw-cancel')) twBar('');
  if (was && said) toast('Door linking cancelled.');
}
async function twLinkDoors(ck, r){
  const P = TW.pending; if (!P || !await needProject()) return;
  if (P.cell === ck && P.k === r.k) return toast('Pick a different door.', true);
  TW.pending = null;
  try {
    const res = await post('/api/doors/pair', {cell_a: P.cell, ref_a: P.k, cell_b: ck, ref_b: r.k});
    for (const k of res.cells || []) if (W.cells[k]) await worldReloadCell(k);
    await afterChange();
    toast(`${r.name || r.id} and ${P.name} (${P.place}) now lead to each other. Undo takes it back.`);
  } catch (e){ toast(e.message, true); }
  twSay({t: 'doorpick-end'}); twDoorEnd(false);
}
// (a click on a door here while one is picked in the other view: link them)
const _twSelectRef = selectRef;
selectRef = function(ck, k, quiet){
  _twSelectRef(ck, k, quiet);
  if (quiet) return;
  const r = findRef(ck, k);
  if (!r) return;
  // (asked for an object by another view: this is it)
  if (TW.answer && TW.answer.kind === 'object'){ twAnswer({id: r.id, name: r.name || r.id, type: r.type, cell: ck, ref: r.k, p: r.p, place: twPlaceName()}); return; }
  // (for the other views: follow this door, select it there too when they show the same place)
  twSay({t: 'sel', cell: ck, k: r.k, to: r.to || null, name: r.name || r.id, place: twPlaceName()});
  if (TW.pending && r.type === 'DOOR') setTimeout(() => twLinkDoors(ck, r), 0);
};
addEventListener('keydown', e => { if (e.key === 'Escape' && (TW.pending || TW.picked)){ twSay({t: 'doorpick-end'}); twDoorEnd(true); } });

// ----- objects across: the selection, copied, is placed in the other view (point and click there);
// a move takes the originals away once it's down, the two folded into one Undo step
async function twSend(move){
  const sel = selectionRefs(); if (!sel.length) return;
  if (move && !await needProject()) return;
  try {
    const c = await post('/api/group/copy', {refs: selRefsBody()});
    const label = sel.length > 1 ? `${sel.length} objects` : (sel[0][1].name || sel[0][1].id);
    twSay({t: 'send', id: Math.random().toString(36).slice(2, 10), items: c.items, label, move: move ? selRefsBody() : null, place: twPlaceName()});
    toast(`${move ? 'Moving' : 'Sending a copy of'} ${label}: point where it goes in the other view and click.`);
  } catch (e){ toast(e.message, true); }
}
function twReceive(m){
  if (TW.orig) return;
  if (!W.key) return toast(`${m.label} was sent here: open a place first.`, true);
  startGroupPlace(m.items, m.label);
  W.groupPlace.tw = {id: m.id, move: m.move, place: m.place};
  toast(`${m.move ? 'Moving' : 'A copy of'} ${m.label} from ${m.place}: point where it goes and click. Esc to stop.`);
}
const _twPlaceGroupAt = placeGroupAt;
placeGroupAt = async function(x, y, z){
  const G = W.groupPlace, tw = G && G.tw;
  if (!tw) return _twPlaceGroupAt(x, y, z);
  // (put down or not: the server's change count, as Undo's depth stops growing at 100)
  const count = async () => { try { return (await api('/api/changes?since=999999999')).n; } catch (e){ return 0; } };
  const before = await count();
  await _twPlaceGroupAt(x, y, z);
  if (await count() <= before) return;
  twSay({t: 'send-taken', id: tw.id});
  if (!tw.move){ G.tw = null; return; }
  setMode(null);
  try {
    await post('/api/group/delete', {refs: tw.move});
    await post('/api/fold', {n: 2, note: `Moved ${G.label} from ${tw.place} to ${twPlaceName()}`});
    await afterChange();
    toast(`Moved ${G.label} here from ${tw.place}. One Undo takes it back.`);
  } catch (e){ toast(e.message, true); }
};

// ----- drag out: an object (or a selection) dragged past the window's edge and let go goes to the other
// window, which places it where you click (a move: one Undo step, as above)
function twOutside(e){ return e.clientX < 0 || e.clientY < 0 || e.clientX >= innerWidth || e.clientY >= innerHeight; }
addEventListener('mouseup', e => {
  if (TW.orig || !twOutside(e) || !twPeerList().some(p => !p.orig)) return;
  const D = W.drag;
  if (!(D && (D.kind === 'obj' || D.kind === 'group') && D.moved)) return;
  // (the map's own mouseup never sees it: the things stay put here)
  e.stopImmediatePropagation();
  W.drag = null; drawMap();
  twSend(true);
}, true);
// (in 3D the handles let go on pointerup, before mouseup: marked here, sent from v3DragEnd)
addEventListener('pointerup', e => { if (!TW.orig && V3.drag && twOutside(e) && twPeerList().some(p => !p.orig)) TW.dragOut = true; }, true);
const _twDragEnd = v3DragEnd;
v3DragEnd = async function(){
  if (!TW.dragOut) return _twDragEnd();
  TW.dragOut = false;
  V3.drag = null; v3Refresh();                      // (back where they were)
  twSend(true);
};

// ----- pick in the other view: a spot (script coordinates, a travel destination, where a door arrives) or
// an object (an ID) is clicked in another view and comes back to the one that asked
TW.syncSel = true; TW.asks = {};
function twAsk(kind, what){
  if (!twOthers()){ toast('Open a second window first (right-click a place: ↗ Open in a second window).', true); return Promise.resolve(null); }
  const id = Math.random().toString(36).slice(2, 10);
  return new Promise(res => {
    TW.asks[id] = res;
    twSay({t: 'ask', id, kind, what});
    toast(`Click ${kind === 'spot' ? 'the spot' : 'the object'} in the other view: ${what}.`);
  });
}
function twAsked(m){
  if (!W.key) return;
  if (TW.answer) twAskEnd(true);
  TW.answer = {id: m.id, kind: m.kind, what: m.what};
  if (m.kind === 'spot'){ W.arriving = {name: m.what}; setMode('arrive'); }
  twBar(`📍 The other view asks: click ${m.kind === 'spot' ? 'the spot' : 'the object'} for <b>${esc(m.what)}</b>. Esc cancels.`, () => twAskEnd(true));
}
function twAnswer(a){
  const A = TW.answer; if (!A) return;
  TW.answer = null; W.arriving = null;
  if (W.mode === 'arrive') setMode(null);
  twBar('');
  twSay(Object.assign({}, a, {t: 'answer', ask: A.id}));     // (ask, not id: an object's answer has an id of its own)
  toast('Sent to the other view.');
}
function twAskEnd(cancelled){
  const A = TW.answer; if (!A) return;
  TW.answer = null; W.arriving = null;
  if (W.mode === 'arrive') setMode(null);
  if ($('#tw-cancel')) twBar('');
  if (cancelled) twSay({t: 'ask-end', id: A.id});
}
function twAnswered(m){
  const ask = m.t === 'answer' ? m.ask : m.id, res = TW.asks[ask];
  if (res){
    delete TW.asks[ask];
    if (m.t === 'answer') twSay({t: 'ask-end', id: ask});        // (any other view still waiting stops)
    else toast('The pick was cancelled in the other view.');
    res(m.t === 'answer' ? m : null);
    return;
  }
  if (TW.answer && TW.answer.id === ask) twAskEnd(false);
}
// (a spot clicked while asked: arrive mode's click, on the map or in 3D)
const _twArriveAt = arriveAt;
arriveAt = function(x, y, z, rz){
  if (!(TW.answer && TW.answer.kind === 'spot')) return _twArriveAt(x, y, z, rz);
  // (on the map there's no height: the door's arrival is worked out by the server, the rest takes the nearest thing's)
  const zg = z != null ? z : groundZ(x, y);
  twAnswer({x, y, z, zg, rz: rz || 0, key: cellKeyAt(x, y), cell: W.info && W.info.interior ? W.info.name : '', place: twPlaceName()});
};
addEventListener('keydown', e => { if (e.key === 'Escape' && TW.answer) twAskEnd(true); });
setInterval(() => { if (TW.answer && TW.answer.kind === 'spot' && W.mode !== 'arrive') twAskEnd(true); }, 1000);

async function twDoorArrival(ck, r){
  const a = await twAsk('spot', `where the player arrives through ${r.name || r.id}`);
  if (!a || !await needProject()) return;
  await relinkDoor(ck, r.k, a.key, [a.x, a.y, a.z, a.rz], a.place);
  if (W.cells[ck]) await worldReloadCell(ck);
}

// the script editor: a command with a spot, or an object's ID, from the other view
if (typeof sRender === 'function'){
  const _twSRender = sRender;
  sRender = function(){
    _twSRender.apply(this, arguments);
    const bar = document.querySelector('#smain .chbtns'); if (!bar) return;
    const b = document.createElement('button');
    b.className = 'btn sm'; b.textContent = '📍 From the other view ▾';
    b.title = 'Click a spot or an object in another Workshop window, and it goes into the script where the cursor is';
    b.onclick = e => pnlMenu({x: e.clientX, y: e.clientY}, [
      {label: 'PositionCell / Position: put someone at a spot (click it)', act: () => twScriptSpot(false)},
      {label: 'AITravel: walk to a spot (click it)', act: () => twScriptSpot(true)},
      {label: 'An object\'s ID (click it)', act: () => twScriptId()}]);
    bar.prepend(b);
  };
}
async function twScriptSpot(travel){
  const a = await twAsk('spot', travel ? 'AITravel in the script' : 'PositionCell in the script');
  if (!a || !$('#s-ta')) return;
  const xyz = [a.x, a.y, a.zg].map(v => Math.round(v)).join(' '), deg = Math.round((a.rz || 0) * 180 / Math.PI);
  // (a line of its own, wherever the cursor is in the line)
  const ta = $('#s-ta'), s = ta.selectionStart, text = ta.value;
  const before = text.slice(text.lastIndexOf('\n', s - 1) + 1, s), after = text.slice(s, (text.indexOf('\n', s) + 1 || text.length + 1) - 1);
  const cmd = travel ? `AITravel ${xyz}` : a.cell ? `PositionCell ${xyz} ${deg} "${a.cell}"` : `Position ${xyz} ${deg}`;
  sInsert((before.trim() ? '\n' : '') + cmd + (after.trim() ? '\n' : ''));
}
async function twScriptId(){
  const a = await twAsk('object', 'an ID in the script');
  if (!a || !$('#s-ta')) return;
  sInsert(/[\s']/.test(a.id) ? `"${a.id}"` : a.id);
}

// characters: where a package walks to, who it follows, what it uses, where they take the player
if (typeof cAI === 'function'){
  const _twCAI = cAI;
  cAI = function(box){
    _twCAI(box);
    const d = C.data;
    box.querySelectorAll('.cai').forEach((el, n) => {
      const a = d.ai[n], head = el.querySelector('.caihead span'); if (!a || !head) return;
      const add = (label, title, fn) => { const b = document.createElement('button'); b.className = 'btn sm'; b.textContent = label; b.title = title; b.onclick = fn; head.prepend(b); };
      const done = () => { cRender(); cChanged(); };
      if (a.kind === 'activate') add('📍 Pick it', 'Click the object in the other view', async () => { const r = await twAsk('object', 'what they go and use'); if (r){ a.target = r.id; done(); } });
      if (a.kind === 'follow' || a.kind === 'escort') add('👤 Pick who', 'Click the character in the other view', async () => { const r = await twAsk('object', a.kind === 'follow' ? 'who they follow' : 'who they escort'); if (r){ a.target = r.id; done(); } });
      if (a.kind === 'travel' || a.kind === 'follow' || a.kind === 'escort') add('📍 Pick the spot', 'Click where they go, in the other view', async () => {
        const s = await twAsk('spot', 'where they go'); if (!s) return;
        a.p = [s.x, s.y, s.zg]; if (a.kind !== 'travel') a.cell = s.cell; done();
      });
    });
  };
}
if (typeof cServices === 'function'){
  const _twCServices = cServices;
  cServices = function(box){
    _twCServices(box);
    const dd = $('#c-dest'); if (!dd) return;
    const b = document.createElement('button');
    b.className = 'btn sm'; b.style.marginTop = '6px'; b.textContent = '📍 Add a destination: click it in the other view';
    b.onclick = async () => {
      const s = await twAsk('spot', 'where they take the player'); if (!s) return;
      C.data.travel.push({p: [s.x, s.y, s.zg, 0, 0, s.rz || 0], cell: s.cell}); cRender(); cChanged();
    };
    dd.closest('.dd').after(b);
  };
}

// ----- follow and select along: a door picked in another view takes this one where it leads; a thing
// selected in another view showing the same place is selected here too
async function twOtherSelected(m){
  if (TW.answer || W.mode) return;
  if (TW.follow && m.to){ await twGoTo(m.to.key, m.to); return; }
  if (!TW.syncSel || !W.cells[m.cell] || !findRef(m.cell, m.k) || (W.sel && W.sel.cell === m.cell && W.sel.k === m.k)) return;
  _twSelectRef(m.cell, m.k, true); W.multi.clear(); drawMap();
}
async function twGoTo(key, to){
  if (W.key !== key) await worldOpen(key);
  if (V3.on){
    if (typeof qolWaitFor3D === 'function') await qolWaitFor3D(key);
    V3.pos.set(to.x - V3.origin[0], to.y - V3.origin[1], (to.z || 0) + 100 - V3.origin[2]); V3.yaw = to.rz || 0; V3.pitch = -0.1; v3Refresh();
  } else { W.cam.x = to.x; W.cam.y = to.y; if (W.cam.z < 0.3) W.cam.z = 0.6; drawMap(); }
}

// ----- the other view's place: its lighting and fog here, or furnish like it
async function twCopyLighting(o){
  if (!await needProject()) return;
  try {
    const s = (await api('/api/place/settings?key=' + encodeURIComponent(o.key))).settings;
    if (!s.has_lighting) return toast(`${o.place} has no lighting of its own.`, true);
    const mine = (await api('/api/place/settings?key=' + encodeURIComponent(W.key))).settings;
    const m = await post('/api/place/settings', {key: W.key, settings: Object.assign({}, mine, {ambient: s.ambient, sun: s.sun, fog: s.fog, density: s.density})});
    W.cells[W.key] = prepCell(m); W.info = m; W.placeEdit = null; V3.lightPreview = null;
    renderWside(); if (V3.on) v3ApplyLighting(); v3Refresh(); await afterChange();
    toast(`Copied the lighting and fog of ${o.place}. Undo takes it back.`);
  } catch (e){ toast(e.message, true); }
}
async function twFurnishLike(o){
  await furnishDialog(W.key);
  const sel = $('#fu-like'); if (!sel) return;
  if (![...sel.options].some(x => x.value === o.key)){
    const op = document.createElement('option'); op.value = o.key; op.textContent = o.place + ' · in the other view'; sel.appendChild(op);
  }
  sel.value = o.key;
}

// ----- a "before" window (orig=1 in its link): the place as the game has it, without your mod, to look at
// only. Its places are read without the mod, and nothing it would change reaches the server.
if (TW.orig){
  const _twFetch = window.fetch.bind(window);
  window.fetch = (u, opt) => {
    if (typeof u === 'string'){
      if (u.startsWith('/api/cellmap?')) u += '&original=1';
      else if (opt && opt.method === 'POST' && u.startsWith('/api/') && !/^\/api\/(settings|group\/copy)$/.test(u))
        return Promise.resolve(new Response(JSON.stringify({error: 'This window shows the place without your mod, to look at only: make changes in the other view.'}),
                                            {status: 400, headers: {'Content-Type': 'application/json'}}));
    }
    return _twFetch(u, opt);
  };
  const badge = document.createElement('div');
  badge.textContent = 'Without your mod: the game\'s version, to look at only';
  badge.style.cssText = 'position:fixed;top:6px;left:50%;transform:translateX(-50%);z-index:60;pointer-events:none;padding:3px 12px;border-radius:12px;' +
    'background:var(--sel);color:var(--gold2);border:1px solid var(--goldline);font-size:12px';
  document.body.appendChild(badge);
}
