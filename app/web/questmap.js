// ---------- Quests on the map: the quest maker docked under the 3D view ----------
// (questmap.py reads and writes; questmake.py writes each step the way the game writes it.) A quest is its
// stages top to bottom, each with the steps that reach it and a 📍 for where they happen; in 3D the steps are
// numbered pins joined in order, and a spot to reach is a ring on the ground. Right-click starts and grows it
// from where you stand: "Quest that begins here", "Next: talk to…", "Next: take this", "Next: reach this spot".
// Every step adds its stage too, as one Undo.
const QM = {key: null, d: null, list: [], form: null, dock: false};

(function(){
  const st = document.createElement('style');
  st.textContent = `#qm-dock{position:absolute;left:0;right:0;bottom:0;height:44%;z-index:40;background:var(--panel);border-top:2px solid var(--blue,#5aa7ff);
      display:flex;flex-direction:column;box-shadow:0 -6px 18px #0007}
    #qm-dock .qm-bar{display:flex;align-items:center;gap:8px;padding:3px 8px;border-bottom:1px solid var(--line)}
    #qm-dock .qm-grip{cursor:ns-resize;padding:0 10px;font-size:18px;line-height:12px;color:var(--muted)}
    #qm-body{flex:1;overflow:auto;padding:6px 12px 12px}
    .qmk .qm-row{display:flex;gap:6px;align-items:center;flex-wrap:wrap;padding:3px 0}
    .qmk .qm-row .inp{padding:3px 6px} .qmk .qm-row select.inp{width:auto}
    .qmk .qm-cols{display:grid;grid-template-columns:minmax(320px,1.2fr) minmax(300px,1fr);gap:18px}
    .qmk .qm-stage{border-left:3px solid var(--blue,#5aa7ff);padding:4px 0 6px 10px;margin:6px 0}
    .qmk .qm-stage.bad{border-left-color:var(--red)} .qmk .qm-stage.dead{border-left-color:var(--amber)} .qmk .qm-stage.fin{border-left-color:var(--gold)}
    .qmk .qm-num{display:inline-block;min-width:34px;height:24px;line-height:22px;border-radius:12px;border:2px solid var(--blue,#5aa7ff);text-align:center;font-weight:600;font-size:12px}
    .qmk .qm-stage.fin .qm-num{border-color:var(--gold);background:var(--gold);color:var(--deep)}
    .qmk .qm-step{font-size:12.5px;color:var(--muted);padding:2px 0 2px 42px;display:flex;gap:6px;align-items:center;flex-wrap:wrap}
    .qmk .qm-step b{color:var(--text);font-weight:600}
    .qmk .qm-flag{font-size:11.5px;color:var(--amber);padding-left:42px} .qmk .qm-stage.bad .qm-flag{color:var(--red)}
    .qmk .qm-next{display:flex;flex-wrap:wrap;gap:5px}
    .qmk .qm-form{border:1px solid var(--line2);border-radius:8px;padding:8px 10px;margin-top:8px;background:var(--panel2,var(--panel))}
    .qmk .qm-chips{display:flex;flex-wrap:wrap;gap:4px}
    .qmk .qm-chip{border:1px solid var(--line2);border-radius:12px;padding:1px 9px;cursor:pointer;font-size:12px;background:var(--panel)}
    .qmk .qm-chip:hover,.qmk .qm-chip.on{border-color:var(--gold);color:var(--gold2)}
    .qmk .qm-flash{outline:2px solid var(--gold,#b8954a)}
    .qmk .qm-adds{display:none;opacity:.8} .qmk .qm-stage:hover .qm-adds{display:flex}`;
  document.head.appendChild(st);
})();

// what the player does, in words, with its icon (the steps questmake writes)
const QM_VERBS = {
  talk: ['🗣', 'Talk to'], meet: ['👋', 'Meet'], bring: ['🎁', 'Bring to'], show: ['👁', 'Show to'], kill: ['⚔', 'Kill'],
  take: ['✋', 'Take'], read: ['📖', 'Read'], open: ['📦', 'Open'], use: ['⚙', 'Use'], enter: ['🚪', 'Go into'],
  reach: ['📍', 'Reach a spot'], approach: ['🚶', 'Come near'], wait: ['⏳', 'Wait'], after: ['🔗', 'After another quest'],
};
// (the quests worked on lately, newest first, for the picker and the right-click list)
function qmRecent(){ try { return JSON.parse(localStorage.getItem('ws-qm-recent') || '[]'); } catch (e){ return []; } }
function qmRemember(q){
  if (!q || !q.key) return;
  const r = [{key: q.key, title: q.title || q.id, id: q.id}].concat(qmRecent().filter(x => x.key !== q.key)).slice(0, 8);
  try { localStorage.setItem('ws-qm-recent', JSON.stringify(r)); } catch (e){}
}
// (every quest of the load order, read once a mod; ☆ pinned ones kept with the mod)
async function qmEvery(force){
  if (!QM.every || force){ try { const r = await api('/api/quest/every'); QM.every = r.quests; QM.pins = r.pinned; } catch (e){ QM.every = QM.every || []; QM.pins = QM.pins || []; } }
  return QM.every;
}
function qmStepText(s){
  const nm = id => { const c = (QM.d && QM.d.cast || []).find(x => x.id.toLowerCase() === String(id || '').toLowerCase()); return c ? c.name : id; };
  const who = s.whoName || nm(s.who) || (s.carriers || []).map(nm).join(', ');
  const it = (s.items || []).map(nm).join(', ') || (s.takes || []).map(g => nm(g.id)).join(', ');
  switch (s.verb){
    case 'talk': return `Talk to <b>${esc(who)}</b>${s.topic && s.topic !== 'Greeting' ? ` about “${esc(s.topic)}”` : ''}`;
    case 'meet': return `Meet <b>${esc(who)}</b>`;
    case 'bring': return `Bring <b>${esc(it || 'something')}</b> to <b>${esc(who)}</b>`;
    case 'show': return `Show <b>${esc(it || 'something')}</b> to <b>${esc(who)}</b>`;
    case 'kill': return `Kill <b>${esc(who)}</b>`;
    case 'reach': return `Reach a spot <span class="msg">(${Math.round(s.ring.radius)} units round)</span>`;
    case 'enter': return `Go into <b>${esc((s.places || []).join(', ') || 'a place')}</b>`;
    case 'wait': return 'Wait some days';
    case 'after': { const oq = (QM.every || []).find(x => x.key === String(s.after.quest).toLowerCase()); return `When <b>${esc(oq ? oq.title || oq.id : s.after.quest)}</b> reaches stage ${s.after.stage}`; }
    default: return `${esc((QM_VERBS[s.verb] || ['', s.verb])[1])} <b>${esc(who || 'something')}</b>`;
  }
}

