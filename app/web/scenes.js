// ---------- Scenes: the mod's cutscenes, listed on the Scripts page and made beside the 3D view ----------
// A scene (openmw-scene/1, kept by bridge.py, played in the game by scenes.py) is made here with the scene maker,
// or sent by a connected program or a coding agent. The maker docks along the bottom of the World map, under the
// 3D view: a timeline you drag, people and the player on marks you see and drag in 3D, shots from the 3D view or
// aimed at someone, lines timed by their voices; ▶ Preview runs the shots in the 3D view; ▶ Try it starts the game
// there and plays it. Right-click the ground, a person or a door for a new scene; in Dialogue a line's "Then do"
// can play one, and a quest stage's 🎬 starts one.
const SCN = {list: null, open: null, kinds: {}, ed: null, try: null, prev: null};
(function(){
  const st = document.createElement('style');
  st.textContent = `#scn-dock{position:absolute;left:0;right:0;bottom:0;height:44%;z-index:40;background:var(--panel);border-top:2px solid var(--gold,#b8954a);
      display:flex;flex-direction:column;box-shadow:0 -6px 18px #0007}
    #scn-dock .scn-dockbar{display:flex;align-items:center;gap:8px;padding:3px 8px;border-bottom:1px solid var(--line)}
    #scn-dock .scn-grip{cursor:ns-resize;padding:0 10px;font-size:18px;line-height:12px;color:var(--muted)}
    #scn-dockbody{flex:1;overflow:auto;padding:0 10px 10px} #scn-dockbody .wrap{padding:6px 0}
    #scn-sub{position:absolute;inset:0;pointer-events:none;z-index:39}
    #scn-sub .scn-bar{position:absolute;left:0;right:0;height:11%;background:#000} #scn-sub .scn-bar.top{top:0} #scn-sub .scn-bar.bot{bottom:44%}
    #scn-sub .scn-subt{position:absolute;left:10%;right:10%;bottom:calc(44% + 14%);text-align:center;font-size:18px;color:#fff;text-shadow:0 0 4px #000,0 0 8px #000}`;
  document.head.appendChild(st);
})();
const SCN_FRAMES = {
  close: {label: 'Close-up', offset: [35, 80, 0], fov: 35},
  medium: {label: 'Medium', offset: [60, 170, -25], fov: 45},
  wide: {label: 'Wide', offset: [160, 520, 60], fov: 55},
  shoulder: {label: 'Over the player\'s shoulder', from: true, fov: 45},
};

// ----- the list (Scripts page side) and the overview
async function scnMine(){
  const box = $('#s-scenes'); if (!box) return;
  if (!S.summary || !S.summary.project){ box.innerHTML = ''; return; }
  try { SCN.list = await api('/api/scenes'); } catch (e){ box.innerHTML = `<div class="msg">${esc(e.message)}</div>`; return; }
  SCN.kinds = SCN.list.triggers || {};
  const l = SCN.list.scenes || [];
  box.innerHTML = (l.length ? l.map(s => `<div class="drow ${SCN.open === s.scene ? 'on' : ''}" data-scnopen="${esc(s.scene)}"><span>🎬 ${esc(s.name)}</span>
      <small>${esc(scnWhenShort(s.trigger))}</small></div>`).join('') : '')
    + '<button class="btn sm" id="scn-newside" style="margin-top:6px">+ New scene</button>';
  box.querySelectorAll('[data-scnopen]').forEach(r => r.onclick = () => scnEdit(r.dataset.scnopen));
  $('#scn-newside').onclick = () => scnNew();
}
async function scnList(){ try { SCN.list = await api('/api/scenes'); } catch (e){} return (SCN.list && SCN.list.scenes) || []; }

// from the Scripts and Dialogue menus, the Scripts start page and the side list's heading
async function scnShow(){
  if (typeof pageOn === 'function' && !pageOn('scripts')) showView('scripts');
  await scnMine();
  scnOverview();
}

function scnLeave(){
  if (SCN.ed && SCN.ed.dirty && !confirm('Leave this scene without saving it?')) return false;
  scnPreviewStop();
  if (SCN.ed && SCN.ed.dock) scnUndock();
  SCN.ed = null;
  scnMarks3D();
  return true;
}

function scnOverview(){
  if (!scnLeave()) return;
  const l = (SCN.list && SCN.list.scenes) || [];
  SCN.open = null; SC.id = null; if (typeof LU !== 'undefined'){ LU.name = null; LU.data = null; }
  $('#smain').innerHTML = `<div class="wrap" style="max-width:820px"><h1>🎬 Scenes${typeof guideLink === 'function' ? guideLink('making-cutscenes.md', 'Your first cutscene') : ''}</h1>
    <p class="msg" title="Shots, people and their animations, spoken lines, music, fades and videos, played in the game when something starts them. Also made by connected programs and coding agents.">Cutscenes in your mod.</p>
    <div class="actions" style="margin:0 0 12px"><button class="btn primary" id="scn-new">+ New scene</button>
      <span class="msg">or right-click the ground or a person on the World map: 🎬 New scene here…</span></div>
    ${l.length ? `<div class="cgrid">${l.map(s => `<div class="ccard" data-scnov="${esc(s.scene)}"><div style="font-size:22px">🎬</div><b>${esc(s.name)}</b>
        <div class="msg">${s.length || 0} s · ${s.actors} ${s.actors === 1 ? 'person' : 'people'} · ${esc(scnWhen(s.trigger))}</div></div>`).join('')}</div>`
      : `<div class="card msg" style="line-height:1.7">No scenes yet. <b>+ New scene</b> makes one in the place on the World map; the guide
         <a href="#" id="scn-guide">Your first cutscene</a> walks through one.</div>`}</div>`;
  $('#smain').querySelectorAll('[data-scnov]').forEach(c => c.onclick = () => scnEdit(c.dataset.scnov));
  $('#scn-new').onclick = () => scnNew();
  const g = $('#scn-guide'); if (g) g.onclick = e => { e.preventDefault(); if (typeof docModal === 'function') docModal('making-cutscenes.md'); };
  scnMine();
}

function scnWhen(t){
  if (!t) return 'when another script asks';
  if (t.from === 'dialogue') return 'after a line of dialogue';
  return {area: 'when the player comes near a spot', quest: 'when a quest reaches a stage', global: 'when a global variable is set'}[t.kind] || '';
}
function scnWhenShort(t){
  if (!t) return 'when asked';
  if (t.from === 'dialogue') return 'dialogue';
  return {area: 'near a spot', quest: 'quest stage', global: 'global'}[t.kind] || '';
}

// ----- starting a scene: the + New scene button, or the right-click menu
function scnHere(){
  // (the place on the map: outdoors its grid cell, indoors its name)
  if (typeof W === 'undefined' || !W.key) return null;
  const m = /^#(-?\d+),(-?\d+)$/.exec(W.key);
  if (m) return {cell: [+m[1], +m[2]], key: W.key, label: (W.info && (W.info.name || W.info.region)) || W.key};
  return {cell: (W.info && W.info.id) || W.key, key: W.key, label: (W.info && W.info.id) || W.key};
}
function scnKeyOf(cell){ return Array.isArray(cell) ? `#${cell[0]},${cell[1]}` : String(cell || '').toLowerCase(); }
function scnCellAt(x, y){
  // (outdoors the grid cell a spot is in; indoors the place itself)
  const h = scnHere(); if (!h) return null;
  return Array.isArray(h.cell) ? [Math.floor(x / 8192), Math.floor(y / 8192)] : h.cell;
}

function scnBlank(cell){
  const taken = new Set(((SCN.list && SCN.list.scenes) || []).map(s => s.scene));
  let n = 1; while (taken.has('scene_' + n)) n++;
  return {format: 'openmw-scene/1', scene: 'scene_' + n, name: 'New scene', cell, length: 12,
    player: {controls: 'off', sheathe: true}, marks: {}, actors: [], shots: [], lines: [], sound: [],
    screen: [{at: 0, fade: 'in', dur: 1}, {at: 0, letterbox: '2.39'}],
    end: {do: [{controls: 'on'}], onSkip: 'end', onMissingActor: 'end'}};
}

async function scnNew(){
  if (!await needProject()) return;
  const h = scnHere();
  if (!h){ toast('Open the place the scene happens in on the World map first.', true); return; }
  if (!scnLeave()) return;
  await scnList();
  await scnStart(scnBlank(h.cell), true, {dock: true});
}

function scnStartMenu(pt, o){
  const go = start => () => scnNewWith(o, start);
  if (o.only) return go(o.only)();
  const items = [{label: 'It starts when…', disabled: true, head: true},
    {label: '🚶 The player arrives here', act: go('arrive')},
    {label: '💬 After a line of dialogue', act: go('dialogue')},
    {label: '📜 A quest reaches a stage', act: go('quest')},
    {label: '⚙ Only when a script asks', act: go('script')}];
  const m = pnlMenu(pt, items);
  m.querySelectorAll('button').forEach((b, n) => { if (items[n] && items[n].head) b.className = 'phd'; });
  m.querySelectorAll('button').forEach((b, n) => { if (items[n] && items[n].act) b.onclick = () => { m.remove(); items[n].act(); }; });
}

async function scnNewWith(o, start){
  if (!await needProject()) return;
  const h = scnHere(); if (!h) return;
  if (!scnLeave()) return;
  await scnList();
  const sc = scnBlank(h.cell);
  const spot = o.spot ? [Math.round(o.spot[0]), Math.round(o.spot[1]), Math.round(o.spot[2] || 0)] : null;
  if (start === 'arrive' && spot){
    sc.trigger = {kind: 'area', center: spot, radius: o.door ? 220 : 300, once: true};
    if (!Array.isArray(sc.cell)) sc.trigger.cell = sc.cell;
    sc.name = o.door ? 'Through the door' : 'Arriving here';
  } else if (start === 'dialogue') sc.trigger = {kind: 'dialogue', once: true};
  else if (start === 'quest') sc.trigger = {kind: 'quest', quest: '', stage: 10, once: true};
  await scnStart(sc, true, {dock: true, person: o.person, spot});
  if (start === 'dialogue') toast('Save the scene, then in Dialogue pick the line: Then do › Play a scene.');
  if (start === 'quest') toast('Give the quest and its stage under Starts when.');
}

async function scnEdit(id, opts){
  if (!scnLeave()) return;
  let sc;
  try { sc = await api('/api/scenes/get?scene=' + encodeURIComponent(id)); } catch (e){ return toast(e.message, true); }
  await scnStart(sc, false, opts || {});
}

async function scnStart(sc, isNew, opts){
  opts = opts || {};
  SCN.open = sc.scene; if (typeof SC !== 'undefined') SC.id = null; if (typeof LU !== 'undefined'){ LU.name = null; LU.data = null; }
  for (const k of ['actors', 'shots', 'lines', 'sound', 'screen', 'vfx', 'world']) if (!Array.isArray(sc[k])) sc[k] = [];
  sc.player = sc.player || {}; sc.marks = sc.marks || {};
  sc.end = sc.end || {do: [{controls: 'on'}]}; if (!Array.isArray(sc.end.do)) sc.end.do = [];
  SCN.ed = {sc, isNew, dirty: isNew, people: [], objects: [], anims: {}, cursor: 0, problems: null, dock: false};
  const cq = encodeURIComponent(Array.isArray(sc.cell) ? JSON.stringify(sc.cell) : sc.cell);
  try { SCN.ed.people = (await api('/api/scenes/actors?cell=' + cq)).actors || []; }
  catch (e){ SCN.ed.people = []; }
  try { SCN.ed.objects = (await api('/api/scenes/objects?cell=' + cq)).objects || []; } catch (e){}
  if (!SCN.fx) try { SCN.fx = await api('/api/scenes/effects'); } catch (e){ SCN.fx = {effects: [], weathers: []}; }
  if (opts.person){
    const p = SCN.ed.people.find(x => x.k === opts.person);
    if (p){
      const key = scnNewKey(p.id);
      sc.actors.push({key, ref: p.ref, clips: []});
      sc.shots.push({at: 0, aim: {actor: key, at: 'head'}, offset: SCN_FRAMES.close.offset.slice(), fov: SCN_FRAMES.close.fov});
      if (sc.name === 'New scene') sc.name = 'Scene with ' + p.name;
    }
  }
  await Promise.all(sc.actors.map(a => scnAnims(scnActorId(a))));
  // (someone the scene makes: their name from the game's records)
  SCN.names = SCN.names || {};
  await Promise.all(sc.actors.filter(a => a.spawn && a.id && !a.name && !SCN.names[a.id.toLowerCase()]).map(async a => {
    try { const r = await api('/api/search?' + new URLSearchParams({q: a.id, types: 'NPC_,CREA', limit: 10}));
      const row = r.rows.find(x => x.id.toLowerCase() === a.id.toLowerCase()); if (row) SCN.names[a.id.toLowerCase()] = row.name || row.id; } catch (e){}
  }));
  const wantDock = opts.dock || (typeof pageOn === 'function' && pageOn('world') && !pageOn('scripts'));
  if (wantDock) await scnDock(); else { if (typeof pageOn === 'function' && !pageOn('scripts')) showView('scripts'); scnRender(); }
  scnMine();
}

function scnNewKey(id){
  const sc = SCN.ed.sc;
  let key = id.toLowerCase().replace(/[^a-z0-9_]/g, '_'), n = 2;
  while (sc.actors.some(a => a.key === key) || key === 'player') key = id.toLowerCase().replace(/[^a-z0-9_]/g, '_') + '_' + n++;
  return key;
}
function scnActorId(a){
  if (a.id) return a.id;
  const p = scnPerson(a);
  return p ? p.id : '';
}
function scnPerson(a){
  return SCN.ed.people.find(x => a.ref && x.ref.file.toLowerCase() === String(a.ref.file).toLowerCase() && x.ref.index === a.ref.index)
    || (a.id ? SCN.ed.people.find(x => x.id.toLowerCase() === a.id.toLowerCase()) : null);
}
function scnName(a){ return a === 'player' ? 'The player' : (a.name || (scnPerson(a) || {}).name || (a.id && SCN.names && SCN.names[a.id.toLowerCase()]) || a.key); }
async function scnAnims(id){
  if (!id || SCN.ed.anims[id.toLowerCase()]) return;
  try { SCN.ed.anims[id.toLowerCase()] = (await api('/api/scenes/anims?id=' + encodeURIComponent(id))).groups || []; }
  catch (e){ SCN.ed.anims[id.toLowerCase()] = []; }
}

// ----- docked along the bottom of the World map, under the 3D view
function scnHostEl(){ return SCN.ed && SCN.ed.dock ? $('#scn-dockbody') : $('#smain'); }

