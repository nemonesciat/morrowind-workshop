// ---------- Conversations: the conversation map, the "What would they say?" tester and a quest's flow ----------
// (convo.py does the reading; this draws it.) The tester keeps one state of the game across
// characters, the way a playthrough does: quest stages you reach talking to one person count for the next.
const CV = {tab: 'lines', scope: 'own', zoom: 1, follow: true, log: [], for: null, last: null, qtab: 'stages',
  state: {race: 'Dark Elf', sex: 0, faction: '', rank: 0, level: 1, talked: false, disposition: null,
          quests: {}, globals: {}, items: {}, dead: {}, locals: {}, values: {}, choice: null}};

(function cvStyle(){
  const st = document.createElement('style');
  st.textContent = `
.cvtabs{display:flex;gap:4px;margin:10px 0 4px;flex-wrap:wrap}
.cvtabs button{background:none;border:1px solid var(--line2);border-radius:16px;color:var(--muted);padding:4px 13px;font:inherit;font-size:13px;cursor:pointer}
.cvtabs button.on{border-color:var(--gold);color:var(--gold2);background:var(--panel2)}
.dwrap.cvwide{max-width:none}
.cvbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:10px 0}
.cvbar .seg{display:flex;border:1px solid var(--line2);border-radius:8px;overflow:hidden}
.cvbar .seg button{background:none;border:0;border-right:1px solid var(--line2);color:var(--muted);padding:4px 10px;font:inherit;font-size:12.5px;cursor:pointer}
.cvbar .seg button:last-child{border-right:0}
.cvbar .seg button.on{background:var(--panel2);color:var(--gold2)}
.cvlegend{display:flex;gap:12px;flex-wrap:wrap;font-size:12px;color:var(--muted)}
.cvlegend i{display:inline-block;width:18px;height:0;border-top:2px solid;vertical-align:middle;margin-right:4px}
.cvcanvas{position:relative;overflow:auto;border:1px solid var(--line);border-radius:10px;background:var(--deep);height:calc(100vh - 290px);min-height:360px;cursor:grab}
.cvcanvas.drag{cursor:grabbing;user-select:none}
.cvsizer{position:relative}
.cvinner{position:absolute;left:0;top:0;transform-origin:0 0;padding:18px;user-select:none}
.cvinner .cvbox,.cvinner .qcard{box-shadow:0 2px 10px rgba(0,0,0,.35)}
.cvedges{position:absolute;left:0;top:0;pointer-events:none;overflow:visible}
.cvedges path{fill:none;stroke-width:1.4;opacity:.55}
.cvedges path.link{stroke:var(--muted)} .cvedges path.learn{stroke:var(--blue)} .cvedges path.set{stroke:var(--gold);stroke-width:1.8;opacity:.75}
.cvedges path.need{stroke:var(--green);stroke-dasharray:5 4;opacity:0}
.cvedges path.dim{opacity:.07} .cvedges path.hot{opacity:1;stroke-width:2.4}
.cvcols{display:flex;gap:110px;align-items:flex-start}
.cvcol{display:flex;flex-direction:column;gap:14px;width:290px;flex:none}
.cvcolh{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--faint);margin-bottom:-4px}
.cvbox{border:1px solid var(--line2);border-radius:9px;background:var(--panel);overflow:hidden;cursor:default}
.cvbox.t2{border-color:var(--goldline)} .cvbox.quest{border-color:var(--goldline);background:var(--panel2)}
.cvbox.ghost{opacity:.75;border-style:dashed}
.cvbh{padding:6px 10px;background:var(--panel2);border-bottom:1px solid var(--line);font-size:13px;font-weight:600;cursor:pointer;display:flex;justify-content:space-between;gap:8px}
.cvbh small{font-weight:400;color:var(--faint);white-space:nowrap}
.cvbox.ghost .cvbh{border-bottom:0;font-weight:500}
.cvrow{padding:6px 10px 6px 12px;border-bottom:1px solid var(--line0);font-size:12.5px;line-height:1.4;cursor:pointer;position:relative}
.cvrow:last-child{border-bottom:0}
.cvrow:hover,.cvrow.hot{background:var(--hover)}
.cvrow::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px}
.cvrow.own::before{background:var(--gold)} .cvrow.group::before{background:var(--blue)} .cvrow.all::before{background:var(--line2)}
.cvrow .cvt{display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.cvrow.mine .cvt{color:var(--text-c)}
.cvchips{display:flex;flex-wrap:wrap;gap:3px;margin-top:3px}
.cvchips span{font-size:10.5px;border:1px solid var(--line2);border-radius:8px;padding:0 6px;color:var(--muted);white-space:nowrap}
.cvchips .need{border-color:var(--green);color:var(--green)} .cvchips .set{border-color:var(--goldline);color:var(--gold2)}
.cvchips .warn{border-color:var(--amber);color:var(--amber)}
.cvst{padding:5px 10px;border-bottom:1px solid var(--line0);font-size:12px;line-height:1.35;cursor:pointer}
.cvst:last-child{border-bottom:0} .cvst b{color:var(--gold2);margin-right:4px} .cvst:hover,.cvst.hot{background:var(--hover)}
.cvtest{display:grid;grid-template-columns:290px minmax(0,1fr);gap:14px;margin-top:8px;align-items:start}
.cvstate{border:1px solid var(--line);border-radius:10px;background:var(--panel);padding:10px 12px;max-height:calc(100vh - 250px);overflow:auto;font-size:12.5px}
.cvstate h4{margin:12px 0 6px;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--faint)}
.cvstate h4:first-child{margin-top:0}
.cvf{display:grid;grid-template-columns:minmax(0,1fr) 112px;gap:6px;align-items:center;margin-bottom:5px}
.cvf > span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cvf .inp{padding:3px 6px;font-size:12px}
.cvwin{display:grid;grid-template-columns:minmax(0,1fr) 210px;border:1px solid var(--goldline);border-radius:10px;background:var(--panel);min-height:420px;max-height:calc(100vh - 250px);overflow:hidden}
.cvlog{padding:12px 16px;overflow:auto;border-right:1px solid var(--line)}
.cvtopics{overflow:auto;padding:8px 6px}
.cvtopics button{display:block;width:100%;text-align:left;background:none;border:0;border-radius:5px;color:var(--text);padding:3px 8px;font:inherit;font-size:13px;cursor:pointer}
.cvtopics button:hover{background:var(--hover);color:var(--gold2)}
.cvtopics button.own{font-weight:600} .cvtopics button.maybe{color:var(--amber)}
.cvtopics .h{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--faint);padding:8px 8px 2px}
.cvsaid{margin-bottom:14px}
.cvsaid .tn{font-family:Cinzel,serif;color:var(--gold2);font-size:14px;margin-bottom:2px}
.cvsaid .tx{font-size:14px;line-height:1.55;white-space:pre-wrap}
.cvsaid .tx a{color:var(--blue);cursor:pointer;text-decoration:none} .cvsaid .tx a:hover{text-decoration:underline}
.cvsaid .fx{display:flex;flex-wrap:wrap;gap:4px;margin-top:4px}
.cvsaid .fx span{font-size:11.5px;border:1px solid var(--goldline);color:var(--gold2);border-radius:9px;padding:0 7px}
.cvsaid .why{font-size:11.5px;color:var(--faint);cursor:pointer;margin-top:3px;display:inline-block}
.cvsaid .why:hover{color:var(--gold2)}
.cvsaid .none{color:var(--faint);font-style:italic}
.cvchoice{display:flex;flex-direction:column;gap:3px;margin-top:6px}
.cvchoice button{text-align:left;background:none;border:0;color:var(--blue);font:inherit;font-size:13.5px;cursor:pointer;padding:0}
.cvchoice button:hover{color:var(--gold2)}
.cvwhy{margin-top:14px}
.cvwl{border:1px solid var(--line);border-radius:8px;padding:7px 10px;margin-top:6px;background:var(--panel);font-size:13px}
.cvwl.said{border-color:var(--gold);box-shadow:0 0 0 1px var(--gold) inset}
.cvwl.skip{opacity:.62} .cvwl.maybe{border-color:var(--amber)}
.cvwl .wtop{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}
.cvwl .tag{font-size:11px;white-space:nowrap;color:var(--faint)} .cvwl.said .tag{color:var(--gold2)} .cvwl.maybe .tag{color:var(--amber)}
.cvwl .dchip.mb{border-color:var(--amber);color:var(--amber)} .cvwl .dchip.mb::before{content:"? "}
.qflow{display:grid;gap:10px 60px;align-items:start;position:relative}
.qflow .qh{position:sticky;top:0;z-index:2;background:var(--panel2);border:1px solid var(--goldline);border-radius:8px;padding:6px 9px;font-size:12px;line-height:1.35}
.qflow .qh b{color:var(--gold2)} .qflow .qh.fin b::after{content:" ✓ finished";color:var(--green);font-weight:400}
.qflow .qwho{font-size:12.5px;font-weight:600;color:var(--blue);padding-top:8px;cursor:pointer}
.qflow .qcell{display:flex;flex-direction:column;gap:8px}
.qcard{border:1px solid var(--line2);border-radius:8px;background:var(--panel);padding:6px 9px;font-size:12.5px;line-height:1.4;cursor:pointer}
.qcard:hover,.qcard.hot{background:var(--hover)} .qcard.mine{border-left:3px solid var(--gold)}
.qcard .qt{font-size:11px;color:var(--faint)} .qcard .cvt{display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
@media (max-width:900px){.cvtest{grid-template-columns:1fr}.cvwin{grid-template-columns:1fr}.cvlog{border-right:0;border-bottom:1px solid var(--line)}}`;
  document.head.appendChild(st);
})();