// ----- opening, the dock
async function qmList(){ try { QM.list = (await api('/api/quest/mine')).quests || []; } catch (e){ QM.list = []; } return QM.list; }
async function qmOpen(key, form){
  if (typeof needProject === 'function' && !await needProject()) return;
  // (one dock at a time: the scene maker steps aside, asking first if it has changes)
  if (typeof SCN !== 'undefined' && SCN.ed && SCN.ed.dock){ if (typeof scnLeave === 'function' && !scnLeave()) return; }
  if (typeof pageOn === 'function' && !pageOn('world')) showView('world');
  if (typeof V3 !== 'undefined' && !V3.on && typeof v3Enable === 'function') await v3Enable(true);
  await qmList();
  QM.key = key || QM.key || (qmRecent()[0] && qmRecent()[0].key) || (QM.list[0] && QM.list[0].key) || null;
  QM.form = form || null;
  qmDock();
  await qmLoad();
}
async function qmLoad(){
  QM.d = null;
  if (QM.key){ try { QM.d = await api('/api/quest/map?' + new URLSearchParams({key: QM.key, near: W.key || ''})); qmRemember(QM.d.quest); } catch (e){ toast(e.message, true); QM.key = null; } }
  qmDock(); qmRender(); qmMarks3D();
  if (typeof v3Tools === 'function' && typeof V3 !== 'undefined' && V3.on) v3Tools();
}
// (the dock open or closed: the 3D bar's 🧩 button)
function qmToggle(){ if (QM.dock) qmClose(); else qmOpen(QM.key); }
// (another place on the map: the pins found again there; the route redrawn unless a form is being filled)
async function qmRefresh(){
  if (!QM.key) return;
  try { QM.d = await api('/api/quest/map?' + new URLSearchParams({key: QM.key, near: W.key || ''})); } catch (e){ return; }
  if (!QM.form) qmRender();
  qmMarks3D();
}
function qmDock(){
  const wrap = document.querySelector('#world .mapwrap'); if (!wrap) return;
  let d = $('#qm-dock');
  if (!d){
    d = document.createElement('div'); d.id = 'qm-dock';
    d.innerHTML = `<div class="qm-bar"><span class="qm-grip" title="Drag to make it taller or shorter">⋯</span><b>🧩 Quest maker</b>
      <button class="btn sm" id="qm-pick" title="Pick any quest: yours, the game's or another mod's; ☆ pinned and recent first" style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"></button>
      <button class="btn sm" id="qm-star" title="Pin it: ☆ quests are first in the picker and in the right-click menu"></button>
      <button class="btn sm" id="qm-newq" title="A quest of your own: its name, and how it begins">+ New quest</button>
      <span style="flex:1"></span><button class="btn sm" id="qm-board" title="The whole quest on its Board, in Dialogue">🧩 Board</button>
      <button class="btn sm" id="qm-close" title="Close the quest maker">✕</button></div><div id="qm-body"></div>`;
    wrap.appendChild(d);
    const grip = d.querySelector('.qm-grip');
    grip.onpointerdown = ev => {
      ev.preventDefault(); const r0 = wrap.getBoundingClientRect();
      const mv = e2 => { const h = Math.max(140, Math.min(r0.height - 80, r0.bottom - e2.clientY)); d.style.height = h + 'px'; try { localStorage.setItem('ws-qmh', String(h)); } catch (e){} };
      const up = () => { window.removeEventListener('pointermove', mv); window.removeEventListener('pointerup', up); if (typeof v3Resize === 'function') v3Resize(); };
      window.addEventListener('pointermove', mv); window.addEventListener('pointerup', up);
    };
    try { const h = +localStorage.getItem('ws-qmh'); if (h) d.style.height = h + 'px'; } catch (e){}
  }
  const pick = d.querySelector('#qm-pick'), star = d.querySelector('#qm-star');
  pick.textContent = '📜 ' + (QM.d ? (QM.d.quest.title || QM.d.quest.id) : 'Pick a quest') + ' ▾';
  pick.onclick = () => qmPicker(pick, k => { QM.key = k; QM.form = null; qmLoad(); });
  const pinnedNow = QM.key && (QM.pins || []).includes(QM.key);
  star.textContent = pinnedNow ? '★' : '☆'; star.disabled = !QM.key;
  star.onclick = async () => { try { const r = await post('/api/quest/pinmap', {key: QM.key, on: !pinnedNow}); QM.pins = r.pinned; if (QM.every) QM.every.forEach(q => q.pinned = QM.pins.includes(q.key)); qmDock(); } catch (e){ toast(e.message, true); } };
  if (!QM.pins) qmEvery().then(() => qmDock());
  d.querySelector('#qm-newq').onclick = () => { QM.form = {verb: 'talk', fresh: true}; qmRender(); };
  d.querySelector('#qm-board').onclick = () => { if (QM.key && typeof dOpen === 'function'){ showView('dialogue'); dOpen('quest', QM.key); } };
  d.querySelector('#qm-close').onclick = () => qmClose();
  d.style.display = ''; QM.dock = true;
}
// ----- the quest picker: ☆ pinned, recent and your mod's first; typing searches every quest of the load order
async function qmPicker(anchor, onPick, title){
  document.querySelectorAll('.qm-picker').forEach(x => x.remove());
  const r = anchor && anchor.getBoundingClientRect ? anchor.getBoundingClientRect() : {left: anchor.x || 200, bottom: anchor.y || 200};
  const box = document.createElement('div'); box.className = 'pmenu qm-picker';
  box.style.cssText = `position:fixed;left:${Math.min(r.left, innerWidth - 420)}px;top:${Math.min(r.bottom + 4, innerHeight - 380)}px;width:400px;max-height:370px;overflow:auto;padding:6px;z-index:9999`;
  box.innerHTML = `${title ? `<div class="msg" style="padding:2px 4px 6px">${esc(title)}</div>` : ''}<input class="inp" placeholder="Search every quest: a title, an ID, a mod…" style="width:100%;box-sizing:border-box"><div class="qm-plist" style="margin-top:4px"><div class="msg">Reading the quests…</div></div>`;
  document.body.appendChild(box);
  const inp = box.querySelector('input'), list = box.querySelector('.qm-plist');
  inp.focus();
  const all = await qmEvery();
  const byKey = Object.fromEntries(all.map(q => [q.key, q]));
  const row = q => `<div class="qm-prow" data-k="${esc(q.key)}" style="display:flex;gap:6px;align-items:center;padding:3px 4px;border-radius:5px;cursor:pointer">
      <span data-star="${esc(q.key)}" title="Pin it" style="color:var(--gold2);width:16px">${(QM.pins || []).includes(q.key) ? '★' : '☆'}</span>
      <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(q.title || q.id)}</span>
      <small class="msg" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:150px">${esc(q.id)}${q.plugin ? ' · ' + esc(q.plugin) : ''}</small></div>`;
  const head = t => `<div class="msg" style="padding:6px 4px 2px;font-size:11px;letter-spacing:.06em;text-transform:uppercase">${t}</div>`;
  const draw = () => {
    const w = inp.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    let html = '';
    if (!w.length){
      const pins = (QM.pins || []).map(k => byKey[k]).filter(Boolean);
      const rec = qmRecent().map(x => byKey[x.key]).filter(q => q && !pins.includes(q));
      const mine = all.filter(q => q.mine && !pins.includes(q) && !rec.includes(q)).slice(0, 40);
      if (pins.length) html += head('☆ Pinned') + pins.map(row).join('');
      if (rec.length) html += head('Recent') + rec.map(row).join('');
      html += head('Your mod\'s') + (mine.map(row).join('') || '<div class="msg" style="padding:2px 4px">None yet.</div>');
      html += '<div class="msg" style="padding:6px 4px">Type to search every quest: the game\'s and other mods\' too.</div>';
    } else {
      const hits = all.filter(q => w.every(x => (q.title + ' ' + q.id + ' ' + q.plugin).toLowerCase().includes(x))).slice(0, 80);
      html = hits.map(row).join('') || '<div class="msg">No quest matches.</div>';
    }
    list.innerHTML = html;
    list.querySelectorAll('.qm-prow').forEach(el => {
      el.onmouseenter = () => el.style.background = 'var(--hover)'; el.onmouseleave = () => el.style.background = '';
      el.onclick = ev => {
        const st = ev.target.closest('[data-star]');
        if (st){
          const k = st.dataset.star, on = !(QM.pins || []).includes(k);
          post('/api/quest/pinmap', {key: k, on}).then(rr => { QM.pins = rr.pinned; draw(); if (QM.dock) qmDock(); }).catch(e => toast(e.message, true));
          return;
        }
        box.remove(); onPick(el.dataset.k);
      };
    });
  };
  inp.oninput = draw; draw();
  inp.onkeydown = e => { if (e.key === 'Escape') box.remove(); if (e.key === 'Enter'){ const f = list.querySelector('.qm-prow'); if (f) f.click(); } };
  setTimeout(() => document.addEventListener('pointerdown', function off(ev){ if (!box.contains(ev.target)){ box.remove(); document.removeEventListener('pointerdown', off); } }), 0);
}

