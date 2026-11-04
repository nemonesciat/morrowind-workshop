// ---------- Roll the interior (rollinside.py): another interior for a built building, kept in limbo until one is kept ----------
// Right-click a building outdoors → 🎲 Roll the interior. The card: the old interior and each roll as a chip with the
// purpose check's verdict, the picked one's plan and what it holds, what to roll until, and Keep / Roll again / Put
// the old one back. The building's door leads into whichever is picked, so Walk in shows it in place.
const RI = {on: false, panel: null, cell: null, ref: null, v: null, until: {forge: false, bed: true, floors: false, clean: false}, busy: false, faulty: null};
const RI_KINDS = [['', 'as it is named'], ['house', 'a home'], ['smith', 'a smithy'], ['shop', 'a shop'], ['tavern', 'a tavern'], ['temple', 'a temple'],
  ['guild:mages', "a Mages' hall"], ['guild:fighters', "a Fighters' hall"], ['manor', 'a manor'], ['guard', 'a guardroom']];
const RI_LEVELS = [['', 'as its trade'], ['poor', 'Poor'], ['modest', 'Modest'], ['comfortable', 'Comfortable'], ['rich', 'Rich'], ['exquisite', 'Exquisite']];
const RI_MARK = {forge: '🔥', anvil: '⚒', bed: '🛏', counter: '▬', shrine: '✦', target: '◎', fire: '♨'};

(function riStyle(){
  const st = document.createElement('style');
  st.textContent = `
.richips{display:flex;flex-wrap:wrap;gap:4px;margin:6px 0}
.richip{border:1px solid var(--line2);border-radius:10px;padding:2px 9px;font-size:12px;cursor:pointer;white-space:nowrap;background:var(--panel)}
.richip:hover{border-color:var(--gold)} .richip.on{border-color:var(--gold);color:var(--gold2)} .richip.old{border-style:dashed}
.richip .ok{color:var(--green)} .richip .bad{color:var(--amber)}
.riplan{display:block;background:var(--deep);border:1px solid var(--line);border-radius:8px;margin:6px 0}
.ristat{font-size:12px;line-height:1.6;color:var(--muted)} .ristat b{color:var(--text);font-weight:600}
.ristat .ok{color:var(--green)} .ristat .bad{color:var(--amber)}
.rirow{display:flex;gap:6px;align-items:center;flex-wrap:wrap;font-size:12px;margin:5px 0}
.rirow select{font-size:12px;padding:2px 4px;width:auto;flex:0 1 auto}
.rirow label{white-space:nowrap}
.rifault{font-size:12px;border-top:1px solid var(--line);margin-top:8px;padding-top:6px}
.rifault div{display:flex;gap:6px;align-items:center;padding:2px 0} .rifault .n{flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}`;
  document.head.appendChild(st);
})();

function riMenuItem(ck, r){
  if (typeof fbOutside !== 'function' || !fbOutside(ck) || !(r.arch || r.type === 'DOOR') || (typeof FB_NOT_BUILDING !== 'undefined' && FB_NOT_BUILDING.test(r.id))) return null;
  return {label: '🎲 Roll the interior…', act: () => riOpen(ck, r.k)};
}

function riPanel(html){
  if (!RI.panel){
    const p = document.createElement('div'); p.className = 'modal'; p.id = 'ri-panel';
    p.style.cssText = 'position:fixed;right:16px;top:90px;width:340px;max-height:calc(100% - 120px);overflow:auto;z-index:61;box-shadow:0 6px 24px #0008;padding:10px';
    document.body.appendChild(p);
    RI.panel = p;
  }
  RI.panel.innerHTML = `<h2 style="margin:0 0 6px;font-size:15px;display:flex;align-items:center;gap:6px"><span style="flex:1">🎲 Roll the interior${typeof guideLink === 'function' ? guideLink('building-interiors.md', 'Roll the interior') : ''}</span><button class="btn sm" id="ri-close" title="Close (the rolls stay in limbo; the door leads into the one picked)">✕</button></h2>${html}`;
  RI.panel.querySelector('#ri-close').onclick = riClose;
}
function riClose(){ RI.on = false; if (RI.panel){ RI.panel.remove(); RI.panel = null; } }

async function riOpen(cell, ref){
  RI.on = true; RI.cell = cell; RI.ref = ref; RI.v = null; RI.faulty = null;
  riPanel('<div class="msg"><span class="spin"></span>Reading the building…</div>');
  try { RI.v = await api('/api/roll/view?cell=' + encodeURIComponent(cell) + '&ref=' + encodeURIComponent(ref)); }
  catch (e){ riPanel(`<div class="msg" style="color:var(--red)">${esc(e.message)}</div>`); return; }
  riRender();
}

function riCard(v){ return [...(v.old ? [v.old] : []), ...v.rolls].find(c => c.key === v.picked) || v.rolls[v.rolls.length - 1] || v.old; }