function cvTabs(){
  return `<div class="cvtabs">${[['lines', '💬 Their own lines'], ['build', '🌳 Write a conversation'], ['map', '🗺 Conversation map'], ['test', '🎭 What would they say?']]
    .map(([k, t]) => `<button data-cvtab="${k}" class="${CV.tab === k ? 'on' : ''}">${t}</button>`).join('')}</div>`;
}
function cvBindTabs(c){
  $('#dmain').querySelectorAll('[data-cvtab]').forEach(b => b.onclick = () => {
    if (CV.tab === 'build' && b.dataset.cvtab !== 'build' && CB.dirty && !confirm('Leave this conversation without saving it?')) return;
    if (b.dataset.cvtab !== 'build') CB.dirty = false;
    CV.tab = b.dataset.cvtab; dRenderNpc();
  });
}
function cvRender(c){
  if (CV.for !== c.id){ CV.for = c.id; CV.log = []; CV.last = null; CV.state.disposition = null; CV.state.locals = {}; CV.cell = null; }
  if (CV.tab === 'map') cvMap(c); else if (CV.tab === 'build') cbOpen(c); else cvTest(c);
}
const cvShortQ = q => q.length > 22 ? q.slice(0, 21) + '…' : q;
const cvOp = op => ({'=': '=', '!=': '≠', '>': '>', '>=': '≥', '<': '<', '<=': '≤'}[op] || op);

// open one line in the line editor (the map and the tester only carry what they show)
async function cvEditLine(topic, inam){
  try {
    const keys = topic === 'greeting' ? Array.from({length: 10}, (_, n) => 'greeting ' + n) : [topic];
    for (const k of keys){
      const t = await api('/api/dlg/topic?key=' + encodeURIComponent(k)).catch(() => null);
      const l = t && t.lines.find(x => x.inam === inam);
      if (l) return dEditLine(k, l);
    }
    toast('That line is no longer there.', true);
  } catch (e){ toast(e.message, true); }
}