function qmClose(){
  const d = $('#qm-dock'); if (d) d.style.display = 'none';
  QM.dock = false; QM.form = null;
  if (typeof V3 !== 'undefined' && V3.qmGroup && V3.scene){ V3.scene.remove(V3.qmGroup); V3.qmGroup = null; }
  if (typeof v3Tools === 'function' && typeof V3 !== 'undefined' && V3.on) v3Tools();
}

// ----- the dock's body: the route on the left, what happens next on the right
function qmRender(){
  const body = $('#qm-body'); if (!body) return;
  const d = QM.d;
  const route = !d ? `<p class="msg">${QM.list.length ? 'Pick a quest above, or start one.' : 'No quest yet.'} Right-click someone in 3D › 🧩 Quest given by…, or the ground › 🧩 Quest that begins here…, or + New quest.</p>`
    : `<div class="qm-row" style="gap:10px"><h3 style="margin:0">${esc(d.quest.title || d.quest.id)}</h3><span class="msg">${esc(d.quest.id)}</span></div>
       ${!d.quest.own && d.quest.plugin ? (/\.esm$/i.test(d.quest.plugin)
         ? `<div class="msg" style="margin:2px 0 6px" title="Steps you add here go into your mod, as changes to this quest">A quest of ${esc(d.quest.plugin)}: what you add here goes into your mod.</div>`
         : `<div class="msg sev-warning" style="margin:2px 0 6px" title="Your mod changes this quest: it adds stages and lines to it. Players need your mod loaded after ${esc(d.quest.plugin)}.">⚠ A quest of ${esc(d.quest.plugin)}: your mod continues it, so load it after ${esc(d.quest.plugin)}.</div>`) : ''}
       ${d.route && d.route.length ? `<div class="qm-row" style="font-size:12.5px"><span class="msg">Where:</span>${d.route.map((p, i) => `<button class="btn sm ${p.cell === W.key ? 'primary' : ''}" data-qmplace="${i}" title="Stage ${p.stage}">📍 ${esc(String(p.name).replace(/\s*\(-?\d+, -?\d+\)$/, ''))}</button>${i < d.route.length - 1 ? '<span class="msg">›</span>' : ''}`).join('')}
         ${d.route.length > 1 ? '<button class="btn sm" id="qm-nextplace" title="The next place this quest goes to">Next place ›</button>' : ''}</div>` : ''}
       ${d.stages.length ? '' : '<p class="msg">No stages yet.</p>'}
       ${d.stages.map(s => qmStageRow(s)).join('')}`;
  body.innerHTML = `<div class="qmk"><div class="qm-cols"><div>${route}</div><div>${qmNextPane()}</div></div></div>`;
  qmBind();
}
function qmStageRow(s){
  const d = QM.d, steps = d.steps.filter(t => t.sets.includes(s.index));
  const cls = s.finished ? 'fin' : !s.reachable ? 'bad' : s.deadend ? 'dead' : '';
  return `<div class="qm-stage ${cls}" data-qmst="${s.index}"><div class="qm-row"><span class="qm-num">${s.index}</span>
      <input class="inp" data-qmtext="${s.index}" value="${esc(s.text)}" placeholder="What the player writes in their journal here" style="flex:1;min-width:200px">
      <label title="The quest is finished at this stage"><input type="checkbox" data-qmfin="${s.index}" ${s.finished ? 'checked' : ''}> ends it</label></div>
    ${steps.map(t => `<div class="qm-step">${(QM_VERBS[t.verb] || ['•'])[0]} ${qmStepText(t)}
      ${(t.pins || []).slice(0, 2).map((p, i) => `<button class="btn sm" data-qmgo="${t.n}:${i}" title="${esc(p.name)}">📍${p.cell === W.key ? '' : ' ' + esc(String(p.name).split(',')[0])}</button>`).join('')}
      ${t.ring ? `<button class="btn sm" data-qmring="${t.n}" title="Where the player must come (drag its middle in 3D to move it)">📍</button>
        <input class="inp" data-qmrad="${t.ring.to}" value="${Math.round(t.ring.radius)}" style="width:52px;padding:1px 4px" title="How near the player must come, in units (Enter to keep)">` : ''}
      ${t.mine ? `<button class="btn sm" data-qmrm="${t.n}" title="Take this step out (the stage stays; Undo puts it back)">✕</button>` : ''}</div>`).join('')}
    ${!s.reachable ? `<div class="qm-flag">⚠ Nothing leads here yet: add a step that reaches it${steps.length ? '' : `, or <a href="#" data-qmrmst="${s.index}">take the stage out</a>`}.</div>` : s.deadend ? '<div class="qm-flag">⛔ Nothing leads on from here.</div>' : ''}
    <div class="qm-step qm-adds"><button class="btn sm" data-qmway="${s.index}" title="Another way the player can reach this stage">＋ way here</button>
      <button class="btn sm" data-qmfork="${s.index}" title="A step that starts from this stage: for a quest that forks here">＋ from here</button></div></div>`;
}
function qmNextPane(){
  const f = QM.form;
  const verbs = ['talk', 'bring', 'show', 'kill', 'take', 'read', 'open', 'use', 'enter', 'reach', 'wait', 'after'];
  return `<h3 style="margin:2px 0 6px">${f && f.fresh ? 'A new quest' : QM.d ? 'What happens next?' : 'Start a quest'}</h3>
    ${f ? qmForm(f) : `<div class="qm-next">${verbs.map(v => `<button class="btn sm" data-qmverb="${v}" ${QM.d ? '' : 'disabled'}>${QM_VERBS[v][0]} ${QM_VERBS[v][1]}${['talk', 'bring', 'show', 'kill', 'take', 'read', 'open', 'use'].includes(v) ? '…' : ''}</button>`).join('')}</div>
      <p class="msg" style="margin-top:8px">Or right-click in 3D: a person › 🧩 Next: talk to…, a thing › 🧩 Next: take it, the ground › 🧩 Next: reach this spot.</p>`}`;
}