function riPlan(c){
  const P = c && c.plan; if (!P || !P.rooms.length) return '<div class="msg" style="padding:8px 0">no rooms read</div>';
  const x0 = Math.min(...P.rooms.map(r => r.x0)), x1 = Math.max(...P.rooms.map(r => r.x1)), y0 = Math.min(...P.rooms.map(r => r.y0)), y1 = Math.max(...P.rooms.map(r => r.y1));
  const W = 316, H = 170, s = Math.min((W - 16) / Math.max(1, x1 - x0), (H - 16) / Math.max(1, y1 - y0));
  const X = x => 8 + (x - x0) * s, Y = y => H - 8 - (y - y0) * s;
  const zs = [...new Set(P.rooms.map(r => r.z))].sort((a, b) => a - b);
  let h = `<svg class="riplan" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">`;
  for (const r of P.rooms){
    const up = zs.indexOf(r.z);
    h += `<rect x="${X(r.x0)}" y="${Y(r.y1)}" width="${(r.x1 - r.x0) * s}" height="${(r.y1 - r.y0) * s}" fill="${up ? 'none' : 'rgba(210,168,90,.06)'}" stroke="${up ? 'var(--muted)' : 'var(--goldline)'}" stroke-width="${up ? 1 : 1.5}" ${up ? 'stroke-dasharray="4 3"' : ''}><title>${esc(r.name || 'room')}${up ? ' (floor ' + (up + 1) + ')' : ''}</title></rect>`;
    if ((r.x1 - r.x0) * s > 40 && (r.y1 - r.y0) * s > 16) h += `<text x="${X(r.x0) + 4}" y="${Y(r.y1) + 11}" font-size="9" fill="var(--faint)">${esc((r.name || '').slice(0, 14))}</text>`;
  }
  for (const m of P.marks) h += `<text x="${X(m.x)}" y="${Y(m.y) + 4}" font-size="11" text-anchor="middle"><title>${esc(m.f)}</title>${RI_MARK[m.f] || '•'}</text>`;
  for (const d of P.doors) h += `<circle cx="${X(d.x)}" cy="${Y(d.y)}" r="3.5" fill="${d.out ? 'var(--green)' : 'var(--blue)'}"><title>${d.out ? 'the way out' : 'a door'}</title></circle>`;
  return h + '</svg>';
}