async function scnDock(){
  const E = SCN.ed, sc = E.sc;
  if (typeof pageOn === 'function' && !pageOn('world')) showView('world');
  if (scnKeyOf(sc.cell) !== W.key && typeof worldOpen === 'function') await worldOpen(scnKeyOf(sc.cell));
  if (typeof V3 !== 'undefined' && !V3.on && typeof v3Enable === 'function') await v3Enable(true);
  // (the Scripts window over the map steps aside: the dock takes its place)
  if (typeof vwClose === 'function') try { vwClose('scripts'); } catch (e){}
  const wrap = document.querySelector('#world .mapwrap'); if (!wrap) return;
  let d = $('#scn-dock');
  if (!d){
    d = document.createElement('div'); d.id = 'scn-dock';
    d.innerHTML = `<div class="scn-dockbar"><span class="scn-grip" title="Drag to make it taller or shorter">⋯</span><b>🎬 Scene maker</b><span style="flex:1"></span>
      <button class="btn sm" id="scn-topage" title="Open it as a page on Scripts instead">⇱ As a page</button><button class="btn sm" id="scn-close" title="Close the scene maker">✕</button></div>
      <div id="scn-dockbody"></div>`;
    wrap.appendChild(d);
    const grip = d.querySelector('.scn-grip');
    grip.onpointerdown = ev => {
      ev.preventDefault(); const r0 = wrap.getBoundingClientRect();
      const mv = e2 => { const h = Math.max(140, Math.min(r0.height - 80, r0.bottom - e2.clientY)); d.style.height = h + 'px'; try { localStorage.setItem('ws-scnh', String(h)); } catch (e){} };
      const up = () => { window.removeEventListener('pointermove', mv); window.removeEventListener('pointerup', up); if (typeof v3Resize === 'function') v3Resize(); };
      window.addEventListener('pointermove', mv); window.addEventListener('pointerup', up);
    };
    try { const h = +localStorage.getItem('ws-scnh'); if (h) d.style.height = h + 'px'; } catch (e){}
  }
  d.querySelector('#scn-topage').onclick = () => { scnPreviewStop(); scnUndock(); E.dock = false; showView('scripts'); if (typeof renderScripts === 'function') renderScripts().then(() => scnRender()); else scnRender(); };
  d.querySelector('#scn-close').onclick = () => { if (scnLeave()) { scnMine(); } };
  d.style.display = '';
  E.dock = true;
  scnRender();
  scnDragInit();
}
function scnUndock(){ const d = $('#scn-dock'); if (d) d.style.display = 'none'; const s = $('#scn-sub'); if (s) s.remove(); }

// ----- the maker
function scnChanged(redraw){
  SCN.ed.dirty = true; SCN.ed.problems = null;
  const t = $('#scn-title'); if (t) t.textContent = '🎬 ' + (SCN.ed.sc.name || SCN.ed.sc.scene) + ' *';
  if (redraw) scnRender(); else scnTimeline();
  scnMarks3D();
}

const scnNum = (v, d) => (v === '' || v == null || isNaN(+v)) ? d : +v;
const scnSort = l => l.sort((a, b) => (+a.at || 0) - (+b.at || 0));
// (when a new shot goes: at the time picked, or after the last shot when one is already there)
function scnShotTime(){
  const E = SCN.ed, sc = E.sc, t = E.cursor || 0;
  if (!sc.shots.some(s => Math.abs((s.at || 0) - t) < 0.05)) return t;
  const last = Math.max(...sc.shots.map(s => s.at || 0));
  return Math.min(Math.max(0, (sc.length || 10) - 1), Math.round((last + 3) * 10) / 10);
}
const scnLineLen = l => l.dur || Math.max(1.5, 1 + String(l.text || '').split(/\s+/).filter(Boolean).length * 0.33);

function scnWho(sel){
  const sc = SCN.ed.sc;
  return `<option value="player" ${sel === 'player' ? 'selected' : ''}>The player</option>` +
    sc.actors.map(a => `<option value="${esc(a.key)}" ${sel === a.key ? 'selected' : ''}>${esc(scnName(a))}</option>`).join('');
}

// the game's animation groups in words, the raw name kept beside (patterns, so creatures' own read right too)
function scnAnimLabel(name){
  const n = String(name), l = n.toLowerCase(), num = (l.match(/(\d+)$/) || [])[1];
  const T = [
    [/^idle$/, 'Standing'], [/^idle\d+$/, 'Fidgets ' + num], [/^idlesneak/, 'Crouched, still'], [/^idlespell/, 'Hands ready for a spell'],
    [/^idlehh/, 'Fists up'], [/^idle1h/, 'Weapon in one hand, still'], [/^idle2c|^idle2w/, 'Weapon in both hands, still'], [/^idlecrossbow/, 'Crossbow ready'],
    [/^idlestorm/, 'Braced against the storm'], [/^idleswim/, 'Treading water'],
    [/^walkforward/, 'Walks forward'], [/^walkback/, 'Walks back'], [/^walkleft/, 'Walks left'], [/^walkright/, 'Walks right'],
    [/^runforward/, 'Runs forward'], [/^runback/, 'Runs back'], [/^runleft/, 'Runs left'], [/^runright/, 'Runs right'],
    [/^sneakforward/, 'Sneaks forward'], [/^turnleft/, 'Turns left'], [/^turnright/, 'Turns right'],
    [/^swim/, 'Swims'], [/^jump/, 'Jumps'], [/^spellcast/, 'Casts a spell'], [/^spellturn/, 'Turns, casting'],
    [/^handtohand/, 'Fights with fists'], [/^weapononehand/, 'Fights, one-handed'], [/^weapontwohand/, 'Fights, two-handed'],
    [/^weapontwowide/, 'Fights with a spear or staff'], [/^bowandarrow/, 'Shoots a bow'], [/^crossbow/, 'Shoots a crossbow'], [/^throwweapon/, 'Throws'],
    [/^pickprobe/, 'Picks a lock'], [/^shield/, 'Raises a shield'], [/^torch/, 'Holds up a torch'], [/^attack\d*/, 'Attacks ' + (num || '')],
    [/^hit\d*/, 'Flinches ' + (num || '')], [/^swimhit/, 'Flinches in the water'], [/^knockdown/, 'Knocked down'], [/^knockout/, 'Knocked out'],
    [/^deathknockdown/, 'Dies, knocked down'], [/^deathknockout/, 'Dies, knocked out'], [/^swimdeath/, 'Dies in the water'], [/^death\d*/, 'Dies ' + (num || '')],
    [/^getup/, 'Gets up'], [/^equip|^unequip/, 'Draws or sheathes'],
  ];
  const t = T.find(([re]) => re.test(l));
  return t ? `${t[1].trim()} · ${n}` : n;
}
function scnAnimSorted(groups){
  const rank = g => { const l = g.group.toLowerCase();
    return /^inventory|1st|^swim/.test(l) ? 9 : /^idle/.test(l) ? 0 : /^(walk|run|turn|sneak)/.test(l) ? 1 : /^(spell|torch|pick|shield)/.test(l) ? 2
      : /^(hit|knock|getup)/.test(l) ? 4 : /^death/.test(l) ? 5 : 3; };
  return groups.filter(g => !/^inventory/i.test(g.group)).slice().sort((a, b) => rank(a) - rank(b) || a.group.localeCompare(b.group, undefined, {numeric: true}));
}