// ----- the form for a step: who, what, the words, the journal line of the stage it reaches
function qmForm(f){
  const v = f.verb, last = QM.d && QM.d.stages.length ? Math.max(...QM.d.stages.map(s => s.index)) : 0;
  const person = ['talk', 'meet', 'bring', 'show', 'kill', 'approach'].includes(v), thing = ['take', 'read', 'open', 'use'].includes(v);
  const people = (QM.near || []).filter(p => p.type === 'npc' || p.type === 'creature');
  return `<div class="qm-form">
    ${f.fresh ? `<div class="qm-row"><label>Quest</label><input class="inp" id="qmf-title" value="${esc(f.title || '')}" placeholder="Its title in the journal, e.g. A Ring for Fargoth" style="flex:1">
      </div><div class="qm-row"><label title="Players never see it: letters, numbers and _">ID</label><input class="inp" id="qmf-id" value="${esc(f.id || '')}" placeholder="made from the title" style="width:200px"></div>
      <div class="qm-row"><label>It begins</label><select class="inp" id="qmf-verb">${['talk', 'meet', 'take', 'read', 'reach', 'enter', 'after'].map(x => `<option value="${x}" ${x === v ? 'selected' : ''}>${QM_VERBS[x][0]} ${x === 'after' ? 'after another quest' : 'when the player ' + QM_VERBS[x][1].toLowerCase()}</option>`).join('')}</select></div>`
      : `<div class="qm-row"><select class="inp" id="qmf-verb" title="What the player does">${Object.keys(QM_VERBS).filter(x => x !== 'meet' && x !== 'approach').map(x => `<option value="${x}" ${x === v ? 'selected' : ''}>${QM_VERBS[x][0]} ${QM_VERBS[x][1]}</option>`).join('')}</select>
        <span class="msg">reaches stage</span><input class="inp" id="qmf-index" value="${f.index || last + 10}" style="width:56px">
        <span class="msg">from</span><select class="inp" id="qmf-from">${(QM.d ? QM.d.stages : []).map(s => `<option value="${s.index}" ${s.index === (f.from != null ? f.from : last) ? 'selected' : ''}>stage ${s.index}</option>`).join('') || '<option value="0">the start</option>'}</select></div>`}
    ${v === 'after' ? `<div class="qm-row"><label>When</label><button class="btn sm" id="qmf-oq" title="The other quest">${esc(f.oqTitle || f.oq || 'pick a quest…')}</button>
      <label>reaches</label><select class="inp" id="qmf-ostage">${(f.ostages || []).map(s => `<option value="${s.index}" ${+f.ostage === s.index ? 'selected' : ''}>stage ${s.index}${s.text ? ': ' + esc(s.text.slice(0, 40)) : ''}</option>`).join('') || '<option value="">—</option>'}</select></div>` : ''}
    ${person ? `<div class="qm-row"><label>${v === 'kill' ? 'Who dies' : 'Who'}</label><input class="inp" id="qmf-who" value="${esc(f.who || '')}" list="qmf-dl-who" placeholder="Search people and creatures" style="width:220px">
        <datalist id="qmf-dl-who"></datalist>${f.whoName ? `<span class="msg">${esc(f.whoName)}</span>` : ''}</div>
      ${people.length ? `<div class="qm-chips" title="People here">${people.slice(0, 12).map(p => `<span class="qm-chip" data-qmwho="${esc(p.id)}">${esc(p.name)}</span>`).join('')}</div>` : ''}` : ''}
    ${thing ? `<div class="qm-row"><label title="${f.placeAt ? 'Placed on the spot you right-clicked when you add the step' : ''}">${f.placeAt ? 'Put here' : 'What'}</label><input class="inp" id="qmf-thing" value="${esc(f.thing || '')}" list="qmf-dl-thing" placeholder="Search items, books, containers…" style="width:220px"><datalist id="qmf-dl-thing"></datalist>
      ${f.thingName ? `<span class="msg">${esc(f.thingName)}</span>` : ''}</div>` : ''}
    ${['talk', 'bring', 'show'].includes(v) ? `<div class="qm-row"><label title="The words the player clicks in the conversation">Topic</label><input class="inp" id="qmf-topic" value="${esc(f.topic || '')}" placeholder="e.g. lost ring" style="width:200px"></div>` : ''}
    ${['bring', 'show'].includes(v) ? `<div class="qm-row"><label>Item</label><input class="inp" id="qmf-item" value="${esc(f.item || '')}" list="qmf-dl-item" placeholder="Search items" style="width:200px"><datalist id="qmf-dl-item"></datalist>
      × <input class="inp" id="qmf-n" value="1" style="width:44px"></div>` : ''}
    ${['talk', 'meet', 'bring', 'show'].includes(v) ? `<div class="qm-row"><label>They say</label><input class="inp" id="qmf-say" value="${esc(f.say || '')}" placeholder="What they answer" style="flex:1"></div>
      <div class="qm-row"><label>Reward</label><input class="inp" id="qmf-give" list="qmf-dl-give" placeholder="an item, or gold_001" style="width:170px"><datalist id="qmf-dl-give"></datalist>
        × <input class="inp" id="qmf-given" value="1" style="width:56px"></div>` : ''}
    ${v === 'reach' ? `<div class="qm-row">${f.spot ? `<span class="msg">📍 ${Math.round(f.spot[0])}, ${Math.round(f.spot[1])}</span>` : '<span class="msg">📍 the middle of the 3D view (or right-click the ground › Next: reach this spot)</span>'}
      <label>within</label><input class="inp" id="qmf-radius" value="${f.radius || 300}" style="width:60px"> units</div>` : ''}
    ${v === 'enter' ? `<div class="qm-row"><label>Place</label><input class="inp" id="qmf-place" value="${esc(f.place || '')}" list="qmf-dl-place" placeholder="an interior's name, or its start (Balmora)" style="width:240px"><datalist id="qmf-dl-place"></datalist></div>` : ''}
    ${v === 'wait' ? `<div class="qm-row"><label>Days</label><input class="inp" id="qmf-days" value="1" style="width:50px"></div>` : ''}
    <div class="qm-row"><label>Journal</label><input class="inp" id="qmf-text" value="${esc(f.text || '')}" placeholder="What the player writes in their journal then" style="flex:1"></div>
    ${f.fresh ? '' : '<div class="qm-row"><label><input type="checkbox" id="qmf-fin"> the quest ends here</label></div>'}
    <div class="qm-row"><button class="btn primary sm" id="qmf-ok">${f.fresh ? 'Begin the quest' : 'Add this step'}</button><button class="btn sm" id="qmf-no">Cancel</button><span class="msg" id="qmf-msg"></span></div></div>`;
}