// ---------------------------------------------------------------- the conversation map
async function cvMap(c){
  const box = $('#cvbody');
  box.innerHTML = '<div class="msg" style="padding:20px"><span class="spin"></span>Reading everything they can say…</div>';
  let m;
  try { m = await api('/api/convo/map?' + new URLSearchParams({id: c.id, scope: CV.scope})); }
  catch (e){ box.innerHTML = `<div class="msg err">${esc(e.message)}</div>`; return; }
  if (CV.for !== c.id || CV.tab !== 'map') return;
  CV.map = m;
  const n = m.counts, real = m.boxes.filter(b => !b.ghost);
  const scopes = [['own', `Just theirs (${n.own})`], ['group', `+ their kind (${n.group})`], ['all', `+ everyone (${n.all})`]];
  let h = `<div class="cvbar"><div class="seg">${scopes.map(([k, t]) => `<button data-scope="${k}" class="${CV.scope === k ? 'on' : ''}" title="${{own: 'Lines written for this character alone', group: 'Also lines for their race, class, faction, place or script', all: 'Also the lines anyone can say'}[k]}">${t}</button>`).join('')}</div>
    <div class="seg"><button data-zoom="-1" title="Smaller">−</button><button data-zoom="0" title="Actual size">${Math.round(CV.zoom * 100)}%</button><button data-zoom="1" title="Larger">+</button></div>
    <button class="btn sm" id="cv-tidy" title="Put every box back where the map first laid it (drag a box by its title to move it)">↺ Tidy up</button>
    <div class="cvlegend"><span><i style="border-color:var(--muted)"></i>mentions a topic</span><span><i style="border-color:var(--blue)"></i>adds a topic</span>
      <span><i style="border-color:var(--gold)"></i>moves a quest on</span><span><i style="border-color:var(--green);border-top-style:dashed"></i>needs a quest stage (point at a line)</span></div></div>`;
  if (!real.length){
    box.innerHTML = h + `<div class="card msg" style="line-height:1.7">${CV.scope === 'own' ? `${esc(c.name || c.id)} has no lines written just for them. Try <b>+ their kind</b> or <b>+ everyone</b> to see what they say as one of their race, class or faction.` : 'Nothing to show.'}</div>`;
    cvBindMapBar(c); return;
  }
  // columns: the greeting first, then each topic as far along as the first line that leads to it
  const by = Object.fromEntries(m.boxes.map(b => [b.key, b]));
  const depth = {}, order = {}; let ord = 0;
  const queue = [];
  const start = by.greeting ? ['greeting'] : [];
  for (const k of start){ depth[k] = 0; order[k] = ord++; queue.push(k); }
  while (queue.length){
    const k = queue.shift(), d = depth[k];
    for (const r of by[k].lines) for (const t of [...r.links, ...r.fx.learns]){
      if (by[t] && depth[t] === undefined){ depth[t] = Math.min(d + 1, 4); order[t] = ord++; queue.push(t); }
    }
  }
  const cols = [];
  for (const b of m.boxes){
    let d = depth[b.key];
    if (d === undefined) d = b.ghost ? 1 : 'rest';
    b._col = d;
  }
  const maxd = Math.max(0, ...m.boxes.map(b => typeof b._col === 'number' ? b._col : 0));
  const colKeys = [...Array(maxd + 1).keys()];
  if (m.boxes.some(b => b._col === 'rest')) colKeys.push('rest');
  for (const ck of colKeys){
    const bs = m.boxes.filter(b => b._col === ck).sort((a, b) => (order[a.key] ?? 1e9) - (order[b.key] ?? 1e9) || a.id.localeCompare(b.id));
    if (bs.length) cols.push({key: ck, boxes: bs});
  }
  const colTitle = k => k === 0 ? 'When you talk to them' : k === 'rest' ? 'Other topics they talk about' : k === 1 ? 'What that leads to' : 'Further on';
  const chip = r => {
    const out = [];
    for (const nd of r.needs) out.push(`<span class="need" title="Only when the quest is at this stage">📜 ${esc(cvShortQ(nd.quest))} ${cvOp(nd.op)} ${nd.value}</span>`);
    if (r.answer != null) out.push(`<span title="Said when the player picks answer ${r.answer}">↳ answer ${r.answer}</span>`);
    for (const s of r.fx.sets) out.push(`<span class="set" title="Moves the quest on">→ ${esc(cvShortQ(s.quest))} ${s.stage}</span>`);
    if (r.fx.choices.length) out.push(`<span title="${esc(r.fx.choices.map(x => x.n + ': ' + x.label).join('\n'))}">offers ${r.fx.choices.length} choices</span>`);
    for (const g of r.fx.gives) out.push(`<span title="Gives the player">+ ${g.n} ${esc(g.id)}</span>`);
    for (const g of r.fx.takes) out.push(`<span title="Takes from the player">− ${g.n} ${esc(g.id)}</span>`);
    if (r.fx.disp) out.push(`<span>disposition ${r.fx.disp.set ? '= ' : (r.fx.disp.n >= 0 ? '+' : '')}${r.fx.disp.n}</span>`);
    for (const f of r.fx.faction) out.push(`<span>${esc(f)}</span>`);
    if (r.fx.bye) out.push(`<span>ends the talk</span>`);
    if (r.other) out.push(`<span title="Other conditions: open the line to see them">+${r.other} other test${r.other > 1 ? 's' : ''}</span>`);
    if (r.shadow != null) out.push(`<span class="warn" title="A line above it in this topic always wins, so they never say this one">⚠ never said</span>`);
    return out.length ? `<div class="cvchips">${out.join('')}</div>` : '';
  };
  const boxHtml = b => b.ghost
    ? `<div class="cvbox ghost" data-box="${esc(b.key)}"><div class="cvbh" data-bopen="${esc(b.key)}" title="${b.theirs ? `They have ${b.n} line(s) here, from a wider group than shown` : 'They have nothing to say about it; others may'}">💬 ${esc(b.id)} <small>${b.theirs ? b.n + ' wider' : 'not theirs'}</small></div></div>`
    : `<div class="cvbox t${b.type}" data-box="${esc(b.key)}"><div class="cvbh" data-bopen="${esc(b.key)}">${D_ICON[b.type] || '💬'} ${esc(b.id)} <small>${b.lines.length}${b.n > b.lines.length ? ' of ' + b.n : ''} line${b.n > 1 ? 's' : ''}</small></div>
      ${b.lines.map(r => `<div class="cvrow ${r.tier} ${r.mine ? 'mine' : ''}" data-row="${esc(b.key)}|${esc(r.inam)}" data-topic="${esc(r.topic)}" title="${esc(r.src)} · click to open">
        <div class="cvt">${esc(r.text) || '<i class="msg">(no text)</i>'}</div>${chip(r)}</div>`).join('')}</div>`;
  h += `<div class="cvcanvas" id="cv-canvas"><div class="cvsizer" id="cv-sizer"><div class="cvinner" id="cv-inner" style="transform:scale(${CV.zoom})"><svg class="cvedges" id="cv-edges"></svg><div class="cvcols">
    ${cols.map(col => `<div class="cvcol"><div class="cvcolh">${colTitle(col.key)}</div>${col.boxes.map(boxHtml).join('')}</div>`).join('')}
    ${m.quests.length ? `<div class="cvcol"><div class="cvcolh">Quests</div>${m.quests.map(q => `<div class="cvbox quest" data-quest="${esc(q.key)}"><div class="cvbh" data-qopen="${esc(q.key)}">📜 ${esc(q.title || q.id)} <small>${esc(q.id)}</small></div>
      ${q.stages.map(s => `<div class="cvst" data-st="${esc(q.key)}|${s.index}" title="${esc(s.text)}"><b>${s.index}</b>${esc(s.text.slice(0, 90))}${s.finished ? ' ✓' : ''}</div>`).join('') || '<div class="cvst msg">No stages</div>'}</div>`).join('')}</div>` : ''}
  </div></div></div></div>`;
  box.innerHTML = h;
  cvBindMapBar(c);
  const inner = $('#cv-inner');
  const saveKey = 'cvmap:' + c.id.toLowerCase() + '|' + CV.scope;
  cvDraggable(inner, [...inner.querySelectorAll('[data-box],[data-quest]')].map(el => ({el, key: el.dataset.box || 'q:' + el.dataset.quest, handle: el.firstElementChild})),
              () => cvEdges(m), saveKey);
  cvEdges(m);
  const tidy = $('#cv-tidy'); if (tidy) tidy.onclick = () => { try { localStorage.removeItem(saveKey); } catch (e){} cvMap(c); };
  inner.querySelectorAll('[data-row]').forEach(el => {
    el.onclick = () => cvEditLine(el.dataset.topic, el.dataset.row.split('|').slice(1).join('|'));
    el.onmouseenter = () => cvHot(el.dataset.row, null);
    el.onmouseleave = () => cvHot(null, null);
  });
  inner.querySelectorAll('[data-st]').forEach(el => {
    el.onmouseenter = () => cvHot(null, el.dataset.st);
    el.onmouseleave = () => cvHot(null, null);
    el.onclick = () => dOpen('quest', el.dataset.st.split('|')[0]);
  });
  inner.querySelectorAll('[data-bopen]').forEach(el => el.onclick = () => {
    const k = el.dataset.bopen;
    if (k === 'greeting') return;           // (greetings are several topics: open them from the list)
    dOpen('topic', k);
  });
  inner.querySelectorAll('[data-qopen]').forEach(el => el.onclick = () => dOpen('quest', el.dataset.qopen));
  cvPan($('#cv-canvas'));
}
function cvBindMapBar(c, root){
  root = root || $('#cvbody');
  root.querySelectorAll('[data-scope]').forEach(b => b.onclick = () => { CV.scope = b.dataset.scope; cvMap(c); });
  root.querySelectorAll('[data-zoom]').forEach(b => b.onclick = () => {
    const z = +b.dataset.zoom;
    CV.zoom = z === 0 ? 1 : Math.max(0.3, Math.min(1.6, +(CV.zoom * (z > 0 ? 1.2 : 1 / 1.2)).toFixed(2)));
    const inner = $('#cv-inner'); if (!inner) return;
    inner.style.transform = `scale(${CV.zoom})`; cvSize();
    b.closest('.seg').querySelector('[data-zoom="0"]').textContent = Math.round(CV.zoom * 100) + '%';
  });
}
function cvSize(){
  const inner = $('#cv-inner'), sizer = $('#cv-sizer'); if (!inner || !sizer) return;
  sizer.style.width = inner.offsetWidth * CV.zoom + 'px'; sizer.style.height = inner.offsetHeight * CV.zoom + 'px';
}
// boxes you can drag about: they leave the layout for where they stand, follow the mouse (the arrows
// with them), and stay where you put them for next time (this browser only; ↺ Tidy up forgets it)
function cvDraggable(inner, items, redraw, saveKey){
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(saveKey) || '{}') || {}; } catch (e){ saved = {}; }
  const pos = items.map(it => cvPos(it.el, inner));
  const W = inner.scrollWidth, H = inner.scrollHeight;
  items.forEach((it, n) => {
    const p = saved[it.key] || [pos[n].x, pos[n].y];
    Object.assign(it.el.style, {position: 'absolute', left: p[0] + 'px', top: p[1] + 'px', width: pos[n].w + 'px', margin: '0'});
  });
  const fit = () => {
    let w = W, h = H;
    for (const it of items){ w = Math.max(w, it.el.offsetLeft + it.el.offsetWidth + 40); h = Math.max(h, it.el.offsetTop + it.el.offsetHeight + 40); }
    inner.style.width = w + 'px'; inner.style.height = h + 'px'; cvSize();
  };
  fit();
  let z = 5;
  for (const it of items){
    const hd = it.handle || it.el;
    hd.style.cursor = 'move';
    hd.addEventListener('pointerdown', e => {
      if (e.button !== 0) return;
      e.stopPropagation();
      const sx = e.clientX, sy = e.clientY, ox = it.el.offsetLeft, oy = it.el.offsetTop;
      let moved = false, raf = 0;
      it.el.style.zIndex = ++z;
      const mv = ev => {
        const dx = (ev.clientX - sx) / CV.zoom, dy = (ev.clientY - sy) / CV.zoom;
        if (!moved && Math.abs(dx) + Math.abs(dy) < 5) return;
        moved = true;
        it.el.style.left = Math.max(0, ox + dx) + 'px'; it.el.style.top = Math.max(0, oy + dy) + 'px';
        if (!raf) raf = requestAnimationFrame(() => { raf = 0; redraw(); });
      };
      const up = () => {
        window.removeEventListener('pointermove', mv); window.removeEventListener('pointerup', up);
        if (!moved) return;
        saved[it.key] = [it.el.offsetLeft, it.el.offsetTop];
        try { localStorage.setItem(saveKey, JSON.stringify(saved)); } catch (e){}
        fit(); redraw();
        // (a drag isn't a click: the box's own click, opening it, waits for a real one)
        const stop = ce => { ce.stopPropagation(); ce.preventDefault(); };
        hd.addEventListener('click', stop, true);
        setTimeout(() => hd.removeEventListener('click', stop, true), 0);
      };
      window.addEventListener('pointermove', mv); window.addEventListener('pointerup', up);
    });
  }
}
// where an element sits inside the map, before the zoom
function cvPos(el, inner){
  let x = 0, y = 0, e = el;
  while (e && e !== inner){ x += e.offsetLeft; y += e.offsetTop; e = e.offsetParent; }
  return {x, y, w: el.offsetWidth, h: el.offsetHeight};
}
function cvEdges(m){
  const inner = $('#cv-inner'), svg = $('#cv-edges'); if (!inner || !svg) return;
  const W = inner.scrollWidth, H = inner.scrollHeight;
  svg.setAttribute('width', W); svg.setAttribute('height', H);
  const boxEl = {}, stEl = {}, qEl = {};
  inner.querySelectorAll('[data-box]').forEach(el => boxEl[el.dataset.box] = el);
  inner.querySelectorAll('[data-st]').forEach(el => stEl[el.dataset.st] = el);
  inner.querySelectorAll('[data-quest]').forEach(el => qEl[el.dataset.quest] = el);
  const paths = [];
  const curve = (a, b, cls, row, st) => {
    const x1 = a.x + a.w, y1 = a.y + Math.min(a.h / 2, 16), x2 = b.x, y2 = b.y + Math.min(b.h / 2, 14);
    let d;
    if (x2 > x1 + 10){ const dx = Math.max(40, (x2 - x1) / 2); d = `M${x1},${y1} C${x1 + dx},${y1} ${x2 - dx},${y2} ${x2},${y2}`; }
    else { const out = 46; d = `M${x1},${y1} C${x1 + out},${y1} ${x1 + out},${y2 - 30} ${(x1 + x2) / 2},${Math.min(y1, y2) - 30} S${x2 - out},${y2} ${x2},${y2}`; }
    paths.push(`<path class="${cls}" d="${d}" data-er="${esc(row)}"${st ? ` data-es="${esc(st)}"` : ''}/>`);
  };
  for (const b of m.boxes) for (const r of b.lines){
    const rowKey = b.key + '|' + r.inam, el = inner.querySelector(`[data-row="${CSS.escape(rowKey)}"]`); if (!el) continue;
    const a = cvPos(el, inner);
    const seen = new Set();
    for (const t of r.fx.learns) if (boxEl[t] && !seen.has(t)){ seen.add(t); curve(a, cvPos(boxEl[t].firstElementChild, inner), 'learn', rowKey); }
    for (const t of r.links) if (boxEl[t] && !seen.has(t)){ seen.add(t); curve(a, cvPos(boxEl[t].firstElementChild, inner), 'link', rowKey); }
    for (const s of r.fx.sets){
      const k = s.quest + '|' + s.stage, tgt = stEl[k] || (qEl[s.quest] && qEl[s.quest].firstElementChild);
      if (tgt) curve(a, cvPos(tgt, inner), 'set', rowKey, k);
    }
    // needs: from the stage(s) that let it be said, shown when you point at the line or the stage
    const q = CV.map.quests;
    for (const nd of r.needs){
      const qq = q.find(x => x.key === nd.quest); if (!qq) continue;
      for (const s of qq.stages){
        const ok = {'=': s.index === nd.value, '!=': s.index !== nd.value, '>': s.index > nd.value, '>=': s.index >= nd.value, '<': s.index < nd.value, '<=': s.index <= nd.value}[nd.op];
        if (ok && stEl[nd.quest + '|' + s.index]){
          const sp = cvPos(stEl[nd.quest + '|' + s.index], inner);
          paths.push(`<path class="need" d="M${sp.x},${sp.y + sp.h / 2} C${sp.x - 120},${sp.y + sp.h / 2} ${a.x + a.w + 120},${a.y + 14} ${a.x + a.w},${a.y + 14}" data-er="${esc(rowKey)}" data-es="${esc(nd.quest + '|' + s.index)}"/>`);
        }
      }
    }
  }
  svg.innerHTML = paths.join('');
  cvSize();
}
function cvHot(row, st){
  const svg = $('#cv-edges'); if (!svg) return;
  const inner = $('#cv-inner');
  inner.querySelectorAll('.hot').forEach(x => x.classList.remove('hot'));
  const any = row || st;
  svg.querySelectorAll('path').forEach(p => {
    const on = (row && p.dataset.er === row) || (st && p.dataset.es === st);
    p.classList.toggle('hot', !!on); p.classList.toggle('dim', !!any && !on);
    if (on && st){ const r = inner.querySelector(`[data-row="${CSS.escape(p.dataset.er)}"]`); if (r) r.classList.add('hot'); }
    if (on && row && p.dataset.es){ const s = inner.querySelector(`[data-st="${CSS.escape(p.dataset.es)}"]`); if (s) s.classList.add('hot'); }
  });
}
// drag the empty background to look around
function cvPan(el){
  if (!el) return;
  let sx, sy, sl, stp, on = false;
  el.onpointerdown = e => {
    if (e.button !== 0 || e.target.closest('.cvbox,.qcard,.qh,.qwho')) return;
    on = true; sx = e.clientX; sy = e.clientY; sl = el.scrollLeft; stp = el.scrollTop; el.classList.add('drag'); el.setPointerCapture(e.pointerId);
  };
  el.onpointermove = e => { if (on){ el.scrollLeft = sl - (e.clientX - sx); el.scrollTop = stp - (e.clientY - sy); } };
  el.onpointerup = el.onpointercancel = () => { on = false; el.classList.remove('drag'); };
}