function scnRender(){
  const host = scnHostEl(); if (!host || !SCN.ed) return;
  const E = SCN.ed, sc = E.sc;
  const cellTxt = Array.isArray(sc.cell) ? `outdoors, cell ${sc.cell[0]}, ${sc.cell[1]}` : sc.cell;
  const present = new Set(sc.actors.map(a => a.ref ? a.ref.file.toLowerCase() + '|' + a.ref.index : ''));
  const addable = E.people.filter(p => !present.has(p.ref.file.toLowerCase() + '|' + p.ref.index));
  const tr = sc.trigger || {}, c = tr.center || [];
  const kind = tr.from === 'dialogue' ? 'dialogue' : (tr.kind || '');
  const endQ = sc.end.do.find(d => d.quest) || {}, endG = sc.end.do.find(d => d.global) || {};
  const fadeOut = sc.screen.find(x => x.fade === 'out');
  const music = (sc.sound.find(x => x.music) || {}).music || '';
  const pm = sc.player.mark && sc.marks[sc.player.mark];
  host.innerHTML = `<div class="wrap scnmk ${E.dock ? 'docked' : ''}" style="max-width:${E.dock ? 'none' : '1040px'}">
    <style>.scnmk .scn-row{display:flex;gap:6px;align-items:center;flex-wrap:wrap;padding:4px 0;border-bottom:1px solid var(--line)}
      .scnmk .scn-row .inp{padding:3px 6px} .scnmk .scn-row select.inp{width:auto} .scnmk .scn-at{width:58px} .scnmk h3{margin:12px 0 4px}
      .scnmk.docked .scn-cols{column-count:2;column-gap:22px} .scnmk .scn-sec{break-inside:avoid;display:inline-block;width:100%}
      .scnmk .scn-tl{position:relative;border:1px solid var(--line);border-radius:6px;background:var(--panel2,var(--panel));padding:4px 0 6px;cursor:crosshair;user-select:none}
      .scnmk .scn-tlrow{position:relative;height:20px;margin:2px 14px 2px 100px}
      .scnmk .scn-tllab{position:absolute;left:-96px;top:2px;width:92px;font-size:11px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .scnmk .scn-blk{position:absolute;top:1px;height:17px;border-radius:4px;background:var(--gold-dim,#5a4a2a);border:1px solid var(--gold,#b8954a);font-size:11px;padding:0 4px;overflow:hidden;white-space:nowrap;cursor:grab;box-sizing:border-box}
      .scnmk .scn-blk.fixed{cursor:pointer;opacity:.75}
      .scnmk .scn-cur{position:absolute;top:0;bottom:0;width:2px;background:var(--accent,#6cf);pointer-events:none}
      .scnmk .scn-end{position:absolute;top:0;bottom:0;width:8px;margin-left:-4px;cursor:ew-resize;background:linear-gradient(90deg,transparent 3px,var(--gold,#b8954a) 3px,var(--gold,#b8954a) 5px,transparent 5px)}
      .scnmk .scn-flash{outline:2px solid var(--gold,#b8954a)}</style>
    <div class="scn-row" style="border:0;gap:8px">
      <h2 id="scn-title" style="margin:0 8px 0 0">🎬 ${esc(sc.name || sc.scene)}${E.dirty ? ' *' : ''}</h2>
      <button class="btn primary" id="scn-save" title="Keep it in your mod (Undo takes it back); File › Save writes it">Save</button>
      <button class="btn" id="scn-prev" title="Run the shots in the 3D view, with the lines as subtitles (people don't move here)">${SCN.prev ? '■ Stop' : '▶ Preview'}</button>
      <button class="btn" id="scn-try" title="Start the game here and play the scene (it is saved into your mod first)">▶ Try it in the game</button>
      <button class="btn" id="scn-check" title="Find what would stop it playing">Check</button>
      ${E.dock ? '' : '<button class="btn" id="scn-todock" title="Make it next to the 3D view, on the World map">⧉ Next to the 3D view</button>'}
      ${E.isNew ? '' : '<button class="btn" id="scn-del" title="Remove it from your mod (Undo brings it back)">Remove</button>'}
      <button class="btn" id="scn-back">All scenes</button><span class="msg" id="scn-msg"></span></div>
    ${SCN.list && SCN.list.lua_ok === false ? '<p class="msg sev-warning">Scenes play only in an .omwaddon mod (File › Save as…).</p>' : ''}
    <div id="scn-probs"></div>
    <div class="scn-row" style="border:0"><label>Name</label><input class="inp" id="scn-name" value="${esc(sc.name || '')}" style="max-width:240px">
      <label title="Its ID: letters, numbers and _">ID</label><input class="inp" id="scn-id" value="${esc(sc.scene)}" style="max-width:150px" ${E.isNew ? '' : 'disabled'}>
      <label>Length</label><input class="inp num" id="scn-len" value="${sc.length || 10}" style="width:54px"> s
      <span class="msg" title="Where it happens">${esc(cellTxt)}</span></div>

    <div class="scn-tl" id="scn-tl"></div>
    <p class="msg" style="margin:2px 0 0">Drag a block to move it in time, the end mark to change the length; click to pick a time (new things start there).</p>

    <div class="scn-cols">
    <div class="scn-sec"><h3>People</h3>
    <div class="scn-row"><b style="min-width:130px">The player</b>
      <label><input type="checkbox" id="scn-ctl" ${sc.player.controls === 'on' ? '' : 'checked'}> can't move or look</label>
      <label><input type="checkbox" id="scn-sheathe" ${sc.player.sheathe ? 'checked' : ''}> weapon away</label>
      <span class="msg" title="Right-click a spot on the map or in 3D: The player stands here">${pm ? '📍 on a spot' : 'where they are'}</span>
      ${pm ? '<button class="btn sm" data-scnunmark="player" title="Let them stay where they are">✕ spot</button>' : ''}</div>
    ${sc.actors.map((a, i) => { const p = scnPerson(a) || {}, m = a.mark && sc.marks[a.mark]; return `<div class="scn-row"><b style="min-width:130px">${esc(scnName(a))}</b>
      <span class="msg" title="Right-click a spot: ${esc(p.name || a.key)} stands here. Drag the marker in 3D to move it">${m ? '📍 on a spot' : 'where they stand'}</span>
      ${m ? `<button class="btn sm" data-scnunmark="${esc(a.key)}">✕ spot</button>` : ''}<span style="flex:1"></span>
      <button class="btn sm" data-scnrm="actors:${i}" title="Take them out of the scene (their animations and lines go too)">✕</button></div>
      ${scnActorMore(a, i)}`; }).join('')}
    <div class="scn-row" style="border:0">${addable.length ? `<select class="inp" id="scn-addwho" style="max-width:250px">${addable.map((p, i) =>
      `<option value="${i}">${esc(p.name)} (${esc(p.id)})</option>`).join('')}</select><button class="btn sm" id="scn-addactor">+ Add</button>`
      : '<span class="msg">Nobody else stands in this place.</span>'}</div>
    <div class="scn-row" style="border:0"><input class="inp" id="scn-newwho" list="dl-scnnew" placeholder="Someone new: a person or creature" style="max-width:250px"
      title="Brought into the scene at a spot, when you say: summoned, walking in, or just there"><datalist id="dl-scnnew"></datalist>
      <button class="btn sm" id="scn-newadd">+ Bring in</button></div></div>

    <div class="scn-sec"><h3>Shots</h3>
    ${scnSort(sc.shots).map((s, i) => scnShotRow(s, i)).join('')}
    <div class="scn-row" style="border:0"><button class="btn sm" id="scn-addview" title="The 3D view's camera as it is now: frame the shot in the 3D view first">+ Shot from the 3D view</button>
      <button class="btn sm" id="scn-addaim" ${sc.actors.length ? '' : 'disabled title="Add someone under People first"'}>+ Shot on someone</button></div></div>

    <div class="scn-sec"><h3>Animations</h3>
    ${scnSort(sc.actors.flatMap((a, ai) => (a.clips || []).map((c, ci) => ({a, ai, c, ci, at: c.at})))).map(x => scnClipRow(x)).join('')}
    <div class="scn-row" style="border:0"><button class="btn sm" id="scn-addclip" ${sc.actors.length ? '' : 'disabled'}>+ Animation</button></div></div>

    <div class="scn-sec"><h3>Lines</h3>
    ${scnSort(sc.lines).map((l, i) => `<div class="scn-row" data-scnrow="lines:${i}"><input class="inp num scn-at" data-scnf="lines:${i}:at" value="${l.at || 0}" title="Seconds from the start"> s
      <select class="inp" data-scnf="lines:${i}:who" style="max-width:150px">${scnWho(l.who || l.actor)}</select>
      <input class="inp" data-scnf="lines:${i}:text" value="${esc(l.text || '')}" placeholder="What they say" style="flex:1;min-width:180px">
      <button class="btn sm" data-scnvoice="${i}" title="${l.voice ? esc(l.voice) : 'Pick a voice file (their lips move as it plays)'}">🔊 ${l.voice ? esc(l.voice.split(/[\\/]/).pop()) + (l.dur ? ' · ' + l.dur + ' s' : '') : 'Voice…'}</button>
      ${l.voice ? `<button class="btn sm" data-scnnovoice="${i}" title="No voice: the words show as a message">✕🔊</button>` : ''}
      <button class="btn sm" data-scnrm="lines:${i}">✕</button></div>`).join('')}
    <div class="scn-row" style="border:0"><button class="btn sm" id="scn-addline">+ Line</button>
      ${sc.lines.length > 1 ? '<button class="btn sm" id="scn-spacelines" title="Each line starts just after the one before ends (its voice\'s length, or the time to read it)">⇣ One after another</button>' : ''}</div></div>

    <div class="scn-sec"><h3>Effects</h3>
    ${sc.vfx.map((v, i) => scnFxRow(v, i)).join('')}
    <div class="scn-row" style="border:0"><button class="btn sm" id="scn-addfx" title="Fire, magic, smoke: on someone or at a spot">+ Effect</button></div></div>

    <div class="scn-sec"><h3>In the world</h3>
    ${sc.world.map((w, i) => scnWorldRow(w, i)).join('')}
    <div class="scn-row" style="border:0"><button class="btn sm" id="scn-addobj" ${E.objects.length ? '' : 'disabled title="No doors, lights or such in this place"'} title="Open or close a door, use a lever, put out a light, show or hide a thing">+ Door, light or thing</button>
      <button class="btn sm" id="scn-addweather">+ Weather</button><button class="btn sm" id="scn-addhour" title="The game's clock moves on to an hour">+ Time of day</button></div></div>

    <div class="scn-sec"><h3>Screen and sound</h3>
    <div class="scn-row"><label><input type="checkbox" id="scn-fadein" ${sc.screen.some(x => x.fade === 'in') ? 'checked' : ''}> Fade in</label>
      <label><input type="checkbox" id="scn-fadeout" ${fadeOut ? 'checked' : ''}> Fade out at the end</label>
      <label><input type="checkbox" id="scn-lbox" ${sc.screen.some(x => x.letterbox != null) ? 'checked' : ''}> Black bars</label></div>
    <div class="scn-row"><label>Music</label><input class="inp" id="scn-music" value="${esc(music)}" placeholder="Music/… (optional)" style="max-width:300px"></div>
    ${sc.sound.map((x, i) => x.sound != null ? scnSoundRow(x, i) : '').join('')}
    <div class="scn-row" style="border:0"><button class="btn sm" id="scn-addsnd" title="A sound at a time: the game's sounds by name, or a file; heard from someone or something">+ Sound</button></div>
    ${sc.screen.map((x, i) => x.movie != null ? `<div class="scn-row" data-scnrow="screen:${i}"><input class="inp num scn-at" data-scnf="screen:${i}:at" value="${x.at || 0}"> s
      <label>Video</label><input class="inp" data-scnf="screen:${i}:movie" value="${esc(x.movie)}" placeholder="file.bik in the game's Video folder" style="max-width:260px">
      <span class="msg">the game waits while it plays</span><button class="btn sm" data-scnrm="screen:${i}">✕</button></div>` : '').join('')}
    <div class="scn-row" style="border:0"><button class="btn sm" id="scn-addvid">+ Video</button></div>
    <div class="scn-row" style="border:0"><b title="Post-processing: the player needs it on in OpenMW's settings (Options › Post Processing); without it the scene plays the same, without these">Look</b>
      <span class="msg">colour, focus and blur, blended in over a time</span></div>
    ${sc.screen.map((x, i) => scnLookRow(x, i)).join('')}
    <div class="scn-row" style="border:0"><button class="btn sm" id="scn-addcol" title="Darker or brighter, warmer or colder, less colour, dark edges">+ Colour</button>
      <button class="btn sm" id="scn-adddof" title="Sharp on someone or at a distance, soft before and beyond">+ Focus</button>
      <button class="btn sm" id="scn-addmb" title="Blur as the camera moves">+ Motion blur</button>
      <button class="btn sm" id="scn-addshake" title="The camera shakes: a blast, a summoning, a fall">+ Shake</button></div>
    ${sc.screen.map((x, i) => x.shake != null ? `<div class="scn-row" data-scnrow="screen:${i}"><input class="inp num scn-at" data-scnf="screen:${i}:at" value="${x.at || 0}"> s
      <b style="min-width:100px">〰 Shake</b><label>strength</label><input class="inp num" data-scnf="screen:${i}:shake" value="${x.shake}" style="width:46px" title="0 to 1">
      <label>for</label><input class="inp num" data-scnf="screen:${i}:dur" value="${x.dur || 1}" style="width:40px"> s
      <button class="btn sm" data-scnrm="screen:${i}">✕</button></div>` : '').join('')}</div>

    <div class="scn-sec"><h3>At the end</h3>
    <div class="scn-row"><span class="msg">The player gets the controls back.</span></div>
    <div class="scn-row"><label>Quest</label><input class="inp" id="scn-eq" value="${esc(endQ.quest || '')}" placeholder="quest ID (optional)" style="max-width:200px" list="dl-scnquests">
      <label>stage</label><input class="inp num" id="scn-es" value="${endQ.stage != null ? endQ.stage : ''}" style="width:54px"></div>
    <div class="scn-row"><label>Global set to 1</label><input class="inp" id="scn-eg" value="${esc(endG.global || '')}" placeholder="(optional)" style="max-width:200px"></div>
    <div class="scn-row"><label title="The conversation opens with them again: for a scene started from a line of dialogue">Talk with</label>
      <select class="inp" id="scn-etalk" style="max-width:200px"><option value="">nobody</option>${sc.actors.map(a => `<option value="${esc(a.key)}" ${(sc.end.do.find(d => d.talk) || {}).talk === a.key ? 'selected' : ''}>${esc(scnName(a))}</option>`).join('')}</select></div></div>

    <div class="scn-sec"><h3>Starts when</h3>
    <div class="scn-row"><select class="inp" id="scn-kind" style="max-width:300px">
      <option value="">Only when a script asks</option>
      <option value="area" ${kind === 'area' ? 'selected' : ''}>The player comes near a spot</option>
      <option value="dialogue" ${kind === 'dialogue' ? 'selected' : ''}>After a line of dialogue</option>
      <option value="quest" ${kind === 'quest' ? 'selected' : ''}>A quest reaches a stage</option>
      <option value="global" ${kind === 'global' ? 'selected' : ''} title="Set from MWScript: set name to 1">A global variable is set to 1</option></select>
      <label><input type="checkbox" id="scn-once" ${tr.once === false ? '' : 'checked'}> once a game</label></div>
    <div class="scn-row" id="scn-area" style="display:none"><span class="msg" title="The green ring in the 3D view: drag it, or right-click a spot › New scene here">📍 ${c.length ? Math.round(c[0]) + ', ' + Math.round(c[1]) : 'no spot yet'}</span>
      within <input class="inp num" id="scn-r" value="${tr.radius != null ? tr.radius : 300}" style="width:56px"> units
      <button class="btn sm" id="scn-spot" title="The spot in the middle of the 3D view">Here</button></div>
    <div class="scn-row" id="scn-dlg" style="display:none"><span class="msg">${tr.name ? `In Dialogue, a line's <b>Then do › Play a scene</b> starts it (it sets ${esc(tr.name)} to 1).`
      : 'Save, then in Dialogue pick the line: <b>Then do › Play a scene</b>.'}</span></div>
    <div class="scn-row" id="scn-quest" style="display:none"><input class="inp" id="scn-q" value="${esc(tr.quest || '')}" placeholder="quest ID" style="max-width:190px" list="dl-scnquests">
      stage <input class="inp num" id="scn-st" value="${tr.stage != null ? tr.stage : 10}" style="width:56px"></div>
    <div class="scn-row" id="scn-global" style="display:none"><input class="inp" id="scn-g" value="${esc(tr.name || '')}" placeholder="global variable" style="max-width:200px"></div>
    </div></div></div>`;
  scnBind();
  scnTimeline();
  scnProblems();
  scnMarks3D();
  scnQuestList();
}

async function scnQuestList(){
  if ($('#dl-scnquests')) return;
  try {
    const qids = (await api('/api/dlg/index?' + new URLSearchParams({kind: 4}))).map(r => r.id);
    const dl = document.createElement('datalist'); dl.id = 'dl-scnquests'; dl.innerHTML = qids.map(q => `<option value="${esc(q)}">`).join(''); document.body.appendChild(dl);
  } catch (e){}
}

function scnShotRow(s, i){
  const sc = SCN.ed.sc, aimed = !!(s.aim || s.from);
  const frame = s.from ? 'shoulder' : (Object.keys(SCN_FRAMES).find(k => SCN_FRAMES[k].offset && s.offset && SCN_FRAMES[k].offset.join() === s.offset.join()) || (aimed ? 'custom' : ''));
  return `<div class="scn-row" data-scnrow="shots:${i}"><input class="inp num scn-at" data-scnf="shots:${i}:at" value="${s.at || 0}" title="Seconds from the start"> s
    ${aimed ? `<select class="inp" data-scnf="shots:${i}:aimactor" style="max-width:150px">${sc.actors.map(a => `<option value="${esc(a.key)}" ${(s.aim || {}).actor === a.key ? 'selected' : ''}>${esc(scnName(a))}</option>`).join('')}</select>
      <select class="inp" data-scnf="shots:${i}:frame">${Object.entries(SCN_FRAMES).map(([k, f]) => `<option value="${k}" ${frame === k ? 'selected' : ''}>${f.label}</option>`).join('')}${frame === 'custom' ? '<option value="custom" selected>As it was made</option>' : ''}</select>
      <label title="The camera moves slowly in over the shot"><input type="checkbox" data-scnf="shots:${i}:push" ${s.move ? 'checked' : ''}> push in</label>`
      : `<span class="msg" style="min-width:180px" title="A fixed camera, where the 3D view was: ${s.pos ? s.pos.map(v => Math.round(v)).join(', ') : '?'}">📷 fixed · ${Math.round(s.yaw || 0)}° · ${Math.round(s.pitch || 0)}° up</span>
      <button class="btn sm" data-scnview="${i}" title="Take the 3D view's camera as it is now for this shot">Take the 3D view</button>`}
    <label>width</label><input class="inp num" data-scnf="shots:${i}:fov" value="${s.fov || (aimed ? 40 : 60)}" style="width:46px" title="Field of view, in degrees (smaller: closer)">°
    ${(s.at || 0) > 0 ? `<select class="inp" data-scnf="shots:${i}:cut" title="How the shot before gives way to this one">
      <option value="">cut</option><option value="dip" ${s.cut === 'dip' ? 'selected' : ''}>dip to black</option><option value="white" ${s.cut === 'white' ? 'selected' : ''}>dip to white</option></select>` : ''}
    <button class="btn sm" data-scnlook="${i}" title="Show this shot in the 3D view">👁</button>
    <button class="btn sm" data-scnrm="shots:${i}">✕</button></div>`;
}

function scnClipRow(x){
  const groups = scnAnimSorted(SCN.ed.anims[(scnActorId(x.a) || '').toLowerCase()] || []);
  const k = `clips:${x.ai}:${x.ci}`, cur = String(x.c.group || '').toLowerCase();
  return `<div class="scn-row" data-scnrow="${k}"><input class="inp num scn-at" data-scnf="${k}:at" value="${x.c.at || 0}"> s
    <b style="min-width:110px">${esc(scnName(x.a))}</b>
    <select class="inp" data-scnf="${k}:group" style="max-width:250px">${groups.some(g => g.group.toLowerCase() === cur) ? '' : `<option selected>${esc(x.c.group || '')}</option>`}${groups.map(g =>
      `<option ${g.group.toLowerCase() === cur ? 'selected' : ''} value="${esc(g.group)}">${esc(scnAnimLabel(g.group))} (${g.length} s)</option>`).join('')}</select>
    <button class="btn sm" data-scnseeanim="${k}" title="See this animation played">▶</button>
    <label><input type="checkbox" data-scnf="${k}:loop" ${x.c.loop ? 'checked' : ''}> repeat</label>
    <label>speed</label><input class="inp num" data-scnf="${k}:speed" value="${x.c.speed || 1}" style="width:44px">
    <button class="btn sm" data-scnrm="${k}">✕</button></div>`;
}

// ----- people coming and going: comes in (summoned, or just there at a time), walks between spots, dies or goes
const SCN_BONES = [['', 'whole body'], ['Bip01 Head', 'head'], ['Bip01 R Hand', 'right hand'], ['Bip01 L Hand', 'left hand'], ['Bip01 Spine1', 'chest'], ['Bip01 Pelvis', 'waist']];
function scnFxOptions(cur, none){
  const fx = (SCN.fx && SCN.fx.effects) || [], groups = [...new Set(fx.map(e => e.group))];
  const known = fx.some(e => e.model.toLowerCase() === String(cur || '').toLowerCase());
  return (none ? `<option value="">${none}</option>` : '') + (cur && !known ? `<option value="${esc(cur)}" selected>${esc(String(cur).split('/').pop())}</option>` : '')
    + groups.map(g => `<optgroup label="${esc(g)}">${fx.filter(e => e.group === g).map(e => `<option value="${esc(e.model)}" ${String(cur || '').toLowerCase() === e.model.toLowerCase() ? 'selected' : ''}>${esc(e.name)}</option>`).join('')}</optgroup>`).join('');
}
function scnActorMore(a, i){
  const ap = a.appear, lv = a.leave, sc = SCN.ed.sc;
  return `<div class="scn-row" style="padding-left:22px;font-size:12px">
    <label title="${a.spawn ? 'Made by the scene at their spot, at this time' : 'Not there when the scene starts; there from this time'}"><input type="checkbox" data-scna="${i}:appear" ${ap || a.spawn ? 'checked' : ''} ${a.spawn ? 'disabled' : ''}> comes in</label>
    ${ap || a.spawn ? `at <input class="inp num scn-at" data-scna="${i}:appearat" value="${(ap && ap.at) || 0}"> s
      <select class="inp" data-scna="${i}:appearfx" style="max-width:150px" title="An effect where they come in">${scnFxOptions(ap && ap.vfx, 'no effect')}</select>` : ''}
    <label><input type="checkbox" data-scna="${i}:leave" ${lv ? 'checked' : ''}> leaves</label>
    ${lv ? `at <input class="inp num scn-at" data-scna="${i}:leaveat" value="${lv.at || 0}"> s
      <select class="inp" data-scna="${i}:how"><option value="vanish">vanishes</option><option value="die" ${lv.how === 'die' ? 'selected' : ''}>dies</option></select>
      <select class="inp" data-scna="${i}:leavefx" style="max-width:150px">${scnFxOptions(lv.vfx, 'no effect')}</select>` : ''}
    ${a.spawn ? `<label title="Unticked, they are gone once the scene ends"><input type="checkbox" data-scna="${i}:stay" ${a.stay ? 'checked' : ''}> stays after</label>`
      : `<label title="Put back where they stood once the scene ends"><input type="checkbox" data-scna="${i}:back" ${a.back ? 'checked' : ''}> back after</label>`}
    <button class="btn sm" data-scnwalk="${i}" title="They walk to a new spot (drag its 📍 in 3D); add more for a path">+ Walk</button></div>
    ${(a.moves || []).map((mv, j) => `<div class="scn-row" data-scnrow="moves:${i}:${j}" style="padding-left:22px;font-size:12px"><input class="inp num scn-at" data-scna="${i}:mvat:${j}" value="${mv.at || 0}"> s
      🚶 walks to <b>${esc(scnMarkLabel(mv.to))}</b> <label><input type="checkbox" data-scna="${i}:mvrun:${j}" ${mv.run ? 'checked' : ''}> runs</label>
      <span class="msg">${sc.marks[mv.to] ? 'drag its 📍 in 3D' : 'no spot!'}</span><button class="btn sm" data-scna="${i}:mvrm:${j}">✕</button></div>`).join('')}`;
}
function scnMarkLabel(name){
  const sc = SCN.ed.sc;
  for (const a of sc.actors) (a.moves || []).forEach((mv, j) => { if (mv.to === name) name = scnName(a) + ' › ' + (j + 1); });
  return name;
}
function scnNewMark(base, near, ahead){
  // (a new spot: ahead of where someone is, or at the middle of the 3D view)
  const sc = SCN.ed.sc;
  let n = 1; while (sc.marks[base + n]) n++;
  let p = near;
  if (!p && typeof V3 !== 'undefined' && V3.on && V3.lastPick && V3.lastPick.point){ const o = V3.origin, pt = V3.lastPick.point; p = [pt.x + o[0], pt.y + o[1], pt.z + o[2], 0]; }
  if (!p && typeof V3 !== 'undefined' && V3.on && V3.pos && typeof v3Dir === 'function'){ const d = v3Dir(), o = V3.origin; p = [V3.pos.x + o[0] + d.x * 400, V3.pos.y + o[1] + d.y * 400, V3.pos.z + o[2] - 120, 0]; }
  if (!p && typeof W !== 'undefined' && W.cam) p = [W.cam.x, W.cam.y, typeof groundZ === 'function' ? groundZ(W.cam.x, W.cam.y) : 0, 0];
  p = (p || [0, 0, 0, 0]).slice();
  const y = (p[3] || 0) * Math.PI / 180, f = ahead || 0;
  sc.marks[base + n] = [Math.round(p[0] + Math.sin(y) * f), Math.round(p[1] + Math.cos(y) * f), Math.round(p[2] || 0), Math.round(p[3] || 0)];
  return base + n;
}
function scnAct(el){
  const sc = SCN.ed.sc, [i, f, j] = el.dataset.scna.split(':'), a = sc.actors[+i], v = el.type === 'checkbox' ? el.checked : el.value;
  if (!a) return;
  if (f === 'appear'){ if (v) a.appear = {at: SCN.ed.cursor || 1}; else delete a.appear; return scnChanged(true); }
  if (f === 'appearat'){ a.appear = Object.assign(a.appear || {}, {at: scnNum(v, 0)}); return scnChanged(); }
  if (f === 'appearfx'){ a.appear = a.appear || {at: 0}; if (v) a.appear.vfx = v; else delete a.appear.vfx; return scnChanged(); }
  if (f === 'leave'){ if (v) a.leave = {at: SCN.ed.cursor || Math.max(0, (sc.length || 10) - 2), how: 'vanish'}; else delete a.leave; return scnChanged(true); }
  if (f === 'leaveat'){ a.leave.at = scnNum(v, 0); return scnChanged(); }
  if (f === 'how'){ a.leave.how = v; return scnChanged(); }
  if (f === 'leavefx'){ if (v) a.leave.vfx = v; else delete a.leave.vfx; return scnChanged(); }
  if (f === 'stay' || f === 'back'){ if (v) a[f] = true; else delete a[f]; return scnChanged(); }
  const mv = (a.moves || [])[+j];
  if (f === 'mvat' && mv){ mv.at = scnNum(v, 0); return scnChanged(); }
  if (f === 'mvrun' && mv){ if (v) mv.run = true; else delete mv.run; return scnChanged(); }
  if (f === 'mvrm' && mv){ a.moves.splice(+j, 1); if (!a.moves.length) delete a.moves; if (!sc.actors.some(x => (x.moves || []).some(m => m.to === mv.to))) delete sc.marks[mv.to]; return scnChanged(true); }
}
function scnWalk(a){
  const sc = SCN.ed.sc, last = (a.moves || []).slice(-1)[0];
  const from = (last && sc.marks[last.to]) || scnStandAt(a.key);
  const name = scnNewMark(a.key + '_w', from, 250);
  if (from){ const m = sc.marks[name]; m[3] = scnFacing(from, m); }
  (a.moves = a.moves || []).push({at: SCN.ed.cursor || 0, to: name});
  scnChanged(true);
}

// ----- effects: on someone (a bone) or at a spot, for a time or until the end; fire, magic, the mod's own particles
function scnFxRow(v, i){
  const sc = SCN.ed.sc, onSpot = !v.on;
  return `<div class="scn-row" data-scnrow="vfx:${i}"><input class="inp num scn-at" data-scnf="vfx:${i}:at" value="${v.at || 0}"> s
    <select class="inp" data-scnf="vfx:${i}:model" style="max-width:170px">${scnFxOptions(v.model)}</select>
    <select class="inp" data-scnf="vfx:${i}:on" style="max-width:140px">${sc.actors.map(a => `<option value="${esc(a.key)}" ${v.on === a.key ? 'selected' : ''}>on ${esc(scnName(a))}</option>`).join('')}
      <option value="" ${onSpot ? 'selected' : ''}>at a spot</option></select>
    ${onSpot ? '<span class="msg" title="Drag its 📍 in 3D">📍</span>' : `<select class="inp" data-scnf="vfx:${i}:bone">${SCN_BONES.map(([b, l]) => `<option value="${b}" ${(v.bone || '') === b ? 'selected' : ''}>${l}</option>`).join('')}</select>`}
    <label>for</label><input class="inp num" data-scnf="vfx:${i}:dur" value="${v.dur != null ? v.dur : ''}" placeholder="end" style="width:44px" title="Seconds (empty: until the scene ends)"> s
    <label title="Plays over and over while it lasts (fire, smoke)"><input type="checkbox" data-scnf="vfx:${i}:loop" ${v.loop ? 'checked' : ''}> repeats</label>
    <button class="btn sm" data-scnrm="vfx:${i}">✕</button></div>`;
}

// ----- the world: doors, levers, lights and things; the weather; the hour
const SCN_DO = {door: [['open', 'opens'], ['close', 'closes']], light: [['hide', 'goes out'], ['show', 'comes on']],
  activator: [['activate', 'is used'], ['hide', 'is hidden'], ['show', 'is shown']], container: [['activate', 'is opened'], ['hide', 'is hidden'], ['show', 'is shown']]};
const scnRefKey = r => r ? String(r.file).toLowerCase() + '|' + r.index : '';
function scnObjName(o){ return ({door: '🚪', light: '💡', activator: '⚙', container: '📦'}[o.type] || '') + ' ' + o.name + (o.teleport ? ' (to elsewhere)' : ''); }
function scnWorldRow(w, i){
  const E = SCN.ed;
  let body;
  if (w.weather != null) body = `<b style="min-width:100px">☁ Weather</b><select class="inp" data-scnf="world:${i}:weather">${((SCN.fx && SCN.fx.weathers) || []).map(x => `<option ${String(w.weather).toLowerCase() === x.toLowerCase() ? 'selected' : ''}>${x}</option>`).join('')}</select>
    <label title="The weather before comes back once the scene ends"><input type="checkbox" data-scnf="world:${i}:back" ${w.back ? 'checked' : ''}> back after</label>`;
  else if (w.hour != null) body = `<b style="min-width:100px">🕓 Time</b>moves on to <input class="inp num" data-scnf="world:${i}:hour" value="${w.hour}" style="width:44px" title="0 to 24 (21: nine at night)"> o'clock`;
  else {
    const cur = E.objects.find(o => scnRefKey(o.ref) === scnRefKey(w.ref));
    const kinds = SCN_DO[(cur || {}).type] || SCN_DO.activator;
    body = `<select class="inp" data-scnf="world:${i}:obj" style="max-width:220px">${cur ? '' : '<option selected>(not in this place)</option>'}${E.objects.map((o, k) => `<option value="${k}" ${o === cur ? 'selected' : ''}>${esc(scnObjName(o))}</option>`).join('')}</select>
      <select class="inp" data-scnf="world:${i}:do">${kinds.map(([d, l]) => `<option value="${d}" ${(w.do || 'activate') === d ? 'selected' : ''}>${l}</option>`).join('')}</select>`;
  }
  return `<div class="scn-row" data-scnrow="world:${i}"><input class="inp num scn-at" data-scnf="world:${i}:at" value="${w.at || 0}"> s ${body}
    <button class="btn sm" data-scnrm="world:${i}">✕</button></div>`;
}