// (search fields: people, items, places, filled as you type)
function qmSearch(inp, dl, types){
  if (!inp) return;
  let t = 0;
  inp.addEventListener('input', () => { clearTimeout(t); t = setTimeout(async () => {
    const qq = inp.value.trim(); if (qq.length < 2) return;
    try {
      const r = await api('/api/search?' + new URLSearchParams({q: qq, types, limit: 30}));
      dl.innerHTML = r.rows.map(x => `<option value="${esc(x.id)}">${esc(x.name || x.id)}</option>`).join('');
    } catch (e){}
  }, 220); });
}

function qmBind(){
  const body = $('#qm-body'), q = id => body.querySelector('#' + id);
  body.querySelectorAll('[data-qmverb]').forEach(b => b.onclick = () => { QM.form = {verb: b.dataset.qmverb}; qmRender(); });
  body.querySelectorAll('[data-qmplace]').forEach(b => b.onclick = () => qmGo(QM.d.route[+b.dataset.qmplace]));
  const np = q('qm-nextplace');
  if (np) np.onclick = () => {
    // (the place after the one on the map, in the order of the stages; round to the first after the last)
    const rt = QM.d.route, i = rt.findIndex(p => p.cell === W.key);
    qmGo(rt[(i + 1) % rt.length]);
  };
  body.querySelectorAll('[data-qmgo]').forEach(b => b.onclick = () => { const [n, i] = b.dataset.qmgo.split(':'); const t = QM.d.steps.find(s => s.n === +n); qmGo(t.pins[+i]); });
  body.querySelectorAll('[data-qmring]').forEach(b => b.onclick = () => { const t = QM.d.steps.find(s => s.n === +b.dataset.qmring); qmGo({cell: t.ring.cell, pos: t.ring.center}); });
  body.querySelectorAll('[data-qmtext]').forEach(el => el.onchange = () => qmStageEdit(+el.dataset.qmtext, {text: el.value}));
  body.querySelectorAll('[data-qmfin]').forEach(el => el.onchange = () => qmStageEdit(+el.dataset.qmfin, {finished: el.checked}));
  // (a step taken out, a stage nothing reaches taken out, a ring resized; each one Undo)
  body.querySelectorAll('[data-qmrm]').forEach(b => b.onclick = () => qmChange('/api/quest/unstep', {key: QM.key, step: QM.d.steps.find(s => s.n === +b.dataset.qmrm)}, 'Step taken out: Undo puts it back.'));
  body.querySelectorAll('[data-qmrmst]').forEach(a => a.onclick = ev => { ev.preventDefault(); qmChange('/api/quest/unstage', {key: QM.key, index: +a.dataset.qmrmst}, 'Stage taken out: Undo puts it back.'); });
  body.querySelectorAll('[data-qmrad]').forEach(el => el.onkeydown = ev => { if (ev.key === 'Enter') qmChange('/api/quest/ring', {key: QM.key, to: +el.dataset.qmrad, radius: +el.value}, 'Ring resized.'); });
  // (another way to a stage, or a fork from one: the form with its stages set)
  const before = i => { const st = QM.d.stages.map(s => s.index).filter(x => x < i); return st.length ? st[st.length - 1] : 0; };
  body.querySelectorAll('[data-qmway]').forEach(b => b.onclick = () => { const i = +b.dataset.qmway; QM.form = {verb: 'talk', index: i, from: before(i), text: (QM.d.stages.find(s => s.index === i) || {}).text}; qmRender(); });
  body.querySelectorAll('[data-qmfork]').forEach(b => b.onclick = () => {
    // (a fork's own stage: the next free ten after the last, so the numbers stay tidy)
    const i = +b.dataset.qmfork, n = Math.floor(Math.max(...QM.d.stages.map(s => s.index)) / 10) * 10 + 10;
    QM.form = {verb: 'talk', from: i, index: n}; qmRender();
  });
  body.querySelectorAll('[data-qmwho]').forEach(c => c.onclick = () => { const w = q('qmf-who'); if (w){ w.value = c.dataset.qmwho; body.querySelectorAll('[data-qmwho]').forEach(x => x.classList.toggle('on', x === c)); } });
  if (!QM.form) return;
  qmSearch(q('qmf-who'), q('qmf-dl-who'), 'NPC_,CREA');
  qmSearch(q('qmf-thing'), q('qmf-dl-thing'), 'MISC,BOOK,WEAP,ARMO,CLOT,ALCH,INGR,CONT,ACTI,LIGH,APPA');
  qmSearch(q('qmf-item'), q('qmf-dl-item'), 'MISC,BOOK,WEAP,ARMO,CLOT,ALCH,INGR,APPA,LIGH');
  qmSearch(q('qmf-give'), q('qmf-dl-give'), 'MISC,BOOK,WEAP,ARMO,CLOT,ALCH,INGR,APPA,LIGH');
  qmSearch(q('qmf-place'), q('qmf-dl-place'), 'CELL');
  const fv = q('qmf-verb'); if (fv) fv.onchange = () => { QM.form = Object.assign(qmRead(), {verb: fv.value}); qmRender(); };
  const oq = q('qmf-oq');
  if (oq) oq.onclick = () => qmPicker(oq, async k => {
    // (the other quest: its stages to pick from)
    const f = qmRead();
    try { const d2 = await api('/api/dlg/quest?' + new URLSearchParams({key: k})); Object.assign(f, {oq: d2.id, oqTitle: d2.title || d2.id, ostages: d2.stages, ostage: (d2.stages[d2.stages.length - 1] || {}).index}); }
    catch (e){ toast(e.message, true); return; }
    QM.form = f; qmRender();
  }, 'When which quest reaches a stage?');
  const tt = q('qmf-title'), idf = q('qmf-id');
  if (tt && idf) tt.oninput = () => { if (!idf.dataset.typed) idf.value = tt.value.replace(/[^A-Za-z0-9]+/g, '_').replace(/^_|_$/g, '').slice(0, 28); };
  if (idf) idf.oninput = () => { idf.dataset.typed = '1'; };
  if (tt && !QM.form.title) tt.focus();
  q('qmf-no').onclick = () => { QM.form = null; qmRender(); };
  q('qmf-ok').onclick = () => qmWrite();
  if (QM.nearFor !== W.key) qmNear();
}
// (what is in the form now, so changing the kind of step keeps what was typed)
function qmRead(){
  const body = $('#qm-body'), val = id => { const el = body.querySelector('#' + id); return el ? el.value.trim() : undefined; };
  return Object.assign({}, QM.form, {title: val('qmf-title'), id: val('qmf-id'), who: val('qmf-who'), thing: val('qmf-thing'), topic: val('qmf-topic'),
    item: val('qmf-item'), say: val('qmf-say'), text: val('qmf-text'), place: val('qmf-place'), radius: val('qmf-radius'),
    index: val('qmf-index') !== undefined ? +val('qmf-index') : QM.form.index, from: val('qmf-from') !== undefined ? +val('qmf-from') : QM.form.from,
    ostage: val('qmf-ostage') !== undefined ? val('qmf-ostage') : QM.form.ostage});
}
async function qmNear(){
  // (the people of the place on the map, as chips to pick from)
  if (!W.key) return;
  QM.nearFor = W.key;
  try { QM.near = (await api('/api/scenes/actors?cell=' + encodeURIComponent(W.key.startsWith('#') ? JSON.stringify(W.key.slice(1).split(',').map(Number)) : W.key))).actors || []; } catch (e){ QM.near = []; }
  if (QM.form) qmRender();
}