// ---------------------------------------------------------------- the tester
async function cvTest(c){
  const box = $('#cvbody');
  box.innerHTML = `<div class="msg" style="margin:6px 0 2px;line-height:1.6">Set up the game the way the player would find it (on the left), then talk to ${esc(c.name || c.id)} the way the game would: the greeting, then click topics.
      <label style="margin-left:10px;white-space:nowrap"><input type="checkbox" id="cv-follow" ${CV.follow ? 'checked' : ''}> Follow what lines do (quest stages, items, disposition)</label></div>
    <div class="cvtest"><aside class="cvstate" id="cv-state"><span class="spin"></span></aside>
      <section><div class="cvwin"><div class="cvlog" id="cv-log"></div><div class="cvtopics" id="cv-topics"></div></div>
        <div class="actions" style="margin-top:8px"><button class="btn sm" id="cv-greet">👋 Talk to them again</button><button class="btn sm" id="cv-clear">Clear the conversation</button><button class="btn sm" id="cv-reset">Fresh game</button></div>
        <div id="cv-problems"></div><div class="cvwhy" id="cv-why"></div></section></div>`;
  $('#cv-follow').onchange = e => CV.follow = e.target.checked;
  $('#cv-greet').onclick = () => cvSay(c, 'greeting');
  $('#cv-clear').onclick = () => { CV.log = []; CV.last = null; cvDrawLog(c); $('#cv-why').innerHTML = ''; };
  $('#cv-reset').onclick = () => {
    Object.assign(CV.state, {talked: false, disposition: null, quests: {}, globals: {}, items: {}, dead: {}, locals: {}, values: {}, choice: null});
    CV.log = []; CV.last = null; cvTest(c);
  };
  if (!CV.log.length) await cvSay(c, 'greeting');
  else { await cvRefresh(c); cvDrawLog(c); if (CV.last) cvDrawWhy(c, CV.last); }
  if (CV.autoTopic){ const t = CV.autoTopic; CV.autoTopic = null; await cvSay(c, t.startsWith('greeting ') ? 'greeting' : t); }
  api('/api/convo/problems?' + new URLSearchParams({id: c.id})).then(ps => {
    const el = $('#cv-problems'); if (!el || !ps.length) return;
    el.innerHTML = `<div class="card" style="margin-top:12px;border-color:var(--amber)"><b style="color:var(--amber)">⚠ ${ps.length} of your lines can never be said by ${esc(c.name || c.id)}</b>
      <div class="msg" style="margin:4px 0 6px">A line above each one, in the same topic, asks for less and so always wins. Move yours up, or give it a condition the other one doesn't have.</div>
      ${ps.slice(0, 20).map(p => `<div class="dline" style="margin-top:6px"><div class="dtext">${esc(p.line.text)}</div>
        <div class="dchips"><span class="dchip">${esc(p.id)}</span><span class="dchip">beaten by: “${esc(p.by.text.slice(0, 80))}…” (${esc(p.by.src)})</span></div>
        <div class="dbtns"><button class="btn sm" data-pe="${esc(p.line.topic)}|${esc(p.line.inam)}">✎ Open</button></div></div>`).join('')}</div>`;
    el.querySelectorAll('[data-pe]').forEach(b => b.onclick = () => { const [t, ...i] = b.dataset.pe.split('|'); cvEditLine(t, i.join('|')); });
  }).catch(() => {});
}
async function cvCall(c, topic){
  return post('/api/convo/say', {id: c.id, state: CV.state, topic: topic || null, cell: CV.cell || null});
}
// say a topic: the line goes into the conversation, and (if following) what it does happens
async function cvSay(c, topic){
  let r;
  try { r = await cvCall(c, topic); } catch (e){ toast(e.message, true); return; }
  CV.inputs = r.inputs; CV.speaker = r.speaker;
  const d = r.detail;
  const said = d && d.said != null ? d.lines[d.said] : null;
  CV.log.push({key: topic, id: d ? d.id : topic, line: said, maybe: d ? d.lines.slice(0, d.said ?? d.lines.length).filter(l => l.state === 'maybe').length : 0});
  CV.last = d;
  if (CV.state.choice != null) CV.state.choice = null;
  let changed = false;
  if (said && CV.follow) changed = cvApply(said.fx);
  if (changed){ try { r = await cvCall(c, null); } catch (e){ /* keep the old list */ } }
  CV.topics = r.topics;
  if (CV.state.disposition == null) CV.state.disposition = r.state.disposition;
  cvDrawState(c); cvDrawLog(c); cvDrawTopics(c); cvDrawWhy(c, d);
}
async function cvRefresh(c){
  try { const r = await cvCall(c, null); CV.topics = r.topics; CV.inputs = r.inputs; CV.speaker = r.speaker; if (CV.state.disposition == null) CV.state.disposition = r.state.disposition; }
  catch (e){ toast(e.message, true); }
  cvDrawState(c); cvDrawTopics(c);
}
function cvApply(fx){
  const s = CV.state; let ch = false;
  for (const x of fx.sets){ s.quests[x.quest] = x.stage; ch = true; }
  for (const g of fx.gives){ const k = g.id.toLowerCase(); s.items[k] = (+s.items[k] || 0) + g.n; ch = true; }
  for (const g of fx.takes){ const k = g.id.toLowerCase(); s.items[k] = Math.max(0, (+s.items[k] || 0) - g.n); ch = true; }
  if (fx.disp){ s.disposition = Math.max(0, Math.min(100, fx.disp.set ? fx.disp.n : (+s.disposition || 0) + fx.disp.n)); ch = true; }
  return ch;
}
function cvDrawLog(c){
  const el = $('#cv-log'); if (!el) return;
  const names = (CV.topics || []).filter(t => t.type === 0).map(t => t.id).sort((a, b) => b.length - a.length);
  const linkify = text => {
    let h = esc(text);
    if (!names.length) return h;
    const rx = new RegExp('\\b(' + names.map(n => esc(n).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|') + ')\\b', 'gi');
    return h.replace(rx, m => `<a data-cvlink="${esc(m.toLowerCase())}">${m}</a>`);
  };
  el.innerHTML = CV.log.map((e, n) => {
    const l = e.line, fx = l ? l.fx : null, tags = [];
    if (fx){
      for (const s of fx.sets) tags.push(`📜 ${esc(s.quest)} → ${s.stage}`);
      for (const g of fx.gives) tags.push(`you get ${g.n} ${esc(g.id)}`);
      for (const g of fx.takes) tags.push(`you give ${g.n} ${esc(g.id)}`);
      if (fx.disp) tags.push(`disposition ${fx.disp.set ? '= ' : (fx.disp.n >= 0 ? '+' : '')}${fx.disp.n}`);
      for (const t of fx.learns) tags.push(`learn “${esc(t)}”`);
      for (const f of fx.faction) tags.push(esc(f));
      if (fx.bye) tags.push('the conversation ends');
    }
    const last = n === CV.log.length - 1;
    return `<div class="cvsaid"><div class="tn">${esc(e.id)}</div>
      ${l ? `<div class="tx">${linkify(l.text)}</div>` : `<div class="tx none">They have nothing to say about that${e.maybe ? ' (unless something the tester can’t tell is true)' : ''}.</div>`}
      ${tags.length ? `<div class="fx">${tags.map(t => `<span>${t}</span>`).join('')}</div>` : ''}
      ${l && fx.choices.length && last ? `<div class="cvchoice">${fx.choices.map(ch => `<button data-cvch="${ch.n}">${esc(ch.label)}</button>`).join('')}</div>` : ''}
      ${e.maybe ? `<div class="msg" style="color:var(--amber);font-size:12px">${e.maybe} line${e.maybe > 1 ? 's' : ''} above might be said instead: they depend on something the tester can’t tell.</div>` : ''}
      <span class="why" data-cvwhy="${n}">Why this line?</span></div>`;
  }).join('') || '<div class="msg">…</div>';
  el.scrollTop = el.scrollHeight;
  el.querySelectorAll('[data-cvlink]').forEach(a => a.onclick = () => {
    const t = (CV.topics || []).find(x => x.id.toLowerCase() === a.dataset.cvlink); if (t) cvSay(c, t.key);
  });
  el.querySelectorAll('[data-cvch]').forEach(b => b.onclick = () => { CV.state.choice = +b.dataset.cvch; cvSay(c, CV.log[CV.log.length - 1].key); });
  el.querySelectorAll('[data-cvwhy]').forEach(s => s.onclick = async () => {
    const e = CV.log[+s.dataset.cvwhy];
    try { const r = await cvCall(c, e.key); cvDrawWhy(c, r.detail); $('#cv-why').scrollIntoView({behavior: 'smooth', block: 'start'}); } catch (err){ toast(err.message, true); }
  });
}
function cvDrawTopics(c){
  const el = $('#cv-topics'); if (!el) return;
  const ts = (CV.topics || []).filter(t => t.key !== 'greeting');
  const g = k => ts.filter(t => t.type === k);
  const btn = t => `<button data-cvt="${esc(t.key)}" class="${t.own ? 'own' : ''} ${!t.said && t.maybe ? 'maybe' : ''}" title="${t.said ? '' : 'Might have something to say, depending on something the tester can’t tell'}${t.own ? (t.said ? '' : '\n') + 'Has lines written just for them' : ''}">${esc(t.id)}${!t.said && t.maybe ? ' ?' : ''}</button>`;
  el.innerHTML = g(0).map(btn).join('') + (g(3).length ? `<div class="h">Persuasion</div>${g(3).map(btn).join('')}` : '')
    || '<div class="msg" style="padding:6px">Nothing to talk about.</div>';
  el.querySelectorAll('[data-cvt]').forEach(b => b.onclick = () => cvSay(c, b.dataset.cvt));
}
function cvDrawWhy(c, d){
  const el = $('#cv-why'); if (!el || !d) { if (el) el.innerHTML = ''; return; }
  const said = d.said;
  const shown = d.lines.map((l, n) => ({l, n})).filter(({l, n}) => said == null ? true : n <= said || l.mine);
  const below = said == null ? 0 : d.lines.length - 1 - said;
  const verdictChip = (txt, v, title) => `<span class="dchip ${v === 'yes' ? 'ok' : v === 'no' ? 'no' : 'mb'}" ${title ? `title="${esc(title)}"` : ''}>${esc(txt)}</span>`;
  el.innerHTML = `<h3 class="dsec" style="margin-top:6px">${esc(d.id)}: how the line was picked</h3>
    <div class="msg" style="margin-bottom:4px">The game goes down these ${d.lines.length} line${d.lines.length > 1 ? 's' : ''} (just the ones ${esc(c.name || c.id)} could ever say) and says the first one where everything fits.
      ${said == null ? 'None fits right now.' : below ? `The ${below} below the one said aren’t reached${d.lines.slice(said + 1).some(l => l.mine) ? ' (yours are still shown)' : ''}.` : ''}</div>
    ${shown.map(({l, n}) => {
      const cls = n === said ? 'said' : l.state === 'maybe' && (said == null || n < said) ? 'maybe' : (said == null || n < said) ? 'skip' : '';
      const tag = n === said ? '✓ said' : l.state === 'maybe' && (said == null || n < said) ? '? might be said' : (said == null || n < said) ? 'skipped' : 'not reached';
      const who = [l.actor, l.race, l.cls, l.faction && l.faction.toLowerCase() !== 'ffff' ? l.faction : '', l.cell].filter(Boolean);
      const chips = [`<span class="dchip who">${who.length ? '🗣 ' + esc(who.join(' · ')) : 'anyone'}</span>`];
      if (l.sex >= 0) chips.push(`<span class="dchip">${l.sex ? 'female' : 'male'} speaker</span>`);
      if (l.disp) chips.push(verdictChip('disposition ≥ ' + l.disp, l.disp_ok));
      if (l.pcfaction) chips.push(verdictChip('player in ' + l.pcfaction, l.pc_ok));
      l.conds.forEach((cd, i) => chips.push(verdictChip(condText(cd), l.verdicts[i], l.verdicts[i] === 'maybe' ? 'The tester can’t tell this one: set it on the left' : '')));
      return `<div class="cvwl ${cls}"><div class="wtop"><div class="dtext" style="font-size:13px">${esc(l.text) || '<i class="msg">(no text)</i>'}</div>
          <span class="tag">${tag} · #${n + 1}${l.mine ? ' · yours' : ''}${l.shadow != null ? `<br><span style="color:var(--amber)" title="Line #${l.shadow + 1} above asks for less, so it always wins">⚠ never said: #${l.shadow + 1} always wins</span>` : ''}</span></div>
        <div class="dchips" style="margin-top:4px">${chips.join('')}</div>
        <div class="actions" style="margin:4px 0 0"><span class="msg" style="font-size:11px">${esc(l.src)}</span><button class="btn sm" data-cve="${esc(l.topic)}|${esc(l.inam)}">${l.mine ? '✎ Edit' : '✎ Change'}</button></div></div>`;
    }).join('')}`;
  el.querySelectorAll('[data-cve]').forEach(b => b.onclick = () => { const [t, ...i] = b.dataset.cve.split('|'); cvEditLine(t, i.join('|')); });
}
function cvDrawState(c){
  const el = $('#cv-state'); if (!el || !CV.inputs) return;
  const s = CV.state, inp = CV.inputs, sp = CV.speaker || {}, o = D.opts || {};
  const sel = (id, list, v, empty) => `<select class="inp" data-cvs="${id}">${empty != null ? `<option value="">${empty}</option>` : ''}${list.map(x => `<option ${String(x).toLowerCase() === String(v || '').toLowerCase() ? 'selected' : ''}>${esc(x)}</option>`).join('')}</select>`;
  const num = (path, v, ph) => `<input class="inp" type="number" step="any" data-cvs="${path}" value="${v ?? ''}" placeholder="${esc(ph ?? '')}">`;
  const row = (label, ctl, title) => `<div class="cvf" ${title ? `title="${esc(title)}"` : ''}><span>${label}</span>${ctl}</div>`;
  let h = `<h4>The player</h4>
    ${row('Race', sel('race', o.races || [], s.race))}
    ${row('Sex', `<select class="inp" data-cvs="sex"><option value="0" ${!+s.sex ? 'selected' : ''}>male</option><option value="1" ${+s.sex ? 'selected' : ''}>female</option></select>`)}
    ${row('Faction', sel('faction', o.factions || [], s.faction, 'none'))}
    ${s.faction ? row('Rank in it', num('rank', s.rank)) : ''}
    ${row('Level', num('level', s.level))}
    <h4>${esc(sp.name || c.name || c.id)}</h4>
    ${row('Disposition', num('disposition', s.disposition), 'How much they like the player (their own is ' + (sp.disposition ?? '?') + ')')}
    ${row('Talked to the player before', `<input type="checkbox" data-cvs="talked" ${s.talked ? 'checked' : ''} style="justify-self:start">`)}
    ${(sp.cells || []).length > 1 ? row('Standing in', `<select class="inp" data-cvs="cell">${sp.cells.map(x => `<option ${x === (CV.cell || sp.cell) ? 'selected' : ''}>${esc(x)}</option>`).join('')}</select>`) : ''}
    ${inp.locals.map(v => row(`Script variable <code>${esc(v)}</code>`, num('locals.' + v, s.locals[v], '0'))).join('')}`;
  if (inp.quests.length) h += `<h4>Quests</h4>` + inp.quests.map(q => row(esc(q.title || q.id), `<select class="inp" data-cvs="quests.${esc(q.key)}" title="${esc(q.id)}">
      <option value="0">not started</option>${q.stages.map(x => `<option value="${x.index}" ${+s.quests[q.key] === x.index ? 'selected' : ''}>${x.index} · ${esc(x.text.slice(0, 50))}</option>`).join('')}
      ${s.quests[q.key] && !q.stages.some(x => x.index === +s.quests[q.key]) ? `<option selected value="${s.quests[q.key]}">${s.quests[q.key]}</option>` : ''}</select>`, q.id)).join('');
  if (inp.items.length) h += `<h4>The player carries</h4>` + inp.items.map(i => row(esc(i), num('items.' + i.toLowerCase(), s.items[i.toLowerCase()], '0'))).join('');
  if (inp.dead.length) h += `<h4>How many are dead</h4>` + inp.dead.map(i => row(esc(i), num('dead.' + i.toLowerCase(), s.dead[i.toLowerCase()], '0'))).join('');
  if (inp.globals.length) h += `<h4>Global variables</h4>` + inp.globals.map(g => row(esc(g.name), num('globals.' + g.name.toLowerCase(), s.globals[g.name.toLowerCase()], g.random ? 'random' : g.start),
      g.random ? 'The game rolls this afresh all the time. Leave it empty for "sometimes", or set a roll' : 'Starts at ' + g.start)).join('');
  const fs = inp.functions.filter(f => !f.derived);
  if (fs.length) h += `<h4>Other things they test</h4>` + fs.map(f => row(esc(f.name), num('values.' + f.name, s.values[f.name], f.default ?? '?'),
      f.default == null ? 'The tester can’t tell this one by itself: lines that test it count as "might be said" until you set it' : '')).join('');
  const derived = inp.functions.filter(f => f.derived && !['Choice', 'Talked to player before', 'Player sex (0 male, 1 female)'].includes(f.name));
  if (derived.length) h += `<div class="msg" style="margin-top:8px;font-size:11.5px">Also worked out from the player and them: ${derived.map(f => esc(f.name.toLowerCase())).join(', ')}.</div>`;
  el.innerHTML = h;
  let t;
  el.querySelectorAll('[data-cvs]').forEach(inpEl => inpEl.onchange = inpEl.oninput = () => {
    const path = inpEl.dataset.cvs, dot = path.indexOf('.');
    const val = inpEl.type === 'checkbox' ? inpEl.checked : inpEl.value;
    if (path === 'cell'){ CV.cell = val; }
    else if (dot > 0){
      const grp = path.slice(0, dot), k = path.slice(dot + 1);
      if (val === '' || val == null) delete s[grp][k]; else s[grp][k] = +val;
    } else if (['sex', 'rank', 'level', 'disposition'].includes(path)) s[path] = val === '' ? null : +val;
    else s[path] = val;
    clearTimeout(t);
    t = setTimeout(async () => { if (path === 'faction') cvDrawState(c); await cvRefresh(c); }, inpEl.tagName === 'SELECT' || inpEl.type === 'checkbox' ? 0 : 350);
  });
}

// ---------------------------------------------------------------- a quest's flow
// stages left to right, who says what in rows: each line sits under the first stage it can be
// said at, with an arrow to the stage it moves the quest on to.
async function cvQuestFlow(q){
  const box = $('#q-flow');
  box.innerHTML = '<div class="msg" style="padding:20px"><span class="spin"></span>Finding every line that needs or moves this quest…</div>';
  let r;
  try { r = await api('/api/convo/quest?' + new URLSearchParams({key: q.key})); } catch (e){ box.innerHTML = `<div class="msg err">${esc(e.message)}</div>`; return; }
  if (!$('#q-flow')) return;
  const stages = r.quest.stages.map(s => s.index);
  const cols = [0, ...stages.filter(s => s !== 0)];
  const fits = (v, nd) => ({'=': v === nd.value, '!=': v !== nd.value, '>': v > nd.value, '>=': v >= nd.value, '<': v < nd.value, '<=': v <= nd.value})[nd.op];
  const colOf = l => {
    if (!l.needs.length) return 'any';
    const c = cols.find(v => l.needs.every(nd => fits(v, nd)));
    return c === undefined ? 'other' : c;
  };
  const keys = ['any', ...cols, 'other'];
  for (const l of r.lines) l._c = colOf(l);
  const used = keys.filter(k => typeof k === 'number' || r.lines.some(l => l._c === k));
  const who = [];
  for (const k of used) for (const l of r.lines) if (l._c === k && !who.includes(l.who)) who.push(l.who);
  if (!r.lines.length){ box.innerHTML = `<div class="card msg">No line in the game needs or moves this quest yet.</div>`; return; }
  const stageOf = Object.fromEntries(r.quest.stages.map(s => [s.index, s]));
  const head = k => k === 'any' ? `<div class="qh" data-qc="any"><b>Any time</b><br><span class="msg">lines that move it on whatever stage it’s at</span></div>`
    : k === 'other' ? `<div class="qh" data-qc="other"><b>Other stages</b><br><span class="msg">needs a stage the quest doesn’t have</span></div>`
    : k === 0 ? `<div class="qh" data-qc="0"><b>Not started</b><br><span class="msg">before the first journal entry</span></div>`
    : `<div class="qh ${stageOf[k] && stageOf[k].finished ? 'fin' : ''}" data-qc="${k}" title="${esc(stageOf[k] ? stageOf[k].text : '')}"><b>${k}</b> ${esc((stageOf[k] ? stageOf[k].text : '').slice(0, 110))}</div>`;
  const card = (l, n) => `<div class="qcard ${l.mine ? 'mine' : ''}" data-qcard="${n}" title="${esc(l.src)}"><div class="qt">${l.tid === 'Greeting' ? '👋 Greeting' : '💬 ' + esc(l.tid)}${l.other.length ? ` · +${l.other.length} other test${l.other.length > 1 ? 's' : ''}` : ''}</div>
      <div class="cvt">${esc(l.text) || '<i class="msg">(no text)</i>'}</div>
      <div class="cvchips">${l.needs.map(nd => `<span class="need">${cvOp(nd.op)} ${nd.value}</span>`).join('')}${l.sets.map(s => `<span class="set">→ ${s}</span>`).join('')}
        ${l.choices.length ? `<span>${l.choices.length} choices</span>` : ''}${l.gives.map(g => `<span>+ ${g.n} ${esc(g.id)}</span>`).join('')}${l.takes.map(g => `<span>− ${g.n} ${esc(g.id)}</span>`).join('')}</div></div>`;
  let h = `<div class="cvbar"><div class="seg"><button data-zoom="-1" title="Smaller">−</button><button data-zoom="0" title="Actual size">${Math.round(CV.zoom * 100)}%</button><button data-zoom="1" title="Larger">+</button></div>
    <button class="btn sm" id="cv-tidy" title="Put every line back under its stage">↺ Tidy up</button>
    <span class="msg">Each line sits under the first stage it can be said at; a gold arrow goes to the stage it moves the quest on to. Rows are who says it. Point at a line to follow it, drag it to move it, click to open it.${r.more ? ` (${r.more} more lines not shown.)` : ''}</span></div>
    <div class="cvcanvas" id="cv-canvas" style="height:calc(100vh - 300px)"><div class="cvsizer" id="cv-sizer"><div class="cvinner" id="cv-inner" style="transform:scale(${CV.zoom})"><svg class="cvedges" id="cv-edges"></svg>
    <div class="qflow" style="grid-template-columns:150px repeat(${used.length}, 250px)"><div></div>${used.map(head).join('')}`;
  for (const w of who){
    const first = r.lines.find(l => l.who === w);
    h += `<div class="qwho" ${first && first.actor ? `data-qnpc="${esc(first.actor)}" title="Open their dialogue"` : ''}>${esc(w)}</div>`;
    for (const k of used) h += `<div class="qcell" data-qcell="${esc(w)}|${k}">${r.lines.map((l, n) => l.who === w && l._c === k ? card(l, n) : '').join('')}</div>`;
  }
  h += `</div></div></div></div>`;
  box.innerHTML = h;
  cvBindMapBar(null, box);
  // arrows: from each line to the stage it sets, in the same person's row (the next thing they'd say)
  const inner = $('#cv-inner'), svg = $('#cv-edges');
  // the cards can be dragged about (the rows and stages keep their size, so the grid stays put)
  inner.querySelectorAll('.qcell').forEach(el => { el.style.height = el.offsetHeight + 'px'; });
  const saveKey = 'qflow:' + q.key;
  cvDraggable(inner, [...inner.querySelectorAll('[data-qcard]')].map(el => { const l = r.lines[+el.dataset.qcard]; return {el, key: l.topic + '|' + l.inam}; }),
              () => drawFlow(), saveKey);
  const tidy = $('#cv-tidy'); if (tidy) tidy.onclick = () => { try { localStorage.removeItem(saveKey); } catch (e){} cvQuestFlow(q); };
  drawFlow();
  function drawFlow(){
  const W = inner.scrollWidth, H = inner.scrollHeight; svg.setAttribute('width', W); svg.setAttribute('height', H);
  const paths = [];
  inner.querySelectorAll('[data-qcard]').forEach(el => {
    const l = r.lines[+el.dataset.qcard], a = cvPos(el, inner);
    for (const s of l.sets){
      const cell = inner.querySelector(`[data-qcell="${CSS.escape(l.who + '|' + s)}"]`), hd = inner.querySelector(`[data-qc="${s}"]`);
      const tgt = cell && cell.firstElementChild ? cell : hd; if (!tgt) continue;
      const b = cvPos(tgt, inner), x1 = a.x + a.w, y1 = a.y + 18;
      if (tgt === cell){
        const x2 = b.x, y2 = b.y + 14;
        const d = x2 > x1 + 10 ? `M${x1},${y1} C${x1 + 50},${y1} ${x2 - 50},${y2} ${x2},${y2}`
          : `M${x1},${y1} C${x1 + 50},${y1} ${x1 + 50},${y1 - 40} ${(x1 + x2) / 2},${Math.min(y1, y2) - 40} S${x2 - 50},${y2} ${x2},${y2}`;
        paths.push(`<path class="set" data-er="${el.dataset.qcard}" d="${d}"/>`);
      } else {
        const x2 = b.x + Math.min(30, b.w / 2), y2 = b.y + b.h;
        paths.push(`<path class="set" data-er="${el.dataset.qcard}" d="M${x1},${y1} C${x1 + 60},${y1} ${x2},${y2 + 80} ${x2},${y2}"/>`);
      }
    }
  });
  svg.innerHTML = paths.join('');
  cvSize();
  }
  inner.querySelectorAll('[data-qcard]').forEach(el => {
    el.onmouseenter = () => cvHot(el.dataset.qcard, null);
    el.onmouseleave = () => cvHot(null, null);
    el.onclick = () => { const l = r.lines[+el.dataset.qcard]; cvEditLine(l.topic, l.inam); };
  });
  inner.querySelectorAll('[data-qnpc]').forEach(el => el.onclick = () => { CV.tab = 'map'; dOpen('npc', el.dataset.qnpc); });
  cvPan($('#cv-canvas'));
}