// ----- sounds at a time: the game's sounds by name (or a file), heard from someone or something
function scnSoundRow(x, i){
  const sc = SCN.ed.sc, E = SCN.ed, from = x.on ? 'a:' + x.on : x.ref ? 'o:' + scnRefKey(x.ref) : '';
  return `<div class="scn-row" data-scnrow="sound:${i}"><input class="inp num scn-at" data-scnf="sound:${i}:at" value="${x.at || 0}"> s
    <b>🔉</b><input class="inp" data-scnf="sound:${i}:sound" value="${esc(x.sound || '')}" list="dl-scnsnd" placeholder="a sound's name, or Sound/…" style="max-width:190px">
    <select class="inp" data-scnf="sound:${i}:from" style="max-width:170px"><option value="">heard everywhere</option>
      ${sc.actors.map(a => `<option value="a:${esc(a.key)}" ${from === 'a:' + a.key ? 'selected' : ''}>from ${esc(scnName(a))}</option>`).join('')}
      ${E.objects.map(o => `<option value="o:${esc(scnRefKey(o.ref))}" ${from === 'o:' + scnRefKey(o.ref) ? 'selected' : ''}>from ${esc(scnObjName(o))}</option>`).join('')}</select>
    <button class="btn sm" data-scnrm="sound:${i}">✕</button></div>`;
}
async function scnSoundList(){
  if (SCN.sounds) return;
  try { SCN.sounds = (await api('/api/search?' + new URLSearchParams({q: '', types: 'SOUN', limit: 1000}))).rows.map(r => r.id); } catch (e){ SCN.sounds = []; }
  const dl = $('#dl-scnsnd') || Object.assign(document.createElement('datalist'), {id: 'dl-scnsnd'});
  dl.innerHTML = SCN.sounds.map(x => `<option value="${esc(x)}">`).join(''); if (!dl.parentNode) document.body.appendChild(dl);
}

// ----- the look: post-processing cues (colour, focus, motion blur), blended in over dur, held until changed
const SCN_PP_NUM = ['exposure', 'temperature', 'saturation', 'vignette', 'blur', 'range', 'motionblur', 'dur'];
function scnLookKind(x){ return x.blur != null || x.focus != null ? 'dof' : x.motionblur != null ? 'mb' : ['exposure', 'temperature', 'saturation', 'vignette'].some(k => x[k] != null) ? 'col' : ''; }
function scnLookRow(x, i){
  const kind = scnLookKind(x); if (!kind) return '';
  const k = 'screen:' + i, sc = SCN.ed.sc;
  const n = (f, label, tip, w) => `<label title="${tip}">${label}</label><input class="inp num" data-scnf="${k}:${f}" value="${x[f] != null ? x[f] : ''}" style="width:${w || 46}px" title="${tip}">`;
  let body;
  if (kind === 'col') body = n('exposure', 'light', 'Brighter or darker, in steps: 1 is twice as bright, -1 half (0: as it is)')
    + n('temperature', 'warmth', 'Warmer (up to 100) or colder (down to -100); 0: as it is')
    + n('saturation', 'colour', '1: as it is; 0: grey; 2: twice as strong')
    + n('vignette', 'edges', 'Dark edges, 0 to 1');
  else if (kind === 'dof'){
    const who = x.focus && typeof x.focus === 'object' ? x.focus.actor : '';
    body = `<label title="What stays sharp">sharp on</label><select class="inp" data-scnf="${k}:focuswho" style="max-width:150px">
      ${sc.actors.map(a => `<option value="${esc(a.key)}" ${who === a.key ? 'selected' : ''}>${esc(scnName(a))}</option>`).join('')}
      <option value="player" ${who === 'player' ? 'selected' : ''}>the player</option>
      <option value="" ${who ? '' : 'selected'}>a distance</option></select>
      ${who ? '' : `<input class="inp num" data-scnf="${k}:focusd" value="${typeof x.focus === 'number' ? x.focus : 400}" style="width:56px" title="Units from the camera"> units`}`
      + n('blur', 'blur', 'How soft the rest is, 0 to 1') + n('range', 'depth', 'How deep the sharp part is, in units', 56);
  } else body = n('motionblur', 'strength', 'Blur as the camera moves, 0 to 1 (0: off)');
  const icon = {col: '🎨 Colour', dof: '🔍 Focus', mb: '💨 Motion blur'}[kind];
  return `<div class="scn-row" data-scnrow="${k}"><input class="inp num scn-at" data-scnf="${k}:at" value="${x.at || 0}"> s
    <b style="min-width:100px">${icon}</b>${body}
    ${n('dur', 'over', 'Seconds it takes to blend in from what it was (0: at once)', 40)} s
    <button class="btn sm" data-scnrm="${k}">✕</button></div>`;
}