function riRender(){
  const v = RI.v; if (!v) return;
  const c = riCard(v);
  const chip = (x, old) => `<span class="richip ${x.key === v.picked ? 'on' : ''} ${old ? 'old' : ''}" data-ripick="${esc(x.key)}" title="${esc(x.verdict)} · ${x.rooms} rooms, ${x.things} things${x.people ? ', ' + x.people + ' people' : ''}">${old ? 'before' : esc((x.name.match(/\(roll (\d+)\)/) || [, '?'])[1])} <span class="${x.ok ? 'ok' : 'bad'}">${x.ok ? '✓' : '✗'}</span></span>`;
  const has = c ? Object.entries(c.has).filter(([k]) => ['forge', 'anvil', 'bed', 'counter', 'shrine', 'target'].includes(k)).map(([k, n]) => (n > 1 ? n + ' ' : '') + k + (n > 1 && k !== 'shelf' ? 's' : '')).join(', ') : '';
  const faults = c ? Object.entries(c.faults).filter(([k]) => !['purpose', 'nobed'].includes(k)).map(([k, n]) => `${n} ${{bare: 'bare room', deaddoor: 'dead door', sizefit: 'outside its building'}[k] || k}${n > 1 ? 's' : ''}`).join(' · ') : '';
  const h = `<div style="font-size:13px"><b>${esc(v.name)}</b> <span class="msg">${esc(v.building.id)}</span></div>
    <div class="richips">${v.old ? chip(v.old, true) : '<span class="msg">no interior yet</span>'}${v.rolls.map(x => chip(x, false)).join('')}</div>
    ${riPlan(c)}
    ${c ? `<div class="ristat"><b>${c.rooms} room${c.rooms === 1 ? '' : 's'}</b> on ${c.floors} floor${c.floors === 1 ? '' : 's'} · <b>${c.things}</b> things${c.people ? ` · ${c.people} people` : ''}${has ? ` · ${esc(has)}` : ''}<br>
      <span class="${c.ok ? 'ok' : 'bad'}">${c.ok ? '✓ ' : '✗ '}${esc(c.verdict)}</span>${faults ? `<br><span class="msg">${esc(faults)}</span>` : ''}</div>` : ''}
    <div class="rirow">Furnish as <select id="ri-kind" title="What the rolled interior is for">${RI_KINDS.map(([k, t]) => `<option value="${k}" ${k === (v.kind || '') ? 'selected' : ''}>${t}</option>`).join('')}</select>
      <select id="ri-level" title="How well off">${RI_LEVELS.map(([k, t]) => `<option value="${k}" ${k === (v.level || '') ? 'selected' : ''}>${t}</option>`).join('')}</select></div>
    <div class="rirow" title="Rolls again on its own, up to eight times, until the interior has these">Roll until it has
      ${[['forge', 'a forge'], ['bed', 'a bed'], ['floors', '2 floors'], ['clean', 'no fault']].map(([k, t]) => `<label><input type="checkbox" data-riuntil="${k}" ${RI.until[k] ? 'checked' : ''}> ${t}</label>`).join('')}</div>
    <div class="actions" style="margin:8px 0 0;gap:6px;flex-wrap:wrap">
      <button class="btn sm primary" id="ri-roll" ${RI.busy ? 'disabled' : ''}>${RI.busy ? '<span class="spin"></span>Rolling…' : '🎲 Roll' + (v.rolls.length ? ' again' : '')}</button>
      ${c && c.key ? `<button class="btn sm" id="ri-walk" title="Open it on the map, as the door leads">👁 Walk in</button>` : ''}
      ${v.rolls.some(x => x.key === v.picked) ? `<button class="btn sm" id="ri-keep" title="Lock it in: the door leads here, the old interior's people move in, the old one and the other rolls go. One Undo takes it all back.">✓ Keep this one</button>` : ''}
      ${v.open ? `<button class="btn sm" id="ri-cancel" title="Take every roll out; the door leads into the old interior again">↶ Put the old one back</button>` : ''}</div>
    <div class="rifault" id="ri-faulty">${RI.faulty ? riFaultyHtml() : `<a href="#" id="ri-find" class="msg">Find the faulty interiors in this town ▸</a>`}</div>`;
  riPanel(h);
  const P = RI.panel;
  P.querySelectorAll('[data-ripick]').forEach(el => el.onclick = () => riAct('/api/roll/pick', {key: el.dataset.ripick}));
  P.querySelectorAll('[data-riuntil]').forEach(el => el.onchange = () => { RI.until[el.dataset.riuntil] = el.checked; });
  P.querySelector('#ri-roll').onclick = () => riAct('/api/roll', {kind: P.querySelector('#ri-kind').value, level: P.querySelector('#ri-level').value,
    until: Object.keys(RI.until).filter(k => RI.until[k])});
  const w = P.querySelector('#ri-walk'); if (w) w.onclick = () => { if (typeof worldOpen === 'function') worldOpen(c.key); };
  const k = P.querySelector('#ri-keep'); if (k) k.onclick = () => riKeep(v.picked);
  const x = P.querySelector('#ri-cancel'); if (x) x.onclick = () => riAct('/api/roll/cancel', {});
  const f = P.querySelector('#ri-find'); if (f) f.onclick = e => { e.preventDefault(); riFind(); };
  P.querySelectorAll('[data-riroll]').forEach(el => el.onclick = () => riOpen(RI.cell, el.dataset.riroll));
}

async function riAct(path, body){
  if (RI.busy || !await needProject()) return;
  RI.busy = true; riRender();
  try {
    RI.v = await post(path, Object.assign({cell: RI.cell, ref: RI.ref}, body));
    if (path === '/api/roll'){ const c = riCard(RI.v); toast(c ? `Rolled: ${c.rooms} rooms, ${c.things} things. ${c.verdict}` : 'Rolled'); }
    await afterChange();
  } catch (e){ toast(e.message, true); }
  RI.busy = false; riRender();
}

async function riKeep(key){
  if (RI.busy || !await needProject()) return;
  RI.busy = true; riRender();
  try {
    const r = await post('/api/roll/keep', {cell: RI.cell, ref: RI.ref, key});
    toast(`Kept ${r.name}${r.moved ? `, ${r.moved} people moved in` : ''}. One Undo takes it back.`);
    await afterChange();
    RI.busy = false;
    const faulty = RI.faulty;
    await riOpen(RI.cell, RI.ref);
    if (faulty){ RI.faulty = faulty.filter(f => f.key !== r.key && f.key !== key); riRender(); }
  } catch (e){ toast(e.message, true); RI.busy = false; riRender(); }
}

async function riFind(){
  const box = RI.panel && RI.panel.querySelector('#ri-faulty'); if (box) box.innerHTML = '<span class="spin"></span><span class="msg">Checking every interior of the town…</span>';
  try { RI.faulty = (await api('/api/roll/faulty?cell=' + encodeURIComponent(RI.cell))).faulty; } catch (e){ toast(e.message, true); RI.faulty = null; }
  riRender();
}
function riFaultyHtml(){
  const f = RI.faulty || [];
  if (!f.length) return '<span class="msg">Every interior with a door in this cell serves its purpose.</span>';
  return `<div class="msg">${f.length} faulty in this cell:</div>` + f.map(x => `<div><span class="n" title="${esc(x.verdict)}">${esc(x.name)}</span><button class="btn sm" data-riroll="${esc(x.ref)}" title="${esc(x.verdict)}">🎲</button></div>`).join('');
}