async function qmWrite(){
  const f = qmRead(), body = $('#qm-body'), msg = body.querySelector('#qmf-msg'), v = f.verb;
  const num = id => { const el = body.querySelector('#' + id); return el ? +el.value || 0 : 0; };
  const mv = {verb: v, who: f.who || '', thing: f.thing || '', topic: f.topic || '', say: f.say || ''};
  if (['bring', 'show'].includes(v)) mv.items = [{id: f.item || '', n: num('qmf-n') || 1}];
  const give = body.querySelector('#qmf-give'); if (give && give.value.trim()) mv.gives = [{id: give.value.trim(), n: num('qmf-given') || 1}];
  if (v === 'enter') mv.place = f.place || '';
  if (v === 'wait') mv.days = num('qmf-days') || 1;
  if (v === 'after'){
    if (!f.oq || f.ostage === '' || f.ostage == null){ msg.className = 'msg err'; msg.textContent = 'Pick the other quest and its stage.'; return; }
    mv.quest = f.oq; mv.stage = +f.ostage;
  }
  if (v === 'reach'){
    let spot = f.spot;
    if (!spot && typeof V3 !== 'undefined' && V3.on && V3.pos && typeof v3Dir === 'function'){ const dd = v3Dir(), o = V3.origin; spot = [V3.pos.x + o[0] + dd.x * 500, V3.pos.y + o[1] + dd.y * 500, V3.pos.z + o[2] - 150]; }
    if (!spot){ msg.className = 'msg err'; msg.textContent = 'Right-click the ground › Next: reach this spot.'; return; }
    mv.center = spot.map(Math.round); mv.radius = +f.radius || 300; mv.cell = f.cell || (typeof cellKeyAt === 'function' && W.key && W.key.startsWith('#') ? cellKeyAt(spot[0], spot[1]) : W.key);
  }
  if (['talk', 'bring', 'show'].includes(v) && !mv.topic) mv.topic = (f.title || (QM.d && QM.d.quest.title) || 'work').toLowerCase().slice(0, 30);
  const req = f.fresh ? {new: {id: f.id || (f.title || '').replace(/[^A-Za-z0-9]+/g, '_'), title: f.title || f.id}, text: f.text || '', move: mv}
    : {key: QM.key, index: num('qmf-index'), from: num('qmf-from'), text: f.text || '', finished: !!(body.querySelector('#qmf-fin') || {}).checked, move: mv};
  const ok = body.querySelector('#qmf-ok'); ok.disabled = true;
  try {
    // (an item to put on the spot: placed with the step, the two one Undo)
    if (f.placeAt && mv.thing) req.place = {id: mv.thing, pos: f.placeAt, cell: typeof cellKeyAt === 'function' && W.key.startsWith('#') ? cellKeyAt(f.placeAt[0], f.placeAt[1]) : W.key};
    const r = await post('/api/quest/step', req);
    if (req.place && typeof worldReloadCell === 'function') worldReloadCell(req.place.cell);
    QM.key = r.key; QM.form = null;
    await qmList(); qmDock(); await qmLoad();
    if (typeof afterChange === 'function') afterChange();
    toast(f.fresh ? 'Quest begun: Undo takes it back.' : `Stage ${r.index} added: Undo takes it back.`);
  } catch (e){ ok.disabled = false; msg.className = 'msg err'; msg.textContent = e.message; }
}