function scnBind(){
  const E = SCN.ed, sc = E.sc, m = scnHostEl();
  const q = id => m.querySelector('#' + id);
  q('scn-name').oninput = e => { sc.name = e.target.value; if (E.isNew){ const id = e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '').slice(0, 40); if (id){ sc.scene = id; q('scn-id').value = id; } } scnChanged(); };
  q('scn-id').oninput = e => { sc.scene = e.target.value.trim(); scnChanged(); };
  q('scn-len').oninput = e => { sc.length = scnNum(e.target.value, sc.length); scnEndFade(); scnChanged(); };
  q('scn-ctl').onchange = e => { sc.player.controls = e.target.checked ? 'off' : 'on'; scnChanged(); };
  q('scn-sheathe').onchange = e => { sc.player.sheathe = e.target.checked; scnChanged(); };
  m.querySelectorAll('[data-scnf]').forEach(el => el.addEventListener(el.type === 'checkbox' || el.tagName === 'SELECT' ? 'change' : 'input', () => scnField(el)));
  m.querySelectorAll('[data-scnrm]').forEach(b => b.onclick = () => scnRemove(b.dataset.scnrm));
  m.querySelectorAll('[data-scna]').forEach(el => el.tagName === 'BUTTON' ? el.onclick = () => scnAct(el)
    : el.addEventListener(el.type === 'checkbox' || el.tagName === 'SELECT' ? 'change' : 'input', () => scnAct(el)));
  m.querySelectorAll('[data-scnwalk]').forEach(b => b.onclick = () => scnWalk(sc.actors[+b.dataset.scnwalk]));
  m.querySelectorAll('[data-scnunmark]').forEach(b => b.onclick = () => scnUnmark(b.dataset.scnunmark));
  m.querySelectorAll('[data-scnview]').forEach(b => b.onclick = () => { if (scnTakeView(sc.shots[+b.dataset.scnview])) scnChanged(true); });
  m.querySelectorAll('[data-scnlook]').forEach(b => b.onclick = () => scnLook(sc.shots[+b.dataset.scnlook]));
  m.querySelectorAll('[data-scnvoice]').forEach(b => b.onclick = () => scnVoicePick(sc.lines[+b.dataset.scnvoice], b));
  m.querySelectorAll('[data-scnnovoice]').forEach(b => b.onclick = () => { const l = sc.lines[+b.dataset.scnnovoice]; delete l.voice; delete l.dur; scnChanged(true); });
  m.querySelectorAll('[data-scnseeanim]').forEach(b => b.onclick = () => { const p = b.dataset.scnseeanim.split(':'); scnSeeAnim(sc.actors[+p[1]], sc.actors[+p[1]].clips[+p[2]].group); });
  const add = q('scn-addactor');
  if (add) add.onclick = async () => {
    const present = new Set(sc.actors.map(a => a.ref ? a.ref.file.toLowerCase() + '|' + a.ref.index : ''));
    const p = E.people.filter(x => !present.has(x.ref.file.toLowerCase() + '|' + x.ref.index))[+q('scn-addwho').value];
    if (p) await scnAddPerson(p);
  };
  q('scn-addview').onclick = () => { const s = {at: scnShotTime()}; if (scnTakeView(s)){ sc.shots.push(s); scnChanged(true); } };
  q('scn-addaim').onclick = () => { if (!sc.actors.length) return; sc.shots.push({at: scnShotTime(), aim: {actor: sc.actors[0].key, at: 'head'}, offset: SCN_FRAMES.close.offset.slice(), fov: SCN_FRAMES.close.fov}); scnChanged(true); };
  q('scn-addclip').onclick = () => {
    if (!sc.actors.length) return;
    const a = sc.actors[0], g = scnAnimSorted(E.anims[(scnActorId(a) || '').toLowerCase()] || []).find(g => /^idle\d/i.test(g.group));
    (a.clips = a.clips || []).push({at: E.cursor, group: g ? g.group : 'Idle', loop: false, speed: 1}); scnChanged(true);
  };
  q('scn-addline').onclick = () => {
    const last = scnSort(sc.lines.slice()).pop(), at = E.cursor || (last ? Math.round(((last.at || 0) + scnLineLen(last) + 0.4) * 10) / 10 : 1);
    sc.lines.push({at, who: sc.actors.length ? sc.actors[0].key : 'player', text: ''}); scnChanged(true);
  };
  const sp = q('scn-spacelines');
  if (sp) sp.onclick = () => {
    const l = scnSort(sc.lines);
    for (let i = 1; i < l.length; i++) l[i].at = Math.round(((l[i - 1].at || 0) + scnLineLen(l[i - 1]) + 0.4) * 10) / 10;
    const end = l.length ? (l[l.length - 1].at || 0) + scnLineLen(l[l.length - 1]) + 1 : 0;
    if (end > (sc.length || 0)) { sc.length = Math.ceil(end); scnEndFade(); }
    scnChanged(true);
  };
  q('scn-addvid').onclick = () => { sc.screen.push({at: E.cursor, movie: ''}); scnChanged(true); };
  q('scn-addfx').onclick = () => {
    const a = sc.actors[0];
    const v = {at: E.cursor || 0, model: 'meshes/e/magic_hit_dst.NIF', dur: 2};
    if (a) v.on = a.key; else v.mark = scnNewMark('fx', null, 0);
    sc.vfx.push(v); scnChanged(true);
  };
  q('scn-addobj').onclick = () => { const o = E.objects.find(x => x.type === 'door') || E.objects[0]; if (!o) return;
    sc.world.push({at: E.cursor || 0, ref: o.ref, do: (SCN_DO[o.type] || SCN_DO.activator)[0][0]}); scnChanged(true); };
  q('scn-addweather').onclick = () => { sc.world.push({at: E.cursor || 0, weather: 'Thunderstorm', back: true}); scnChanged(true); };
  q('scn-addhour').onclick = () => { sc.world.push({at: E.cursor || 0, hour: 21}); scnChanged(true); };
  q('scn-addsnd').onclick = () => { scnSoundList(); sc.sound.push({at: E.cursor || 0, sound: ''}); scnChanged(true); };
  q('scn-addshake').onclick = () => { sc.screen.push({at: E.cursor || 0, shake: 0.5, dur: 1}); scnChanged(true); };
  q('scn-etalk').onchange = e => { sc.end.do = sc.end.do.filter(d => !d.talk); if (e.target.value) sc.end.do.push({talk: e.target.value}); scnChanged(); };
  const nw = q('scn-newwho');
  nw.oninput = () => { clearTimeout(nw._t); nw._t = setTimeout(async () => {
    try { const r = await api('/api/search?' + new URLSearchParams({q: nw.value, types: 'NPC_,CREA', limit: 40}));
      E.newRows = r.rows; m.querySelector('#dl-scnnew').innerHTML = r.rows.map(x => `<option value="${esc(x.id)}">${esc(x.name || x.id)}</option>`).join(''); } catch (e){}
  }, 220); };
  q('scn-newadd').onclick = async () => {
    const id = nw.value.trim(); if (!id) return;
    const row = (E.newRows || []).find(x => x.id.toLowerCase() === id.toLowerCase());
    const key = scnNewKey(id), at = E.cursor || 0;
    const near = sc.actors[0] ? scnStandAt(sc.actors[0].key) : null;
    sc.marks[key] = sc.marks[scnNewMark(key + '_', near, near ? 220 : 0)]; delete sc.marks[Object.keys(sc.marks).find(k => k.startsWith(key + '_') && sc.marks[k] === sc.marks[key])];
    if (near){ const mk = sc.marks[key]; mk[3] = scnFacing(mk, near); }
    let name = row && (row.name || row.id);
    if (!name) try { const r = await api('/api/search?' + new URLSearchParams({q: id, types: 'NPC_,CREA', limit: 10}));
      const x = r.rows.find(x => x.id.toLowerCase() === id.toLowerCase()); if (!x){ toast('There is no person or creature "' + id + '".', true); delete sc.marks[key]; return; } name = x.name || x.id; } catch (e){}
    sc.actors.push({key, id, name, spawn: true, mark: key, appear: {at}, clips: []});
    await scnAnims(id); scnChanged(true);
  };
  q('scn-addcol').onclick = () => { sc.screen.push({at: E.cursor, exposure: 0, temperature: 0, saturation: 1, vignette: 0.3, dur: 1}); scnChanged(true); };
  q('scn-adddof').onclick = () => { sc.screen.push({at: E.cursor, blur: 0.7, range: 250, focus: sc.actors.length ? {actor: sc.actors[0].key} : 400, dur: 0.5}); scnChanged(true); };
  q('scn-addmb').onclick = () => { sc.screen.push({at: E.cursor, motionblur: 0.5}); scnChanged(true); };
  q('scn-fadein').onchange = e => { sc.screen = sc.screen.filter(x => x.fade !== 'in'); if (e.target.checked) sc.screen.unshift({at: 0, fade: 'in', dur: 1}); scnChanged(); };
  q('scn-fadeout').onchange = e => { sc.screen = sc.screen.filter(x => x.fade !== 'out'); if (e.target.checked) sc.screen.push({at: Math.max(0, (sc.length || 0) - 1), fade: 'out', dur: 1}); scnChanged(); };
  q('scn-lbox').onchange = e => { sc.screen = sc.screen.filter(x => x.letterbox == null); if (e.target.checked) sc.screen.push({at: 0, letterbox: '2.39'}); scnChanged(); };
  q('scn-music').oninput = e => { sc.sound = sc.sound.filter(x => !x.music); if (e.target.value.trim()) sc.sound.unshift({at: 0, music: e.target.value.trim()}); scnChanged(); };
  const endSet = () => {
    sc.end.do = sc.end.do.filter(d => !d.quest && !d.global);
    if (!sc.end.do.some(d => d.controls)) sc.end.do.unshift({controls: 'on'});
    const qq = q('scn-eq').value.trim(), st = scnNum(q('scn-es').value, null), g = q('scn-eg').value.trim();
    if (qq && st != null) sc.end.do.push({quest: qq, stage: st});
    if (g) sc.end.do.push({global: g, value: 1});
    scnChanged();
  };
  ['scn-eq', 'scn-es', 'scn-eg'].forEach(id => q(id).oninput = endSet);
  const show = () => { const k = q('scn-kind').value; [['area', 'area'], ['dlg', 'dialogue'], ['quest', 'quest'], ['global', 'global']].forEach(([n, v]) => q('scn-' + n).style.display = k === v ? '' : 'none'); };
  const trSet = () => { show(); scnTrigger(); scnChanged(); };
  ['scn-kind', 'scn-once'].forEach(id => q(id).onchange = trSet);
  ['scn-r', 'scn-q', 'scn-st', 'scn-g'].forEach(id => q(id).oninput = trSet);
  q('scn-spot').onclick = () => {
    let p = null;
    if (typeof V3 !== 'undefined' && V3.on && V3.lastPick && V3.lastPick.point){ const o = V3.origin, pt = V3.lastPick.point; p = [pt.x + o[0], pt.y + o[1], pt.z + o[2]]; }
    else if (typeof V3 !== 'undefined' && V3.on && V3.pos){ const d = v3Dir(); const o = V3.origin; p = [V3.pos.x + o[0] + d.x * 300, V3.pos.y + o[1] + d.y * 300, V3.pos.z + o[2] - 100]; }
    else if (typeof W !== 'undefined' && W.cam) p = [W.cam.x, W.cam.y, 0];
    if (!p) return;
    sc.trigger = Object.assign({kind: 'area', radius: 300, once: true}, sc.trigger && sc.trigger.kind === 'area' ? sc.trigger : {}, {center: p.map(Math.round)});
    if (!Array.isArray(sc.cell)) sc.trigger.cell = sc.cell;
    scnChanged(true);
  };
  show();
  q('scn-save').onclick = () => scnSave();
  q('scn-check').onclick = async () => { try { E.problems = (await post('/api/scenes/check', {scene: sc})).problems; scnProblems(true); } catch (e){ toast(e.message, true); } };
  q('scn-prev').onclick = () => SCN.prev ? scnPreviewStop() : scnPreview();
  q('scn-try').onclick = () => scnTry();
  const td = q('scn-todock'); if (td) td.onclick = () => scnDock();
  q('scn-back').onclick = () => { if (E.dock){ if (scnLeave()){ showView('scripts'); scnShow(); } } else scnOverview(); };
  const del = q('scn-del');
  if (del) del.onclick = async () => {
    try { await post('/api/scenes/delete', {scene: sc.scene}); afterChange(); E.dirty = false; SCN.open = null; await scnMine(); if (scnLeave()) toast('Scene removed: Undo brings it back.'); }
    catch (e){ toast(e.message, true); }
  };
}

async function scnAddPerson(p){
  const sc = SCN.ed.sc;
  if (sc.actors.some(a => a.ref && a.ref.file.toLowerCase() === p.ref.file.toLowerCase() && a.ref.index === p.ref.index)) return;
  sc.actors.push({key: scnNewKey(p.id), ref: p.ref, clips: []});
  await scnAnims(p.id);
  scnChanged(true);
}

function scnEndFade(){
  const f = SCN.ed.sc.screen.find(x => x.fade === 'out');
  if (f) f.at = Math.max(0, (SCN.ed.sc.length || 0) - (f.dur || 1));
}

function scnTrigger(){
  const sc = SCN.ed.sc, m = scnHostEl(), q = id => m.querySelector('#' + id);
  const k = q('scn-kind').value, once = q('scn-once').checked, old = sc.trigger || {};
  if (!k){ delete sc.trigger; return; }
  if (k === 'area') sc.trigger = {kind: k, center: old.kind === 'area' && old.center ? old.center : null, radius: scnNum(q('scn-r').value, 300), once};
  else if (k === 'dialogue') sc.trigger = old.from === 'dialogue' ? Object.assign({}, old, {once}) : {kind: 'dialogue', once};
  else if (k === 'quest') sc.trigger = {kind: k, quest: q('scn-q').value.trim(), stage: scnNum(q('scn-st').value, 10), once};
  else sc.trigger = {kind: k, name: q('scn-g').value.trim(), value: 1, once};
  if (k === 'area' && !Array.isArray(sc.cell)) sc.trigger.cell = sc.cell;
  if (k === 'area' && !sc.trigger.center){
    const a = sc.actors[0], p = a && scnPerson(a);
    sc.trigger.center = p ? p.pos.slice() : (W && W.cam ? [Math.round(W.cam.x), Math.round(W.cam.y), 0] : [0, 0, 0]);
  }
}

function scnField(el){
  const sc = SCN.ed.sc, parts = el.dataset.scnf.split(':'), val = el.type === 'checkbox' ? el.checked : el.value;
  if (parts[0] === 'clips'){
    const c = sc.actors[+parts[1]].clips[+parts[2]], f = parts[3];
    if (f === 'at' || f === 'speed') c[f] = scnNum(val, c[f]); else c[f] = val;
    return scnChanged();
  }
  const o = sc[parts[0]][+parts[1]], f = parts[2];     // (the rows are in the order the list was drawn in)
  if (f === 'at' || f === 'fov') o[f] = scnNum(val, o[f]);
  else if (parts[0] === 'screen' && (SCN_PP_NUM.includes(f) || f === 'shake')){ const v = scnNum(val, null); if (v == null) delete o[f]; else o[f] = v; }
  else if (['dur', 'hour'].includes(f) && ['vfx', 'world'].includes(parts[0])){ const v = scnNum(val, null); if (v == null) delete o[f]; else o[f] = v; }
  else if (parts[0] === 'vfx' && f === 'on'){
    if (val){ o.on = val; delete o.mark; delete o.pos; } else { delete o.on; delete o.bone; const t = scnStandAt(sc.actors[0] ? sc.actors[0].key : 'player'); o.mark = scnNewMark('fx', t, 0); }
    return scnChanged(true);
  }
  else if (parts[0] === 'vfx' && f === 'bone'){ if (val) o.bone = val; else delete o.bone; }
  else if (parts[0] === 'vfx' && f === 'loop'){ if (val) o.loop = true; else delete o.loop; }
  else if (parts[0] === 'world' && f === 'obj'){ const ob = SCN.ed.objects[+val]; if (ob){ o.ref = ob.ref; o.do = (SCN_DO[ob.type] || SCN_DO.activator)[0][0]; } return scnChanged(true); }
  else if (parts[0] === 'world' && f === 'back'){ if (val) o.back = true; else delete o.back; }
  else if (parts[0] === 'sound' && f === 'from'){
    delete o.on; delete o.ref;
    if (val.startsWith('a:')) o.on = val.slice(2);
    else if (val.startsWith('o:')){ const ob = SCN.ed.objects.find(x => scnRefKey(x.ref) === val.slice(2)); if (ob) o.ref = ob.ref; }
  }
  else if (parts[0] === 'shots' && f === 'cut'){ if (val) o.cut = val; else { delete o.cut; delete o.cutdur; } }
  else if (f === 'focuswho'){ o.focus = val ? {actor: val} : 400; return scnChanged(true); }
  else if (f === 'focusd') o.focus = scnNum(val, 400);
  else if (f === 'aimactor'){ o.aim = Object.assign({}, o.aim || {}, {actor: val}); }
  else if (f === 'frame'){
    const fr = SCN_FRAMES[val]; if (!fr) return;
    if (fr.from){ o.from = {actor: 'player', shoulder: 'right'}; delete o.offset; } else { delete o.from; o.offset = fr.offset.slice(); }
    o.aim = Object.assign({at: 'head'}, o.aim || {}); o.fov = fr.fov; if (o.move) scnPush(o, true);
    return scnChanged(true);
  }
  else if (f === 'push') scnPush(o, val);
  else if (f === 'who'){ o.who = val; delete o.actor; }
  else o[f] = val;
  scnChanged();
}

function scnPush(s, on){
  if (!on || !s.offset){ delete s.move; return; }
  const next = scnSort(SCN.ed.sc.shots.slice()).find(x => (x.at || 0) > (s.at || 0));
  const dur = Math.max(1, ((next ? next.at : SCN.ed.sc.length) || 0) - (s.at || 0));
  s.move = {to: {offset: s.offset.map((v, i) => i === 2 ? v : Math.round(v * 0.7))}, ease: 'inOut', dur};
}

function scnRemove(k){
  const sc = SCN.ed.sc, p = k.split(':');
  if (p[0] === 'clips') sc.actors[+p[1]].clips.splice(+p[2], 1);
  else if (p[0] === 'actors'){
    const a = sc.actors.splice(+p[1], 1)[0];
    sc.lines = sc.lines.filter(l => (l.who || l.actor) !== a.key);
    sc.shots = sc.shots.filter(s => !(s.aim && s.aim.actor === a.key));
    sc.vfx = sc.vfx.filter(v => v.on !== a.key);
    sc.sound.forEach(x => { if (x.on === a.key) delete x.on; });
    (a.moves || []).forEach(mv => delete sc.marks[mv.to]);
    if (a.mark) delete sc.marks[a.mark];
  } else {
    const o = sc[p[0]][+p[1]]; sc[p[0]] = sc[p[0]].filter(x => x !== o);
    if (p[0] === 'vfx' && o && o.mark && !sc.vfx.some(v => v.mark === o.mark)) delete sc.marks[o.mark];
  }
  scnChanged(true);
}

// ----- marks: where someone stands for the scene (the game puts them there, turned as the mark says)
function scnMarkPos(key){
  const sc = SCN.ed.sc;
  if (key.startsWith('m:')) return sc.marks[key.slice(2)];
  if (key === 'player') return sc.player.mark && sc.marks[sc.player.mark];
  const a = sc.actors.find(x => x.key === key);
  return a && a.mark && sc.marks[a.mark];
}
function scnStandAt(key){
  // (where someone will be: their mark, or where they stand now; [x, y, z, yaw])
  const m = scnMarkPos(key); if (m) return m;
  if (key === 'player') return null;
  const a = SCN.ed.sc.actors.find(x => x.key === key), p = a && scnPerson(a);
  return p ? [p.pos[0], p.pos[1], p.pos[2], p.yaw] : null;
}
function scnFacing(from, to){ return Math.round(Math.atan2(to[0] - from[0], to[1] - from[1]) * 1800 / Math.PI) / 10; }

function scnSetMark(key, spot, keepYaw){
  const sc = SCN.ed.sc, s = [Math.round(spot[0]), Math.round(spot[1]), Math.round(spot[2] || 0)];
  if (key.startsWith('m:')){
    // (a walk's or an effect's spot: moved; a walk's last spot turns the way they came)
    const name = key.slice(2), old = sc.marks[name] || [0, 0, 0, 0];
    let yaw = old[3] || 0;
    sc.actors.forEach(a => (a.moves || []).forEach((mv, j) => { if (mv.to === name){ const prev = j ? sc.marks[a.moves[j - 1].to] : scnStandAt(a.key); if (prev) yaw = scnFacing(prev, s); } }));
    sc.marks[name] = [s[0], s[1], s[2], yaw];
    return scnChanged(true);
  }
  // (turned toward the other one: someone faces the player, the player faces the first person)
  const other = key === 'player' ? (sc.actors[0] && scnStandAt(sc.actors[0].key)) : scnStandAt('player');
  const old = scnMarkPos(key);
  const yaw = keepYaw && old ? old[3] : other ? scnFacing(s, other) : (old ? old[3] : 0);
  const name = key === 'player' ? 'P' : key;
  sc.marks[name] = [s[0], s[1], s[2], yaw];
  if (key === 'player'){
    sc.player.mark = name;
    // (people on spots turn to face the player, unless turned by hand: dragged ones keep their turn)
    if (!keepYaw) sc.actors.forEach(a => { const m = a.mark && sc.marks[a.mark]; if (m && !m[4]) m[3] = scnFacing(m, s); });
  } else { const a = sc.actors.find(x => x.key === key); if (a) a.mark = name; }
  scnChanged(true);
}
function scnUnmark(key){
  const sc = SCN.ed.sc;
  if (key === 'player'){ if (sc.player.mark) delete sc.marks[sc.player.mark]; delete sc.player.mark; }
  else { const a = sc.actors.find(x => x.key === key); if (a && a.mark){ delete sc.marks[a.mark]; delete a.mark; } }
  scnChanged(true);
}
function scnCamHere(spot, key){
  const sc = SCN.ed.sc, t = scnStandAt(key); if (!t) return;
  const eye = [spot[0], spot[1], (spot[2] || 0) + 120], head = [t[0], t[1], t[2] + 105];
  const d = [head[0] - eye[0], head[1] - eye[1], head[2] - eye[2]];
  sc.shots.push({at: scnShotTime(), pos: eye.map(Math.round), yaw: Math.round(((Math.atan2(d[0], d[1]) * 180 / Math.PI) % 360 + 360) % 360 * 10) / 10,
    pitch: Math.round(Math.atan2(d[2], Math.hypot(d[0], d[1])) * 1800 / Math.PI) / 10, fov: 50});
  scnChanged(true);
}

// ----- the 3D view: marks drawn and dragged, a shot taken from it or shown in it
function scnTextSprite(text, color){
  const c = document.createElement('canvas'); c.width = 256; c.height = 64;
  const g = c.getContext('2d'); g.font = 'bold 30px sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
  g.lineWidth = 6; g.strokeStyle = 'rgba(0,0,0,.85)'; g.strokeText(text, 128, 32); g.fillStyle = color; g.fillText(text, 128, 32);
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({map: new THREE.CanvasTexture(c), depthTest: false, transparent: true}));
  sp.scale.set(160, 40, 1); sp.renderOrder = 999;
  return sp;
}
function scnMarks3D(){
  if (typeof V3 === 'undefined' || !V3.scene || typeof THREE === 'undefined') return;
  if (V3.scnGroup){ V3.scene.remove(V3.scnGroup); V3.scnGroup = null; }
  const E = SCN.ed; if (!E || !V3.on || scnKeyOf(E.sc.cell) !== W.key) return;
  const sc = E.sc, o = V3.origin || [0, 0, 0], G = new THREE.Group();
  const pin = (key, label, col, m) => {
    const body = new THREE.Mesh(new THREE.CylinderGeometry(22, 22, 130, 16), new THREE.MeshBasicMaterial({color: col, transparent: true, opacity: 0.45, depthWrite: false}));
    body.rotation.x = Math.PI / 2; body.position.set(m[0] - o[0], m[1] - o[1], m[2] - o[2] + 65); body.userData = {scnDrag: key};
    const nose = new THREE.Mesh(new THREE.ConeGeometry(14, 40, 12), new THREE.MeshBasicMaterial({color: col}));
    const yaw = (m[3] || 0) * Math.PI / 180;
    nose.position.set(m[0] - o[0] + Math.sin(yaw) * 40, m[1] - o[1] + Math.cos(yaw) * 40, m[2] - o[2] + 110); nose.rotation.z = -yaw; nose.userData = {scnDrag: key};
    const tx = scnTextSprite(label, '#' + col.toString(16).padStart(6, '0')); tx.position.set(m[0] - o[0], m[1] - o[1], m[2] - o[2] + 170);
    G.add(body, nose, tx);
  };
  sc.actors.forEach(a => { const m = scnMarkPos(a.key); if (m) pin(a.key, scnName(a), 0xe6b24a, m); });
  const pm = scnMarkPos('player'); if (pm) pin('player', 'Player', 0x5aa7ff, pm);
  sc.actors.forEach(a => (a.moves || []).forEach(mv => { const m = sc.marks[mv.to]; if (m) pin('m:' + mv.to, '🚶 ' + scnMarkLabel(mv.to), 0x9ad46a, m); }));
  sc.vfx.forEach(v => { const m = v.mark && sc.marks[v.mark]; if (m) pin('m:' + v.mark, '✨ ' + ((SCN.fx && SCN.fx.effects || []).find(e => e.model.toLowerCase() === String(v.model).toLowerCase()) || {name: 'effect'}).name, 0xff7a3d, m); });
  const tr = sc.trigger;
  if (tr && tr.kind === 'area' && tr.center){
    const r = tr.radius || 300;
    const ring = new THREE.Mesh(new THREE.RingGeometry(r - 8, r, 64), new THREE.MeshBasicMaterial({color: 0x4fd18b, side: THREE.DoubleSide, transparent: true, opacity: 0.8, depthWrite: false}));
    ring.position.set(tr.center[0] - o[0], tr.center[1] - o[1], (tr.center[2] || 0) - o[2] + 6);
    const hub = new THREE.Mesh(new THREE.CylinderGeometry(30, 30, 12, 20), new THREE.MeshBasicMaterial({color: 0x4fd18b, transparent: true, opacity: 0.6}));
    hub.rotation.x = Math.PI / 2; hub.position.copy(ring.position); hub.userData = {scnDrag: '@area'};
    const tx = scnTextSprite('Starts here', '#4fd18b'); tx.position.set(ring.position.x, ring.position.y, ring.position.z + 60);
    G.add(ring, hub, tx);
  }
  scnSort(sc.shots.slice()).forEach((s, n) => {
    if (!s.pos) return;
    const cone = new THREE.Mesh(new THREE.ConeGeometry(16, 44, 4), new THREE.MeshBasicMaterial({color: 0xb07cff}));
    cone.position.set(s.pos[0] - o[0], s.pos[1] - o[1], s.pos[2] - o[2]);
    const yaw = (s.yaw || 0) * Math.PI / 180, pitch = (s.pitch || 0) * Math.PI / 180;
    const dir = new THREE.Vector3(Math.sin(yaw) * Math.cos(pitch), Math.cos(yaw) * Math.cos(pitch), Math.sin(pitch));
    cone.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
    const tx = scnTextSprite('📷 ' + (n + 1), '#b07cff'); tx.position.set(cone.position.x, cone.position.y, cone.position.z + 40);
    G.add(cone, tx);
  });
  if (SCN.prev) G.visible = false;
  V3.scnGroup = G; V3.scene.add(G);
}
// (the marks stay drawn when the 3D view builds its scene again)
setInterval(() => { if (SCN.ed && typeof V3 !== 'undefined' && V3.on && V3.scene && (!V3.scnGroup || !V3.scene.children.includes(V3.scnGroup))) scnMarks3D(); }, 1500);

function scnDragInit(){
  if (typeof V3 === 'undefined' || !V3.renderer || V3.scnDragOn) return;
  V3.scnDragOn = true;
  const cv = V3.renderer.domElement;
  cv.addEventListener('pointerdown', e => {
    if (!SCN.ed || !V3.scnGroup || e.button !== 0) return;
    const r = cv.getBoundingClientRect(), rc = new THREE.Raycaster();
    rc.setFromCamera(new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1), V3.camera);
    const hit = rc.intersectObjects(V3.scnGroup.children.filter(c => c.userData && c.userData.scnDrag), false)[0];
    if (!hit) return;
    e.stopPropagation(); e.preventDefault();
    const key = hit.object.userData.scnDrag, o = V3.origin || [0, 0, 0], sc = SCN.ed.sc;
    const start = key === '@area' ? sc.trigger.center : scnMarkPos(key);
    const plane = new THREE.Plane(new THREE.Vector3(0, 0, 1), -((start[2] || 0) - o[2]));
    let moved = null;
    const mv = ev => {
      const rc2 = new THREE.Raycaster();
      rc2.setFromCamera(new THREE.Vector2(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1), V3.camera);
      const p = new THREE.Vector3(); if (!rc2.ray.intersectPlane(plane, p)) return;
      moved = [p.x + o[0], p.y + o[1], start[2] || 0];
      scnDragShow(key, moved[0] - start[0], moved[1] - start[1]);
    };
    const up = () => {
      window.removeEventListener('pointermove', mv, true); window.removeEventListener('pointerup', up, true);
      if (!moved) return;
      if (key === '@area'){ sc.trigger.center = [Math.round(moved[0]), Math.round(moved[1]), Math.round(start[2] || 0)]; scnChanged(true); }
      else scnSetMark(key, moved);          // (turned to face the player again, as placing them does)
    };
    window.addEventListener('pointermove', mv, true); window.addEventListener('pointerup', up, true);
  }, true);
}
function scnDragShow(key, dx, dy){
  // (while dragging: the marker drawn where it would go)
  const sc = SCN.ed.sc, base = key === '@area' ? sc.trigger.center : scnMarkPos(key); if (!base) return;
  const save = key === '@area' ? sc.trigger.center : null;
  const tmp = [base[0] + dx, base[1] + dy, base[2] || 0, base[3] || 0];
  if (key === '@area'){ sc.trigger.center = tmp.slice(0, 3); scnMarks3D(); sc.trigger.center = save; }
  else { const name = key.startsWith('m:') ? key.slice(2) : key === 'player' ? sc.player.mark : sc.actors.find(a => a.key === key).mark; const old = sc.marks[name]; sc.marks[name] = tmp; scnMarks3D(); sc.marks[name] = old; }
}