async function qmChange(path, body, note){
  try { await post(path, body); if (typeof afterChange === 'function') afterChange(); await qmLoad(); toast(note); }
  catch (e){ toast(e.message, true); }
}

async function qmStageEdit(index, change){
  const d = QM.d; if (!d) return;
  try {
    const q = await api('/api/dlg/quest?' + new URLSearchParams({key: d.quest.key}));
    const stages = q.stages.map(s => Object.assign({}, s, s.index === index ? change : {}));
    await post('/api/dlg/quest/save', {id: q.id, title: q.title, stages});
    if (typeof afterChange === 'function') afterChange();
    await qmLoad();
  } catch (e){ toast(e.message, true); }
}

// (the 3D view goes to a step: its cell opened, the view on the spot)
async function qmGo(p){
  if (!p) return;
  if (p.cell !== W.key && typeof worldOpen === 'function') await worldOpen(p.cell);
  if (p.pos && typeof V3 !== 'undefined' && V3.on && typeof v3Focus === 'function'){ v3Focus({k: null, p: p.pos}); if (typeof v3Loop === 'function') v3Loop(); }
  qmMarks3D();
}

// ----- the 3D view: numbered pins where the steps happen, joined in order; a ring round a spot to reach
function qmMarks3D(){
  if (typeof V3 === 'undefined' || !V3.scene || typeof THREE === 'undefined') return;
  if (V3.qmGroup){ V3.scene.remove(V3.qmGroup); V3.qmGroup = null; }
  const d = QM.d; if (!d || !QM.dock || !V3.on) return;
  const o = V3.origin || [0, 0, 0], G = new THREE.Group(), here = [];
  const col = 0x5aa7ff;
  for (const t of d.steps){
    const stage = t.sets[0];
    for (const p of (t.pins || [])){
      if (p.cell !== W.key) continue;
      here.push([stage, p.pos]);
      const body = new THREE.Mesh(new THREE.CylinderGeometry(6, 6, 170, 8), new THREE.MeshBasicMaterial({color: col}));
      body.rotation.x = Math.PI / 2; body.position.set(p.pos[0] - o[0], p.pos[1] - o[1], p.pos[2] - o[2] + 85);
      const head = new THREE.Mesh(new THREE.SphereGeometry(18, 12, 10), new THREE.MeshBasicMaterial({color: col}));
      head.position.set(p.pos[0] - o[0], p.pos[1] - o[1], p.pos[2] - o[2] + 180); head.userData = {qmStage: stage};
      const tx = typeof scnTextSprite === 'function' ? scnTextSprite(stage + ' · ' + (QM_VERBS[t.verb] || ['', t.verb])[1].toLowerCase(), '#7dbbff') : null;
      if (tx){ tx.position.set(head.position.x, head.position.y, head.position.z + 45); G.add(tx); }
      G.add(body, head);
    }
    if (t.ring && t.ring.cell === W.key){
      const c = t.ring.center, r = t.ring.radius;
      here.push([stage, c]);
      const ring = new THREE.Mesh(new THREE.RingGeometry(r - 10, r, 64), new THREE.MeshBasicMaterial({color: col, side: THREE.DoubleSide, transparent: true, opacity: 0.8, depthWrite: false}));
      ring.position.set(c[0] - o[0], c[1] - o[1], c[2] - o[2] + 6);
      const hub = new THREE.Mesh(new THREE.CylinderGeometry(26, 26, 10, 20), new THREE.MeshBasicMaterial({color: col, transparent: true, opacity: 0.7}));
      hub.rotation.x = Math.PI / 2; hub.position.copy(ring.position); hub.userData = {qmStage: stage, qmRing: t.ring.to}; ring.userData = {qmRingOf: t.ring.to};
      G.add(ring, hub);
      if (typeof scnTextSprite === 'function'){ const tx = scnTextSprite(stage + ' · reach here', '#7dbbff'); tx.position.set(ring.position.x, ring.position.y, ring.position.z + 60); G.add(tx); }
    }
  }
  // (the route: the steps here joined in the order of their stages)
  here.sort((a, b) => a[0] - b[0]);
  if (here.length > 1){
    const pts = here.map(([, p]) => new THREE.Vector3(p[0] - o[0], p[1] - o[1], p[2] - o[2] + 40));
    const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineDashedMaterial({color: col, dashSize: 40, gapSize: 25, transparent: true, opacity: 0.85}));
    line.computeLineDistances(); G.add(line);
  }
  V3.qmGroup = G; V3.scene.add(G);
  qmDragInit();
  if (typeof v3Loop === 'function') v3Loop();
}
// (a ring dragged by its middle: moved where it is let go, its step written again, one Undo)
function qmDragInit(){
  if (typeof V3 === 'undefined' || !V3.renderer || V3.qmDragOn) return;
  V3.qmDragOn = true;
  const cv = V3.renderer.domElement;
  cv.addEventListener('pointerdown', e => {
    if (!QM.dock || !V3.qmGroup || e.button !== 0) return;
    const r = cv.getBoundingClientRect(), rc = new THREE.Raycaster();
    const at = ev => new THREE.Vector2(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
    rc.setFromCamera(at(e), V3.camera);
    const hit = rc.intersectObjects(V3.qmGroup.children.filter(c => c.userData && c.userData.qmRing != null), false)[0];
    if (!hit) return;
    e.stopPropagation(); e.preventDefault();
    const to = hit.object.userData.qmRing, hub = hit.object, o = V3.origin || [0, 0, 0];
    const ring = V3.qmGroup.children.find(c => c.userData && c.userData.qmRingOf === to);
    const plane = new THREE.Plane(new THREE.Vector3(0, 0, 1), -hub.position.z);
    let moved = null;
    const mv = ev => {
      const rc2 = new THREE.Raycaster(); rc2.setFromCamera(at(ev), V3.camera);
      const p = new THREE.Vector3(); if (!rc2.ray.intersectPlane(plane, p)) return;
      hub.position.x = p.x; hub.position.y = p.y; if (ring){ ring.position.x = p.x; ring.position.y = p.y; }
      moved = [p.x + o[0], p.y + o[1], p.z + o[2] - 6];      // (the hub sits 6 above the ring's ground)
      if (typeof v3Loop === 'function') v3Loop();
    };
    const up = () => {
      window.removeEventListener('pointermove', mv, true); window.removeEventListener('pointerup', up, true);
      if (moved) qmChange('/api/quest/ring', {key: QM.key, to, center: moved.map(Math.round)}, 'Spot moved: Undo puts it back.');
    };
    window.addEventListener('pointermove', mv, true); window.addEventListener('pointerup', up, true);
  }, true);
}

// (kept drawn when the 3D view builds its scene again, or another place opens)
setInterval(() => {
  if (!QM.dock || typeof V3 === 'undefined' || !V3.on || !V3.scene) return;
  if (QM.drawnFor !== W.key){ QM.drawnFor = W.key; qmRefresh(); return; }
  if (!V3.qmGroup || !V3.scene.children.includes(V3.qmGroup)) qmMarks3D();
}, 1500);

// ----- the right-click menu: start a quest here, or add the next step from what was clicked
function qmMenu(e, hit, at){
  if (typeof W === 'undefined' || !W.key || !(S.summary && S.summary.project)) return [];
  const r = hit && hit[1], out = [];
  const spot = at || (r && r.p) || null;
  // (the quest being worked on, dock open or not: "Next:" adds to it; "Next step of…" picks another)
  const open = !!QM.key;
  const cur = open ? ((QM.d && QM.d.quest.key === QM.key && (QM.d.quest.title || QM.d.quest.id)) || ((qmRecent().find(x => x.key === QM.key) || {}).title) || QM.key) : '';
  const nm = r ? (r.name || r.id) : '';
  const next = (label, form) => out.push({label: '🧩 ' + label + ' (' + String(cur).slice(0, 28) + ')', act: () => qmOpen(QM.key, form)});
  const fresh = (label, form) => out.push({label: '🧩 ' + label, act: () => qmOpen(QM.key, Object.assign({fresh: true}, form))});
  // (what a step from this thing would be, for the quest picked from "Next step of…")
  let guess = null;
  if (r && (r.type === 'NPC_' || r.type === 'CREA')) guess = {verb: 'talk', who: r.id, whoName: nm};
  else if (r && ['MISC', 'BOOK', 'WEAP', 'ARMO', 'CLOT', 'ALCH', 'INGR', 'APPA', 'LIGH', 'CONT', 'ACTI'].includes(r.type))
    guess = {verb: r.type === 'BOOK' ? 'read' : r.type === 'CONT' ? 'open' : r.type === 'ACTI' ? 'use' : 'take', thing: r.id, thingName: nm};
  else if (r && r.type === 'DOOR' && r.to && r.to.cell) guess = {verb: 'enter', place: r.to.cell};
  else if (spot && !r){ const ck = typeof cellKeyAt === 'function' && W.key.startsWith('#') ? cellKeyAt(spot[0], spot[1]) : W.key; guess = {verb: 'reach', spot: spot.slice(0, 3), cell: ck}; }
  if (guess) out.push({label: open ? '🧩 Next step of another quest…' : '🧩 Next step of a quest…', act: () => {
    const pt = {x: e.clientX, y: e.clientY};
    qmPicker(pt, k => qmOpen(k, Object.assign({}, guess)), `Which quest goes on here? (${nm || 'this spot'})`);
  }});
  if (r && (r.type === 'NPC_' || r.type === 'CREA')){
    if (open){
      next(`Next: talk to ${nm}`, {verb: 'talk', who: r.id, whoName: nm});
      next(`Next: bring something to ${nm}`, {verb: 'bring', who: r.id, whoName: nm});
      next(`Next: kill ${nm}`, {verb: 'kill', who: r.id, whoName: nm});
    }
    fresh(`Quest given by ${nm}…`, {verb: 'talk', who: r.id, whoName: nm});
  } else if (r && ['MISC', 'BOOK', 'WEAP', 'ARMO', 'CLOT', 'ALCH', 'INGR', 'APPA', 'LIGH', 'CONT', 'ACTI'].includes(r.type)){
    const v = r.type === 'BOOK' ? 'read' : r.type === 'CONT' ? 'open' : r.type === 'ACTI' ? 'use' : 'take';
    if (open) next(`Next: ${QM_VERBS[v][1].toLowerCase()} ${nm}`, {verb: v, thing: r.id, thingName: nm});
    fresh(`Quest that begins when the player ${v === 'take' ? 'finds' : v + 's'} ${nm}…`, {verb: v, thing: r.id, thingName: nm});
  } else if (r && r.type === 'DOOR' && r.to && r.to.cell){
    if (open) next(`Next: go into ${r.to.cell}`, {verb: 'enter', place: r.to.cell});
  }
  if (spot && !(r && ['NPC_', 'CREA'].includes(r.type))){
    const ck = typeof cellKeyAt === 'function' && W.key.startsWith('#') ? cellKeyAt(spot[0], spot[1]) : W.key;
    if (open) next('Next: reach this spot', {verb: 'reach', spot: spot.slice(0, 3), cell: ck});
    if (!r) fresh('Quest that begins here…', {verb: 'reach', spot: spot.slice(0, 3), cell: ck});
    if (open && !r) out.push({label: '🧩 Put a quest item here…', act: () => qmItemHere(spot)});
  }
  return out;
}
(function qmMenuOn(){ if (typeof CF_MENU_MORE !== 'undefined') CF_MENU_MORE.push(qmMenu); else setTimeout(qmMenuOn, 200); })();

// ----- the ways in: the 3D bar's 🧩 (named for the quest being worked on), a quest's page in Dialogue, Ctrl+K
function qmBarLabel(){
  if (!QM.key) return 'Quests';
  const t = (QM.d && QM.d.quest.key === QM.key && (QM.d.quest.title || QM.d.quest.id)) || ((qmRecent().find(x => x.key === QM.key) || {}).title) || QM.key;
  return t.length > 22 ? t.slice(0, 21) + '…' : t;
}
document.addEventListener('click', e => {
  const b = e.target.closest && e.target.closest('[data-qonmap]');
  if (b){ e.preventDefault(); qmOpen(b.dataset.qonmap); }
});
(function qmCmdOn(){
  if (typeof CF_ACT === 'undefined'){ setTimeout(qmCmdOn, 200); return; }
  CF_ACT.push({id: 'questmaker', label: '🧩 Quest maker on the map', keys: [], world: true, run: () => qmOpen(QM.key)});
  CF_ACT.push({id: 'questpick', label: '🧩 Work on a quest on the map…', keys: [], world: true, run: () => qmOpen(QM.key).then(() => { const p = $('#qm-pick'); if (p) p.click(); })});
})();

// (an item to be placed on the spot when the step is added: the step is to take it)
function qmItemHere(spot){ qmOpen(QM.key, {verb: 'take', placeAt: spot.slice(0, 3)}); }