function scnTakeView(s){
  if (typeof V3 === 'undefined' || !V3.on || !V3.pos){ toast('Open the 3D view and frame the shot there first.', true); return false; }
  const o = V3.origin || [0, 0, 0];
  s.pos = [Math.round(V3.pos.x + o[0]), Math.round(V3.pos.y + o[1]), Math.round(V3.pos.z + o[2])];
  s.yaw = Math.round(((V3.yaw * 180 / Math.PI) % 360 + 360) % 360 * 10) / 10;
  s.pitch = Math.round(V3.pitch * 1800 / Math.PI) / 10;
  s.fov = Math.round(V3.fov || (V3.camera && V3.camera.fov) || 60);
  delete s.aim; delete s.offset; delete s.from; delete s.move;
  return true;
}

// where a shot's camera is at time t into the scene: {pos, yaw, pitch, fov} (as the game's scene player does it)
function scnShotCam(s, t){
  const sc = SCN.ed.sc;
  if (s.pos){
    let pos = s.pos;
    if (s.move && s.move.to && s.move.to.pos){ const f = scnEase((t - (s.at || 0)) / Math.max(0.01, s.move.dur || 1), s.move.ease); pos = pos.map((v, i) => v + (s.move.to.pos[i] - v) * f); }
    return {pos, yaw: (s.yaw || 0) * Math.PI / 180, pitch: (s.pitch || 0) * Math.PI / 180, fov: s.fov || 60};
  }
  const tk = (s.aim || {}).actor, t0 = tk && scnStandAt(tk); if (!t0) return null;
  const tp = SCN.ed.people.find(p => tk && sc.actors.find(a => a.key === tk) && scnPerson(sc.actors.find(a => a.key === tk)) === p);
  const head = [t0[0], t0[1], t0[2] + ((tp && tp.type === 'creature') ? 70 : 105)];
  let from;
  if (s.from){
    const f = scnStandAt(s.from.actor || 'player'); if (!f) return null;
    const fy = (f[3] || 0) * Math.PI / 180, side = s.from.shoulder === 'left' ? -1 : 1;
    from = [f[0] + Math.cos(fy) * 28 * side - Math.sin(fy) * 45, f[1] - Math.sin(fy) * 28 * side - Math.cos(fy) * 45, f[2] + 111];
  } else {
    let off = s.offset || [0, 150, 0];
    if (s.move && s.move.to && s.move.to.offset){ const f = scnEase((t - (s.at || 0)) / Math.max(0.01, s.move.dur || 1), s.move.ease); off = off.map((v, i) => v + (s.move.to.offset[i] - v) * f); }
    const ry = (t0[3] || 0) * Math.PI / 180;
    from = [t0[0] + Math.cos(ry) * off[0] + Math.sin(ry) * off[1], t0[1] - Math.sin(ry) * off[0] + Math.cos(ry) * off[1], head[2] + (off[2] || 0)];
  }
  const d = [head[0] - from[0], head[1] - from[1], head[2] - from[2]];
  return {pos: from, yaw: Math.atan2(d[0], d[1]), pitch: Math.atan2(d[2], Math.hypot(d[0], d[1])), fov: s.fov || 40};
}
function scnEase(x, k){ x = Math.max(0, Math.min(1, x)); return k === 'in' ? x * x : k === 'out' ? 1 - (1 - x) * (1 - x) : k === 'linear' ? x : x * x * (3 - 2 * x); }
function scnSetCam(c){
  const o = V3.origin || [0, 0, 0];
  V3.pos = new THREE.Vector3(c.pos[0] - o[0], c.pos[1] - o[1], c.pos[2] - o[2]);
  V3.yaw = c.yaw; V3.pitch = c.pitch;
  if (c.fov && V3.camera){ V3.camera.fov = c.fov; V3.camera.updateProjectionMatrix(); }
  if (typeof v3Loop === 'function') v3Loop();
}
function scnLook(s){
  if (typeof V3 === 'undefined' || !V3.on){ toast('Open the 3D view to see the shot.', true); return; }
  const c = scnShotCam(s, s.at || 0);
  if (!c){ toast(s.from ? 'Put the player on a spot first (right-click a spot › The player stands here).' : 'Who the shot is on isn\'t in this place.', true); return; }
  scnSetCam(c);
}

// ----- ▶ Preview: the shots run in the 3D view, the lines as subtitles
function scnPreview(){
  if (typeof V3 === 'undefined' || !V3.on){ toast('Preview runs in the 3D view: open it first (⧉ Next to the 3D view).', true); return; }
  const E = SCN.ed, sc = E.sc;
  if (!sc.shots.length){ toast('Add a shot first.', true); return; }
  const wrap = document.querySelector('#world .mapwrap');
  let sub = $('#scn-sub');
  if (!sub && wrap){ sub = document.createElement('div'); sub.id = 'scn-sub'; wrap.appendChild(sub); }
  SCN.prev = {t: E.cursor >= (sc.length || 0) ? 0 : E.cursor, last: performance.now(), fov: V3.camera ? V3.camera.fov : null};
  const bars = sc.screen.some(x => x.letterbox != null);
  if (sub) sub.innerHTML = (bars ? '<div class="scn-bar top"></div><div class="scn-bar bot"></div>' : '') + '<div class="scn-subt"></div>';
  const b = $('#scn-prev'); if (b) b.textContent = '■ Stop';
  if (V3.scnGroup) V3.scnGroup.visible = false;          // (the marks hide while it plays)
  const step = now => {
    if (!SCN.prev || !SCN.ed) return;
    SCN.prev.t += Math.min(0.1, (now - SCN.prev.last) / 1000); SCN.prev.last = now;
    const t = SCN.prev.t;
    const shot = scnSort(sc.shots.slice()).filter(s => (s.at || 0) <= t).pop() || scnSort(sc.shots.slice())[0];
    const c = shot && scnShotCam(shot, t); if (c) scnSetCam(c);
    const line = sc.lines.filter(l => (l.at || 0) <= t && t < (l.at || 0) + scnLineLen(l)).pop();
    const st = sub && sub.querySelector('.scn-subt');
    if (st) st.textContent = line ? (line.who === 'player' ? 'You' : scnName(sc.actors.find(a => a.key === (line.who || line.actor)) || {key: line.who})) + ': ' + (line.text || '') : '';
    scnLookPreview(sc, t, sub);
    E.cursor = Math.round(t * 10) / 10; scnTimeline();
    if (t >= (sc.length || 0)) return scnPreviewStop();
    SCN.prev.raf = requestAnimationFrame(step);
  };
  SCN.prev.raf = requestAnimationFrame(step);
}
// the look in the preview, roughly (the game's own shaders do it properly): values blended as the scene player does
function scnLookAt(sc, t){
  const v = {exposure: 0, temperature: 0, saturation: 1, vignette: 0, blur: 0, motionblur: 0};
  scnSort(sc.screen.filter(scnLookKind)).filter(x => (x.at || 0) <= t).forEach(x => {
    const f = x.dur > 0 ? Math.min(1, (t - (x.at || 0)) / x.dur) : 1;
    Object.keys(v).forEach(k => { if (x[k] != null && isFinite(+x[k])) v[k] = v[k] + (+x[k] - v[k]) * f; });
  });
  return v;
}
function scnLookPreview(sc, t, sub){
  if (typeof V3 === 'undefined' || !V3.renderer) return;
  const v = scnLookAt(sc, t), w = v.temperature / 100;
  V3.renderer.domElement.style.filter = `brightness(${Math.pow(2, v.exposure).toFixed(3)}) saturate(${Math.max(0, v.saturation).toFixed(3)})`
    + (w > 0 ? ` sepia(${(w * 0.35).toFixed(3)})` : w < 0 ? ` hue-rotate(${(w * 12).toFixed(1)}deg)` : '')
    + (v.blur > 0 ? ` blur(${(v.blur * 1.5).toFixed(2)}px)` : '');
  if (sub){
    let vg = sub.querySelector('.scn-vig');
    if (!vg){ vg = document.createElement('div'); vg.className = 'scn-vig'; vg.style.cssText = 'position:absolute;left:0;right:0;top:0;bottom:44%;pointer-events:none'; sub.prepend(vg); }
    vg.style.background = v.vignette > 0 ? `radial-gradient(ellipse at center, transparent 45%, rgba(0,0,0,${(v.vignette * 0.85).toFixed(3)}) 100%)` : '';
  }
}
function scnPreviewStop(){
  if (!SCN.prev) return;
  cancelAnimationFrame(SCN.prev.raf);
  if (SCN.prev.fov && typeof V3 !== 'undefined' && V3.camera){ V3.camera.fov = V3.fov || SCN.prev.fov; V3.camera.updateProjectionMatrix(); }
  SCN.prev = null;
  if (typeof V3 !== 'undefined' && V3.renderer) V3.renderer.domElement.style.filter = '';
  if (typeof V3 !== 'undefined' && V3.scnGroup) V3.scnGroup.visible = true;
  const s = $('#scn-sub'); if (s) s.remove();
  const b = $('#scn-prev'); if (b) b.textContent = '▶ Preview';
}

// ----- ▶ Try it: the game started here, and the scene played once it is in
async function scnTry(){
  const E = SCN.ed, sc = E.sc;
  if (E.dirty || E.isNew){ const ok = await scnSave(); if (!ok) return; }
  if (typeof LINK !== 'undefined' && LINK.connected){
    await scnPlay(sc.scene);
    toast('Playing it in the running game. The game has the scene as it was when the game started: after changing it, quit the game and Try it again.');
    return;
  }
  // (where the player starts: their spot in the scene, else by the first person, else where the map is)
  let at = scnMarkPos('player');
  if (!at && sc.actors[0]){ const t = scnStandAt(sc.actors[0].key); if (t){ const ry = (t[3] || 0) * Math.PI / 180; at = [t[0] + Math.sin(ry) * 160, t[1] + Math.cos(ry) * 160, t[2], 0]; } }
  if (!at && sc.trigger && sc.trigger.center) at = sc.trigger.center.concat([0]);
  if (!at) at = [W.cam.x, W.cam.y, (typeof groundZ === 'function' ? groundZ(W.cam.x, W.cam.y) : 0), 0];
  SCN.try = {scene: sc.scene, since: Date.now(), linkedAt: 0};
  await playHere({cell: scnKeyOf(sc.cell), x: at[0], y: at[1], z: at[2] + 30, rz: (at[3] || 0) * Math.PI / 180});
  toast('Starting the game here: the scene plays a few seconds after you arrive.');
}
setInterval(async () => {
  const T = SCN.try; if (!T) return;
  if (Date.now() - T.since > 5 * 60000){ SCN.try = null; return; }
  if (typeof LINK === 'undefined' || !LINK.connected || !LINK.session) return;
  if (!T.linkedAt){ T.linkedAt = Date.now(); return; }
  if (Date.now() - T.linkedAt < 4000) return;
  SCN.try = null;
  await scnPlay(T.scene);
}, 1000);

async function scnPlay(id){
  try { await post('/api/test/cmd', {verb: 'scene', args: [id, '0']}); }
  catch (e){ toast(e.message, true); }
}

// ----- the timeline: what happens when, dragged to retime
function scnTimeline(){
  const box = scnHostEl() && scnHostEl().querySelector('#scn-tl'); if (!box || !SCN.ed) return;
  const sc = SCN.ed.sc, L = Math.max(1, +sc.length || 1);
  const pct = t => Math.max(0, Math.min(100, (t / L) * 100));
  const objs = [];
  const blk = (from, to, text, obj, title, fixed) => { objs.push(obj); return `<div class="scn-blk ${fixed ? 'fixed' : ''}" data-scnb="${objs.length - 1}" title="${esc(title || text)}" style="left:${pct(from)}%;width:${Math.max(1.2, pct(to) - pct(from))}%">${esc(text)}</div>`; };
  const shots = scnSort(sc.shots.slice());
  const rows = [];
  rows.push(['Camera', shots.map((s, i) => blk(s.at || 0, i + 1 < shots.length ? shots[i + 1].at : L,
    s.pos ? '📷 fixed' : (SCN_FRAMES[s.from ? 'shoulder' : Object.keys(SCN_FRAMES).find(k => SCN_FRAMES[k].offset && s.offset && SCN_FRAMES[k].offset.join() === s.offset.join())] || {label: 'aimed'}).label + ' · ' + scnName(sc.actors.find(a => a.key === (s.aim || {}).actor) || {key: (s.aim || {}).actor || ''}),
    s))]);
  sc.actors.forEach(a => {
    const cl = (a.clips || []).slice().sort((x, y) => (x.at || 0) - (y.at || 0));
    rows.push([scnName(a), cl.map((c, n) => {
      const g = (SCN.ed.anims[(scnActorId(a) || '').toLowerCase()] || []).find(g => g.group.toLowerCase() === String(c.group).toLowerCase());
      const end = c.loop ? (n + 1 < cl.length ? cl[n + 1].at : L) : (c.at || 0) + (g ? g.length / (c.speed || 1) : 2);
      return blk(c.at || 0, Math.min(L, end), scnAnimLabel(c.group).split(' · ')[0], c, scnAnimLabel(c.group));
    }).concat(a.appear ? [blk(a.appear.at || 0, (a.appear.at || 0) + 0.8, '➜ comes in', a.appear)] : [],
      (a.moves || []).map(mv => blk(mv.at || 0, (mv.at || 0) + 1.5, '🚶 walks', mv)),
      a.leave ? [blk(a.leave.at || 0, (a.leave.at || 0) + 0.8, a.leave.how === 'die' ? '✝ dies' : '✕ goes', a.leave)] : [])]);
  });
  rows.push(['Lines', scnSort(sc.lines.slice()).map(l => blk(l.at || 0, Math.min(L, (l.at || 0) + scnLineLen(l)), '💬 ' + (l.text || '…'), l,
    scnName(l.who === 'player' ? 'player' : (sc.actors.find(a => a.key === (l.who || l.actor)) || {key: l.who})) + ': ' + (l.text || '')))]);
  if (sc.vfx.length) rows.push(['Effects', sc.vfx.map(v => blk(v.at || 0, v.dur != null ? (v.at || 0) + v.dur : L,
    '✨ ' + ((SCN.fx && SCN.fx.effects || []).find(e => e.model.toLowerCase() === String(v.model).toLowerCase()) || {name: 'effect'}).name.split(' / ')[0], v))]);
  if (sc.world.length) rows.push(['World', sc.world.map(w => blk(w.at || 0, (w.at || 0) + 1, w.weather != null ? '☁ ' + w.weather : w.hour != null ? '🕓 ' + w.hour
    : ((SCN.ed.objects.find(o => scnRefKey(o.ref) === scnRefKey(w.ref)) || {name: 'thing'}).name + ' · ' + (w.do || 'activate')), w))]);
  rows.push(['Screen, sound', sc.screen.map(x => x.shake != null ? blk(x.at || 0, (x.at || 0) + (x.dur || 1), '〰 shake', x) : x.fade ? blk(x.at || 0, (x.at || 0) + (x.dur || 1), 'fade ' + x.fade, x, '', x.fade === 'out')
    : x.movie != null ? blk(x.at || 0, (x.at || 0) + 1.5, '🎞 ' + (x.movie || 'video'), x) : '').join('')
    + sc.sound.map(x => x.music ? blk(x.at || 0, L, '♪ ' + x.music.split('/').pop(), x, '', true) : x.sound != null ? blk(x.at || 0, (x.at || 0) + 1, '🔉 ' + (x.sound || '…'), x) : '').join('')]);
  const looks = sc.screen.filter(scnLookKind);
  if (looks.length) rows.push(['Look', looks.map(x => blk(x.at || 0, (x.at || 0) + Math.max(0.8, x.dur || 0),
    {col: '🎨 colour', dof: '🔍 focus', mb: '💨 blur'}[scnLookKind(x)], x, 'Post-processing: it holds until the next one changes it'))]);
  let ticks = '';
  const stp = L <= 20 ? 1 : L <= 60 ? 5 : 10;
  for (let t = 0; t <= L + 0.001; t += stp) ticks += `<span style="position:absolute;left:${pct(t)}%;font-size:10px;color:var(--muted);transform:translateX(-50%)">${t}</span>`;
  box.innerHTML = `<div class="scn-tlrow" style="height:14px">${ticks}<div class="scn-end" id="scn-end" title="Drag to change the length (${L} s)" style="left:100%"></div></div>` +
    rows.map(([lab, html]) => `<div class="scn-tlrow"><span class="scn-tllab">${esc(lab)}</span>${Array.isArray(html) ? html.join('') : html}</div>`).join('') +
    `<div class="scn-cur" style="left:calc(100px + (100% - 114px) * ${pct(SCN.ed.cursor) / 100})"></div>`;
  SCN.ed.tl = objs;
  box.onpointerdown = e => {
    const row = box.querySelector('.scn-tlrow').getBoundingClientRect();
    const toT = x => Math.max(0, Math.min(L, (x - row.left) / row.width * L));
    if (e.target.id === 'scn-end'){
      e.preventDefault();
      const mv = ev => { sc.length = Math.max(1, Math.round((L * (ev.clientX - row.left) / row.width) * 10) / 10); scnEndFade(); scnTimeline(); };
      const up = () => { window.removeEventListener('pointermove', mv); window.removeEventListener('pointerup', up); scnChanged(true); };
      window.addEventListener('pointermove', mv); window.addEventListener('pointerup', up);
      return;
    }
    const b = e.target.closest('[data-scnb]');
    if (b && !b.classList.contains('fixed')){
      e.preventDefault();
      const obj = SCN.ed.tl[+b.dataset.scnb], t0 = obj.at || 0, x0 = e.clientX;
      let moved = false;
      const mv = ev => { if (Math.abs(ev.clientX - x0) > 3) moved = true; if (!moved) return; obj.at = Math.round(Math.max(0, Math.min(L - 0.1, t0 + (ev.clientX - x0) / row.width * L)) * 10) / 10; scnTimeline(); };
      const up = () => {
        window.removeEventListener('pointermove', mv); window.removeEventListener('pointerup', up);
        if (moved) scnChanged(true);
        else { SCN.ed.cursor = Math.round(t0 * 10) / 10; scnTimeline(); scnGoTo(obj); }
      };
      window.addEventListener('pointermove', mv); window.addEventListener('pointerup', up);
      return;
    }
    if (b) return scnGoTo(SCN.ed.tl[+b.dataset.scnb]);
    SCN.ed.cursor = Math.round(toT(e.clientX) * 10) / 10;
    scnTimeline();
    if (typeof V3 !== 'undefined' && V3.on && !SCN.prev){ const s = scnSort(sc.shots.slice()).filter(s => (s.at || 0) <= SCN.ed.cursor).pop(); const c = s && scnShotCam(s, SCN.ed.cursor); if (c) scnSetCam(c); }
  };
}
function scnGoTo(obj){
  // (the row of what was clicked on the timeline, lit for a moment)
  const sc = SCN.ed.sc, host = scnHostEl();
  let key = null;
  const i = sc.shots.indexOf(obj); if (i >= 0) key = 'shots:' + i;
  const j = sc.lines.indexOf(obj); if (j >= 0) key = 'lines:' + j;
  sc.actors.forEach((a, ai) => { const ci = (a.clips || []).indexOf(obj); if (ci >= 0) key = `clips:${ai}:${ci}`;
    const mi = (a.moves || []).indexOf(obj); if (mi >= 0) key = `moves:${ai}:${mi}`; });
  for (const k of ['vfx', 'world', 'sound', 'screen']){ const n = (sc[k] || []).indexOf(obj); if (n >= 0) key = k + ':' + n; }
  const r = key && host.querySelector(`[data-scnrow="${key}"]`);
  if (r){ r.scrollIntoView({block: 'center'}); r.classList.add('scn-flash'); setTimeout(() => r.classList.remove('scn-flash'), 1200); }
}

// ----- voices: picked from the game's and the Library's sound files; a line lasts as long as its voice
function scnVoicePick(line, anchor){
  document.querySelectorAll('.scn-vpick').forEach(x => x.remove());
  const r = anchor.getBoundingClientRect();
  const box = document.createElement('div'); box.className = 'pmenu scn-vpick';
  box.style.cssText = `position:fixed;left:${Math.min(r.left, innerWidth - 380)}px;top:${Math.min(r.bottom + 4, innerHeight - 340)}px;width:360px;max-height:320px;overflow:auto;padding:6px;z-index:9999`;
  box.innerHTML = '<input class="inp" placeholder="Search voice files: a name, a race, a word…" style="width:100%;box-sizing:border-box"><div class="scn-vlist" style="margin-top:4px"></div>';
  document.body.appendChild(box);
  const inp = box.querySelector('input'), list = box.querySelector('.scn-vlist');
  let tok = 0;
  const find = async () => {
    const my = ++tok;
    try {
      const r2 = await api('/api/sounds/files?q=' + encodeURIComponent(('vo/ ' + inp.value).trim()));
      if (my !== tok) return;
      list.innerHTML = r2.files.map(f => `<button style="display:block;width:100%;text-align:left" data-f="${esc(f)}">${esc(f)}</button>`).join('') || '<div class="msg">No voice files match.</div>';
      list.querySelectorAll('[data-f]').forEach(b => b.onclick = async () => {
        line.voice = 'Sound/' + b.dataset.f; box.remove();
        try { const s = await api('/api/scenes/voicelen?path=' + encodeURIComponent(line.voice)); if (s.secs) line.dur = s.secs; else delete line.dur; } catch (e){}
        scnChanged(true);
      });
    } catch (e){ list.innerHTML = `<div class="msg err">${esc(e.message)}</div>`; }
  };
  inp.oninput = () => { clearTimeout(box._t); box._t = setTimeout(find, 200); };
  inp.focus(); find();
  setTimeout(() => document.addEventListener('pointerdown', function off(ev){ if (!box.contains(ev.target)){ box.remove(); document.removeEventListener('pointerdown', off); } }), 0);
}

async function scnSeeAnim(a, group){
  const p = scnPerson(a);
  if (!p || p.ri == null || typeof anShow !== 'function'){ toast('Their animations can\'t be shown here.', true); return; }
  await anShow(p.ri, p.name + ': ' + scnAnimLabel(group));
  const g = AN.d && AN.d.groups.find(x => x.name.toLowerCase() === String(group).toLowerCase());
  if (g && typeof anPick === 'function') anPick(g);
}

function scnProblems(say){
  const box = scnHostEl() && scnHostEl().querySelector('#scn-probs'), P = SCN.ed && SCN.ed.problems;
  if (!box) return;
  if (!P){ box.innerHTML = ''; return; }
  box.innerHTML = P.length ? `<div class="card" style="margin:6px 0">${P.map(p => `<div class="msg ${p.level === 'error' ? 'sev-error' : 'sev-warning'}">${p.level === 'error' ? '✕' : '!'} ${esc(p.text)}</div>`).join('')}</div>`
    : '<div class="msg" style="margin:6px 0">✓ Nothing found that would stop it playing.</div>';
  if (say && !P.length) toast('Nothing found that would stop it playing.');
}

async function scnSave(){
  const E = SCN.ed, sc = E.sc, msg = scnHostEl().querySelector('#scn-msg');
  if (scnHostEl().querySelector('#scn-kind')) scnTrigger();
  if (sc.trigger && sc.trigger.kind === 'quest' && !sc.trigger.quest){ msg.className = 'msg err'; msg.textContent = 'Give the quest under Starts when.'; return false; }
  try {
    const r = await post('/api/scenes/save', {scene: sc});
    E.problems = r.problems || [];
    if (!r.kept){ scnProblems(); msg.className = 'msg err'; msg.textContent = 'Not kept: see what stops it.'; return false; }
    // (the saved scene back as the Workshop keeps it: a dialogue start now has its global)
    try { E.sc = await api('/api/scenes/get?scene=' + encodeURIComponent(sc.scene)); for (const k of ['actors', 'shots', 'lines', 'sound', 'screen', 'vfx', 'world']) if (!Array.isArray(E.sc[k])) E.sc[k] = []; E.sc.marks = E.sc.marks || {}; E.sc.player = E.sc.player || {}; } catch (e){}
    E.dirty = false; E.isNew = false; afterChange(); toast('Scene kept in your mod. File › Save writes it.');
    await scnMine(); scnRender();
    return true;
  } catch (e){ msg.className = 'msg err'; msg.textContent = e.message; return false; }
}

// ----- the right-click menu on the World map and in 3D
function scnMenu(e, hit, at){
  if (typeof W === 'undefined' || !W.key || W.mode === 'paths' || !(S.summary && S.summary.project)) return [];
  const r = hit && hit[1], pt = {x: e.clientX, y: e.clientY};
  const spot = at || (r && r.p) || null;
  const E = SCN.ed, here = E && scnKeyOf(E.sc.cell) === W.key, out = [];
  const person = r && (r.type === 'NPC_' || r.type === 'CREA');
  if (person){
    const nm = r.name || r.id;
    if (here){
      const p = E.people.find(x => x.k === r.k);
      if (p && !E.sc.actors.some(a => scnPerson(a) === p)) out.push({label: `🎬 Add ${nm} to the scene`, act: () => scnAddPerson(p)});
    }
    out.push({label: `🎬 Scene with ${nm}…`, act: () => scnStartMenu(pt, {person: r.k, spot})});
  } else if (r && r.type === 'DOOR'){
    out.push({label: '🎬 Scene when the player comes through this door', act: () => scnStartMenu(pt, {spot: r.p, door: true, only: 'arrive'})});
  }
  if (spot && !person) out.push({label: '🎬 New scene here…', act: () => scnStartMenu(pt, {spot})});
  if (here && spot && !person){
    E.sc.actors.slice(0, 6).forEach(a => out.push({label: `🎬 ${scnName(a)} stands here`, act: () => scnSetMark(a.key, spot)}));
    out.push({label: '🎬 The player stands here', act: () => scnSetMark('player', spot)});
    E.sc.actors.slice(0, 4).forEach(a => out.push({label: `🎥 Camera here, looking at ${scnName(a)}`, act: () => scnCamHere(spot, a.key)}));
    if (E.sc.trigger && E.sc.trigger.kind === 'area') out.push({label: '🎬 The scene starts here', act: () => { E.sc.trigger.center = spot.map(Math.round); scnChanged(true); }});
    E.sc.actors.slice(0, 4).forEach(a => out.push({label: `🚶 ${scnName(a)} walks here`, act: () => {
      const last = (a.moves || []).slice(-1)[0], from = (last && E.sc.marks[last.to]) || scnStandAt(a.key);
      const name = scnNewMark(a.key + '_w', [spot[0], spot[1], spot[2] || 0, 0], 0);
      if (from) E.sc.marks[name][3] = scnFacing(from, E.sc.marks[name]);
      (a.moves = a.moves || []).push({at: E.cursor || 0, to: name}); scnChanged(true);
    }}));
    out.push({label: '✨ An effect here', act: () => { E.sc.vfx.push({at: E.cursor || 0, mark: scnNewMark('fx', [spot[0], spot[1], spot[2] || 0, 0], 0), model: 'meshes/l/Light_Fire.NIF', loop: true}); scnChanged(true); }});
  }
  return out;
}
// (comfort.js, which has the menu's hook, loads after this file)
(function scnMenuOn(){ if (typeof CF_MENU_MORE !== 'undefined') CF_MENU_MORE.push(scnMenu); else setTimeout(scnMenuOn, 200); })();

// ----- the guided first cutscene (Home › Your first cutscene; coach.js runs it, pointing at the real buttons)
const SCN_TOUR = [
  {skip: () => S.summary && S.summary.project, at: () => $('#projpill'), title: 'First, start a mod',
   text: 'Click here and give it a name. Scenes play in an .omwaddon mod, the kind the Workshop starts.',
   done: () => S.summary && S.summary.project},
  {at: () => $('nav [data-view="world"]'), title: 'Open the World map', text: 'Scenes are made where they happen.',
   done: () => pageOn('world')},
  {at: () => $('#w-goto'), title: 'Go to the place', above: false,
   text: 'Type its name, for example Seyda Neen, and pick it. Somebody should be standing there.',
   done: () => pageOn('world') && W.key && W.cells[W.key]},
  {at: () => $('[data-view3d="1"]'), title: 'See it in 3D', text: 'You frame the shots in the 3D view.', skip: () => V3.on, done: () => V3.on},
  {at: null, title: 'Right-click someone',
   text: 'In the 3D view, right-click a person › 🎬 Scene with… › The player arrives here. The scene maker opens along the bottom, with them in it and a close-up ready.',
   done: () => SCN.ed && SCN.ed.dock},
  {at: () => $('#scn-dock'), title: 'Put them on their spots',
   text: 'Right-click the ground › 🎬 … stands here, then once more › The player stands here. They turn to face each other; drag a marker to move it. Next when they stand right.',
   next: true},
  {at: () => $('#scn-addline'), title: 'What they say',
   text: '+ Line, then type it. 🔊 Voice… picks a voice file from the game; the line then lasts as long as the voice.',
   done: () => SCN.ed && SCN.ed.sc.lines.some(l => (l.text || '').trim())},
  {at: () => $('#scn-addclip'), title: 'What they do', text: '+ Animation: pick one in words (Standing, Fidgets, Walks forward…); ▶ beside it shows it played. Next when you like it.', next: true},
  {at: () => $('#scn-addaim'), title: 'More shots',
   text: '+ Shot on someone gives a close-up, medium or wide shot of them. Or move the 3D view to frame one yourself, then + Shot from the 3D view.', next: true},
  {at: () => $('#scn-tl'), title: 'The timeline', above: true,
   text: 'Every shot, animation and line on a row. Drag a block to move it in time, the end mark to make the scene longer.', next: true},
  {at: () => $('#scn-prev'), title: 'Preview it', text: 'The 3D view runs through the shots with the lines as subtitles. Stop it any time.',
   done: () => !!SCN.prev},
  {at: () => $('#scn-save'), title: 'Keep it', text: 'Save keeps the scene in your mod; Undo takes it back. File › Save writes the mod.',
   done: () => SCN.ed && !SCN.ed.dirty},
  {at: () => $('#scn-try'), title: 'Try it in the game',
   text: 'Starts OpenMW right there and plays the scene a few seconds after you arrive. In the game, Space skips it.', last: true},
];
function coachScene(){ if (typeof coachHouse === 'function') coachHouse(SCN_TOUR); }
