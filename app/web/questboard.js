// ---------- The quest Board: a quest as a row of snapshots of its cast ----------
// (questboard.py reads; this draws.) Frames are the stages, left to right. Under each frame sit the
// moves that bring the player to it (a line said, an item handed over, a kill, a book read...), each
// with an arrow from the stage it starts at. The frame shows what the player holds by then, who is
// dead, and who holds the quest's things. Frames nothing leads to, and frames nothing leads out of,
// are flagged: the two faults the journal and the editor both hide.
const QB = {hot: null, cast: null, view: (() => { try { return localStorage.getItem('qb:view') || 'rail'; } catch (e){ return 'rail'; } })()};

(function qbStyle(){
  const st = document.createElement('style');
  st.textContent = `
.qbcast{display:flex;flex-wrap:wrap;gap:4px;align-items:center;margin:6px 0 8px;font-size:12px}
.qbcast .k{color:var(--faint);margin-left:8px;font-size:11px;letter-spacing:.06em;text-transform:uppercase}
.qbcast .k:first-child{margin-left:0}
.qbchip{border:1px solid var(--line2);border-radius:12px;padding:1px 9px;cursor:pointer;background:var(--panel);white-space:nowrap}
.qbchip:hover,.qbchip.on{border-color:var(--gold);color:var(--gold2)}
.qbchip.dim{opacity:.4}
.qbchip.person{border-color:var(--blue)} .qbchip.place{border-style:dashed}
.qboard{display:grid;gap:10px 70px;align-items:start;position:relative}
.qboard .qh{min-height:54px}
.qboard .qh.bad{border-color:var(--red)} .qboard .qh.dead{border-color:var(--amber)}
.qboard .qh .flag{display:block;font-size:11px;color:var(--amber);margin-top:3px} .qboard .qh.bad .flag{color:var(--red)}
.qboard .qh.start{border-style:dashed;color:var(--muted)}
.qbstate{border:1px dashed var(--line2);border-radius:8px;padding:5px 8px;font-size:11.5px;line-height:1.45;color:var(--muted);min-height:24px}
.qbstate b{color:var(--text);font-weight:600}
.qbstate .hold{display:block}
.qcard .verb{font-size:12.5px;color:var(--gold2);font-weight:600}
.qcard.script .verb{color:var(--blue)}
.qcard .cvt{color:var(--muted);font-size:12px}
.qcard.hit{outline:1px solid var(--gold)}
.qbadd{float:right;background:none;border:1px solid var(--line2);border-radius:10px;color:var(--muted);width:20px;height:20px;line-height:16px;padding:0;cursor:pointer;font:inherit;font-size:13px;margin:-2px -4px 0 4px}
.qbadd:hover{border-color:var(--gold);color:var(--gold2)}
.qbform{margin:0 0 8px;padding:8px 12px}
.qbrow{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:4px 0;font-size:13px}
.qbrow .inp{padding:3px 6px;font-size:12.5px}
.qrail .qrn{position:absolute;text-align:center;transition:opacity .15s}
.qrail .qrn .dot{width:34px;height:34px;border-radius:50%;border:2px solid var(--gold);background:var(--panel);margin:0 auto;line-height:30px;font-weight:600;font-size:13px;color:var(--gold2)}
.qrail .qrn.fin .dot{background:var(--gold);color:var(--deep)}
.qrail .qrn.bad .dot{border-color:var(--red);color:var(--red)} .qrail .qrn.dead .dot{border-color:var(--amber)}
.qrail .qrn.start .dot{width:auto;display:inline-block;padding:0 12px;border-radius:17px;border-style:dashed;color:var(--muted);font-weight:500}
.qrail .qrn .txt{font-size:11.5px;color:var(--muted);margin-top:5px;line-height:1.35;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;padding:0 4px}
.qrail .qrn .st{font-size:10.5px;color:var(--faint);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding:0 4px}
.qrail .qrn .st.said{color:var(--faint);opacity:.8}
.qrail .qrn .flag{font-size:10.5px;color:var(--amber);margin-top:2px} .qrail .qrn.bad .flag{color:var(--red)}
.qrail .qrn .qbadd{position:absolute;right:28px;top:-8px;float:none;margin:0;opacity:0} .qrail .qrn:hover .qbadd{opacity:1}
.qrail .qrn.hot .dot{box-shadow:0 0 0 3px rgba(210,168,90,.35)}
.qrm{position:absolute;font-size:12px;line-height:19px;height:19px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;cursor:pointer;color:var(--text);padding:0 4px;border-radius:5px;transition:opacity .15s}
.qrm .v{color:var(--gold2);font-weight:600} .qrm.script .v{color:var(--blue)}
.qrm .fx,.qrm .to,.qrm .wq{font-size:10.5px;color:var(--muted);margin-left:5px;border:1px solid var(--line2);border-radius:8px;padding:0 5px}
.qrm .fx.warn{color:var(--amber);border-color:var(--amber)}
.qrm .wq{color:var(--green);border-color:var(--green);cursor:pointer} .qrm .wq:hover{background:var(--hover)}
.qrm .to{color:var(--gold2)}
.qrm.mine{border-left:2px solid var(--gold)}
.qrm:hover,.qrm.hot{background:var(--hover);overflow:visible;z-index:3;width:auto!important;min-width:0}
.qrm.flag{color:var(--red);cursor:default;font-size:11px} .qrm.flag.faint{color:var(--faint)}
.qrm.flag:hover{background:none}
.qrm.arc{text-align:center} .qrm.arc.back .v{color:var(--amber)}
.qrband{position:absolute;left:24px;display:flex;flex-wrap:wrap;gap:4px 8px;align-items:center;border-top:1px dashed var(--line2);padding:8px 0 0}
.qrband .k{color:var(--faint);font-size:11px;letter-spacing:.06em;text-transform:uppercase;margin-right:6px}
.qrband .qrm{position:static;border:1px solid var(--line2);background:var(--panel);padding:0 7px;max-width:420px}
.qrband .qrm.never{border-color:var(--amber)}
.qrail .dim{opacity:.22}
.cvedges path.rail{stroke:var(--goldline);stroke-width:2.2;opacity:.9} .cvedges path.rail.gone{stroke-dasharray:4 5;stroke:var(--red)}
.cvedges path.rail.dim{opacity:.25}
.cvedges path.back{stroke:var(--amber);stroke-dasharray:5 4}
.qltab{border:1px solid var(--line);border-radius:8px;overflow:hidden;background:var(--panel);margin-top:8px}
.qltab .trow{grid-template-columns:minmax(150px,1.1fr) minmax(160px,2fr) minmax(110px,1fr) 56px 56px 120px;cursor:pointer;border-bottom:1px solid var(--line)}
.qltab .trow:not(.thead):hover{background:var(--panel2)}
.qltab .trow:not(.thead) .id{color:var(--text)}
.qltab .num{text-align:right;color:var(--muted);font-variant-numeric:tabular-nums}
.qltab .fl{font-size:12px} .qltab .fl.bad{color:var(--red)} .qltab .fl.dead{color:var(--amber)} .qltab .fl.ok,.qltab .fl.wait{color:var(--faint)}
.qltab .ttl{color:var(--muted)}`;
  document.head.appendChild(st);
})();

const QB_VERB = {
  talk: m => `Talk to ${m.whoName}${m.tid && m.tid !== 'Greeting' ? ' about "' + m.tid + '"' : ''}`,
  meet: m => `Meet ${m.whoName}`,
  bring: m => `Bring ${qbItems(m.takes)} to ${m.whoName}`,
  show: m => `Show ${qbNames(m.items)} to ${m.whoName}`,
  kill: m => `Kill ${m.whoName || qbNames(m.carriers)}`,
  read: m => `Read ${qbNames(m.carriers)}`,
  open: m => `Open ${qbNames(m.carriers)}`,
  use: m => `Use ${qbNames(m.carriers)}`,
  take: m => `Take ${qbNames(m.carriers)}`,
  drop: m => `Drop ${qbNames(m.carriers)}`,
  enter: m => `Enter ${qbNames(m.places)}`,
  approach: m => `Come near ${m.whoName || qbNames(m.carriers)}`,
  have: m => `Have ${qbNames(m.items)}`,
  wait: m => `Wait (${m.script})`,
  stand: m => `Standing with ${m.whoName || qbNames(m.carriers)}`,
  fight: m => `Fight ${m.whoName || qbNames(m.carriers)}`,
  script: m => `Script ${m.script}${m.whoName ? ' on ' + m.whoName : ''}`,
};
function qbName(id){ const c = QB.cast && QB.cast[(id || '').toLowerCase()]; return c ? c.name : id; }
function qbNames(ids){ return (ids || []).slice(0, 3).map(qbName).join(', ') || 'something'; }
function qbItems(lst){ return (lst || []).slice(0, 3).map(g => (g.n > 1 ? g.n + ' ' : '') + qbName(g.id)).join(', ') || 'something'; }
function qbLabel(m){ try { return (QB_VERB[m.verb] || QB_VERB.script)(m); } catch (e){ return m.verb; } }

async function qbBoard(q){
  const box = $('#q-board');
  box.innerHTML = '<div class="msg" style="padding:20px"><span class="spin"></span>Reading the quest: its stages, its cast, and every line and script that moves it…</div>';
  let r;
  try { r = await api('/api/quest/board?' + new URLSearchParams({key: q.key})); } catch (e){ box.innerHTML = `<div class="msg err">${esc(e.message)}</div>`; return; }
  if (!$('#q-board')) return;
  QB.cast = Object.fromEntries(r.cast.map(c => [c.id.toLowerCase(), c])); QB.last = r;
  if (QB.view === 'map') qbMap(q, r); else qbRail(q, r);
}
function qbView(q, v){ QB.view = v; try { localStorage.setItem('qb:view', v); } catch (e){} qbBoard(q); }
function qbViewSeg(){ return `<div class="seg" title="Rail: the stages on a line, each move written in the gap before the stage it sets. Map: every move as a card with an arrow from the stage it starts at">${[['rail', 'Rail'], ['map', 'Map']].map(([k, t]) => `<button data-qview="${k}" class="${QB.view === k ? 'on' : ''}">${t}</button>`).join('')}</div>`; }
// the cast a move touches (ids, lower case)
function qbCastOf(m){ return [m.who, ...(m.carriers || []), ...(m.items || []), ...(m.places || []), ...m.gives.map(g => g.id), ...m.takes.map(g => g.id)].filter(Boolean).map(x => x.toLowerCase()); }
function qbCastRow(r){
  const kinds = [['person', 'People'], ['creature', 'Creatures'], ['item', 'Items'], ['gold', ''], ['book', 'Books'], ['door', 'Doors'], ['container', 'Containers'], ['thing', 'Things'], ['place', 'Places']];
  const where = c => c.where && c.where.length ? ' · ' + c.where.map(w => w.name).slice(0, 2).join(', ') : '';
  let cast = '';
  for (const [k, label] of kinds){
    const cs = r.cast.filter(c => c.kind === k);
    if (!cs.length) continue;
    if (label) cast += `<span class="k">${label}</span>`;
    cast += cs.map(c => `<span class="qbchip ${k}" data-cast="${esc(c.id.toLowerCase())}" title="${esc(c.id)}${esc(where(c))}">${esc(c.name)}</span>`).join('');
  }
  return cast;
}

// ---------- The rail: the stages on one line, each move written in the gap before the stage it sets ----------
// No line is drawn for a move to the next stage: it is the words in the gap. A move that skips stages is
// an arc over the rail. Where a stage can lead to two next stages, the second runs on a rail below and
// comes back where it meets the main line again. Moves that need no stage sit in the band below.
// Pointing at a move, a stage or a cast member lights what it touches and dims the rest.
function qbRail(q, r){
  const box = $('#q-board');
  const frames = r.frames.slice().sort((a, b) => a.index - b.index), moves = r.moves;
  if (!frames.length){ box.innerHTML = `<div class="card msg">This quest has no stages and nothing moves it.</div>`; return; }
  const fits = (v, nd) => ({'=': v === nd.value, '!=': v !== nd.value, '>': v > nd.value, '>=': v >= nd.value, '<': v < nd.value, '<=': v <= nd.value})[nd.op];
  const stages = frames.map(f => f.index), first = stages[0];
  const nodes = ['start', ...stages], col = {}; nodes.forEach((n, i) => { col[n] = i; });
  const byIdx = {}; frames.forEach(f => { byIdx[f.index] = f; });
  const order = n => n === 'start' ? -1 : n;
  // each move: where it starts (the first stage its needs fit), and whether it is an edge, any-time, or never
  const said = {};   // lines that only need a stage (set none): counted under the first stage they fit
  for (const m of moves){
    m._to = m.sets[0];
    const f = m.needs.length ? [0, ...stages].find(s => m.needs.every(nd => fits(s, nd))) : 0;
    m._from = f === undefined ? null : f === 0 ? 'start' : f;
    if (m._to === undefined){ m._kind = 'said'; if (m._from != null) said[m._from] = (said[m._from] || 0) + 1; continue; }
    if (!m.needs.length){ m._kind = m._to === first ? 'edge' : 'any'; continue; }
    m._kind = m._from == null ? 'never' : 'edge';
  }
  const edges = moves.filter(m => m._kind === 'edge' && m._to !== m._from && byIdx[m._to] !== undefined);
  const pred = {}; for (const n of nodes) pred[n] = new Set();
  for (const m of edges) pred[m._to].add(m._from);
  // rails: a stage joins the rail whose last stage leads to it; led to only from the middle of a rail, it starts one below
  // (a move written from an earlier stage whose tests still hold at a side rail's last stage leads from there too)
  const leads = (p, s) => edges.some(m => m._to === s && (m._from === p || (p !== 'start' && m.needs.length && order(p) < s && m.needs.every(nd => fits(p, nd)))));
  const rails = [{nodes: ['start'], open: true, from: null}], railOf = {start: 0}, joins = [];
  for (const s of stages){
    const ps = [...pred[s]].filter(p => order(p) < s);
    const tails = rails.map((rl, i) => rl.open && leads(rl.nodes[rl.nodes.length - 1], s) ? i : -1).filter(i => i >= 0);
    if (tails.length){
      rails[tails[0]].nodes.push(s); railOf[s] = tails[0];
      for (const j of tails.slice(1)){ rails[j].open = false; joins.push({rail: j, at: s, tail: rails[j].nodes[rails[j].nodes.length - 1]}); }
    } else if (ps.length){
      const from = ps.reduce((a, b) => order(a) > order(b) ? a : b);
      rails.push({nodes: [s], open: true, from}); railOf[s] = rails.length - 1;
    } else { rails[0].nodes.push(s); railOf[s] = 0; }
  }
  // which gap each edge is written in: before its stage on the stage's rail (from the rail's previous stage
  // or the stage it branched from), or on a joining rail before the stage it comes back to; the rest are arcs
  const gaps = {}, gapOf = {};   // "row:col" -> [move idx]
  const put = (row, c, n) => { const k = row + ':' + c; (gaps[k] = gaps[k] || []).push(n); gapOf[n] = k; };
  const railPrev = {};
  rails.forEach((rl, i) => rl.nodes.forEach((n, k) => { railPrev[n] = k ? rl.nodes[k - 1] : rl.from; }));
  const holds = (m, p) => m._from === p || (p != null && p !== 'start' && m.needs.length && order(p) < m._to && m.needs.every(nd => fits(p, nd)));
  moves.forEach((m, n) => {
    if (!edges.includes(m)) return;
    if (holds(m, railPrev[m._to])){ put(railOf[m._to], col[m._to] - 1, n); m._rp = railPrev[m._to]; return; }
    const j = joins.find(j => j.at === m._to && holds(m, j.tail));
    if (j){ put(j.rail, col[m._to] - 1, n); m._rp = j.tail; }
  });
  // a move that needs no stage, when nothing else is written before the stage it sets, is written there
  moves.forEach((m, n) => {
    if (m._kind !== 'any' || byIdx[m._to] === undefined || railPrev[m._to] == null) return;
    const k = railOf[m._to] + ':' + (col[m._to] - 1);
    if (!gaps[k] || gaps[k].every(i => moves[i]._kind === 'any')){ put(railOf[m._to], col[m._to] - 1, n); m._kind = 'anygap'; }
  });
  const arcs = edges.map((m, _) => moves.indexOf(m)).filter(n => gapOf[n] === undefined);
  // the geometry: columns are the stages in order, rows are the rails
  const NW = 150, GW = 210, PAD = 24, R = 17, LH = 21, TXT = 86, ARC = 58;
  const cx = c => PAD + c * (NW + GW) + NW / 2;
  const stack = rails.map(() => 1);
  for (const [k, lst] of Object.entries(gaps)) stack[+k.split(':')[0]] = Math.max(stack[+k.split(':')[0]], lst.length);
  const railY = [], rowH = [];
  let y = 10;
  rails.forEach((rl, i) => { const st = Math.max(stack[i] * LH, 2 * R); railY[i] = y + ARC + st / 2; rowH[i] = ARC + st + TXT; y += rowH[i]; });
  const W = PAD * 2 + nodes.length * (NW + GW) - GW, bandY = y + 10;
  const bad = frames.filter(f => !f.reachable).length, dead = frames.filter(f => f.deadend).length;
  // what the player holds by a stage, in a line
  const stateLine = f => {
    const s = f.state, parts = [];
    if (s.bag.length) parts.push('🎒 ' + s.bag.map(b => (b.n > 1 ? b.n + ' ' : '') + b.name).join(', '));
    for (const [k, h] of Object.entries(s.with || {})) parts.push(`${qbName(k)} with ${h}`);
    if (s.dead.length) parts.push('☠ ' + s.dead.join(', '));
    return parts.join(' · ');
  };
  const node = n => {
    const c = col[n], x = cx(c) - NW / 2, yy = railY[railOf[n]] - R;
    if (n === 'start') return `<div class="qrn start" data-qn="start" style="left:${x}px;top:${yy}px;width:${NW}px"><div class="dot">Start</div><div class="txt">before the first entry</div>${said.start ? `<div class="st said" title="${said.start} lines said before it starts that move it nowhere">💬 ${said.start}</div>` : ''}</div>`;
    const f = byIdx[n], st = stateLine(f);
    return `<div class="qrn ${f.finished ? 'fin' : ''} ${!f.reachable ? 'bad' : f.deadend ? 'dead' : ''}" data-qn="${n}" style="left:${x}px;top:${yy}px;width:${NW}px">
      <div class="dot" title="${f.finished ? 'Finishes the quest' : 'Stage ' + n}">${n}</div><button class="qbadd" data-qadd="${n}" title="Add what brings the player to this stage">+</button>
      <div class="txt" title="${esc(f.text)}">${esc(f.missing ? '(no journal entry)' : f.text)}</div>
      ${!f.reachable ? '<div class="flag">⚠ nothing leads here</div>' : f.deadend ? '<div class="flag">⛔ nothing leads on</div>' : st ? `<div class="st" title="${esc(st)}">${esc(st)}</div>` : ''}${said[n] ? `<div class="st said" title="${said[n]} line${said[n] > 1 ? 's' : ''} said from this stage on that move it nowhere">💬 ${said[n]}</div>` : ''}</div>`;
  };
  const fx = m => [...m.gives.map(g => '+ ' + (g.n > 1 ? g.n + ' ' : '') + qbName(g.id)), ...m.takes.map(g => '− ' + (g.n > 1 ? g.n + ' ' : '') + qbName(g.id))];
  const qop = op => ({'=': '=', '!=': '≠', '>=': '≥', '<=': '≤'}[op] || op);
  const other = m => [...(m.waits || []).map(w => `<span class="wq" data-wq="${esc(w.quest)}" title="Needs ${esc(w.quest)} ${qop(w.op)} ${w.value}: open that quest">⏳ ${esc(w.quest)} ${qop(w.op)} ${w.value}</span>`),
    ...(m.also || []).map(w => `<span class="wq" data-wq="${esc(w.quest)}" title="Also sets ${esc(w.quest)} to ${w.stage}: open that quest">→ ${esc(w.quest)} ${w.stage}</span>`)].join('');
  const tip = m => `${qbLabel(m)}
${m.via === 'line' ? (m.text || '(no text)') : m.text || 'always'}
${m.src}${m.via === 'script' ? ' · script ' + m.script : ''}${m._rp !== undefined && m._rp !== m._from ? `
(possible from stage ${m._from} on)` : ''}`;
  const move = (n, extra, style) => { const m = moves[n];
    return `<div class="qrm ${m.via} ${m.mine ? 'mine' : ''} ${extra}" data-qm="${n}" style="${style}" title="${esc(tip(m))}"><span class="v">${esc(qbLabel(m))}</span>${fx(m).map(t => `<span class="fx">${esc(t)}</span>`).join('')}${other(m)}${m.choices && m.choices.length ? `<span class="fx">${m.choices.length} choices</span>` : ''}${m._kind === 'anygap' ? '<span class="fx">any time</span>' : ''}</div>`; };
  let h = '';
  for (const n of nodes) h += node(n);
  for (const [k, lst] of Object.entries(gaps)){
    const [row, c] = k.split(':').map(Number), x = cx(c) + NW / 2 + 8, top = railY[row] - lst.length * LH / 2;
    lst.forEach((n, i) => { h += move(n, 'gap', `left:${x}px;top:${top + i * LH}px;width:${GW - 16}px`); });
  }
  // stages nothing is written before: say so in the gap
  for (const s of stages){
    const row = railOf[s], k = row + ':' + (col[s] - 1);
    for (const j of joins) if (j.at === s && !gaps[j.rail + ':' + (col[s] - 1)]) h += `<div class="qrm flag faint" style="left:${cx(col[s] - 1) + NW / 2 + 8}px;top:${railY[j.rail] - LH / 2}px;width:${GW - 16}px">the same way as above</div>`;
    if (!gaps[k] && byIdx[s].reachable && railPrev[s] != null && !arcs.some(n => moves[n]._to === s)) h += `<div class="qrm flag faint" style="left:${cx(col[s] - 1) + NW / 2 + 8}px;top:${railY[row] - LH / 2}px;width:${GW - 16}px">only from the band below</div>`;
  }
  // arcs: grouped by where they go from and to, their words at the top of the arc
  const groups = {};
  for (const n of arcs){ const m = moves[n], k = m._from + '>' + m._to; (groups[k] = groups[k] || []).push(n); }
  const arcGeom = {};
  for (const [k, lst] of Object.entries(groups)){
    const m = moves[lst[0]], c1 = col[m._from], c2 = col[m._to], r1 = railOf[m._from], r2 = railOf[m._to];
    const back = c2 < c1;
    const x1 = cx(c1), x2 = cx(c2);
    const rise = back ? -(TXT + 24) : 30 + 9 * Math.min(6, Math.abs(c2 - c1));
    const y1 = railY[r1] + (back ? R : -R), y2 = railY[r2] + (back ? R : -R);
    const top = Math.min(y1, y2) - rise, xm = (x1 + x2) / 2;
    arcGeom[k] = {d: `M${x1},${y1} C${x1},${top} ${x2},${top} ${x2},${y2}`, back, lx: xm, ly: Math.min(y1, y2) - rise * 0.75 - lst.length * LH + (back ? rise * 0.75 + 4 : 0)};
    lst.forEach((n, i) => { h += move(n, 'arc' + (back ? ' back' : ''), `left:${xm - (GW - 16) / 2}px;top:${arcGeom[k].ly + i * LH}px;width:${GW - 16}px`); });
  }
  // the band: moves that need no stage, and moves whose needs fit no stage
  const band = moves.map((m, n) => [m, n]).filter(([m]) => m._kind === 'any' || m._kind === 'never');
  if (band.length) h += `<div class="qrband" style="top:${bandY}px;width:${W - PAD * 2}px"><span class="k">At any time</span>${band.map(([m, n]) =>
    `<div class="qrm band ${m.via} ${m.mine ? 'mine' : ''} ${m._kind === 'never' ? 'never' : ''}" data-qm="${n}" title="${esc(tip(m))}${m._kind === 'never' ? '\n⚠ its stage tests fit no stage of the quest' : ''}"><span class="v">${esc(qbLabel(m))}</span>${fx(m).map(t => `<span class="fx">${esc(t)}</span>`).join('')}${other(m)}<span class="to">→ ${m._to}</span>${m._kind === 'never' ? '<span class="fx warn">never fits</span>' : ''}</div>`).join('')}</div>`;
  box.innerHTML = `<div class="qbcast" id="qb-cast">${qbCastRow(r) || '<span class="msg">no cast read</span>'}</div>
    <div class="cvbar"><div class="seg"><button data-zoom="-1" title="Smaller">−</button><button data-zoom="0" title="Actual size">${Math.round(CV.zoom * 100)}%</button><button data-zoom="1" title="Larger">+</button></div>
    ${qbViewSeg()}
    <button class="btn sm" id="qb-stage" title="A new journal entry">+ Stage</button>
    <button class="btn sm" id="qb-pick" title="Pick the people, things and places this quest is about">+ Cast</button>
    <span class="msg" title="Each stage's number sits on the rail; what brings the player to it is written in the gap before it. An arc skips stages. A second rail is another way through. Point at anything to see what it touches.">${bad ? `<b style="color:var(--red)">${bad} nothing leads to.</b> ` : ''}${dead ? `<b style="color:var(--amber)">${dead} dead end${dead > 1 ? 's' : ''}.</b> ` : ''}${rails.length > 1 ? `${rails.length - 1} other way${rails.length > 2 ? 's' : ''} through. ` : ''}${r.more ? `(${r.more} more lines not shown.)` : ''}</span></div>
    <div id="qb-form"></div>
    <div class="cvcanvas" id="cv-canvas" style="height:calc(100vh - 330px)"><div class="cvsizer" id="cv-sizer"><div class="cvinner qrail" id="cv-inner" style="transform:scale(${CV.zoom});width:${W}px;height:${bandY + 40}px"><svg class="cvedges" id="cv-edges"></svg>${h}</div></div></div>`;
  cvBindMapBar(null, box);
  box.querySelectorAll('[data-qview]').forEach(b => b.onclick = () => qbView(q, b.dataset.qview));
  const inner = $('#cv-inner'), svg = $('#cv-edges');
  const bd = inner.querySelector('.qrband'); if (bd) inner.style.height = bandY + bd.offsetHeight + 30 + 'px';
  // the rails and the arcs
  const paths = [];
  rails.forEach((rl, i) => {
    const yy = railY[i];
    rl.nodes.forEach((n, k) => {
      if (!k) return;
      const a = rl.nodes[k - 1], dashed = n !== 'start' && !byIdx[n].reachable;
      paths.push(`<path class="rail ${dashed ? 'gone' : ''}" data-rail="${i}" d="M${cx(col[a]) + R},${yy} L${cx(col[n]) - R},${yy}"/>`);
    });
    if (rl.from != null){   // a branch: down from the stage it leaves, into the gap before its first stage
      const x0 = cx(col[rl.from]) + 10, y0 = railY[railOf[rl.from]] + 13, x1 = cx(col[rl.nodes[0]] - 1) + NW / 2;
      paths.push(`<path class="rail" data-rail="${i}" d="M${x0},${y0} C${x0},${yy} ${x1 - 70},${yy} ${x1},${yy} L${cx(col[rl.nodes[0]]) - R},${yy}"/>`);
    }
  });
  for (const j of joins){   // back up to the main line, after the gap that holds its last move
    const yy = railY[j.rail], x0 = cx(col[j.tail]) + R, x1 = cx(col[j.at]) - NW / 2, x2 = cx(col[j.at]) - 10, y2 = railY[railOf[j.at]] + 13;
    paths.push(`<path class="rail" data-rail="${j.rail}" d="M${x0},${yy} L${x1},${yy} C${x1 + 70},${yy} ${x2},${y2 + 30} ${x2},${y2}"/>`);
  }
  for (const [k, lst] of Object.entries(groups)) for (const n of lst) paths.push(`<path class="${arcGeom[k].back ? 'back' : 'set'}" data-er="${n}" d="${arcGeom[k].d}"/>`);
  svg.setAttribute('width', inner.offsetWidth); svg.setAttribute('height', inner.offsetHeight); svg.innerHTML = paths.join('');
  cvSize();
  // lighting: a set of moves lights them, their stages and their cast; everything else dims
  const movesAt = n => new Set(moves.map((m, i) => [m, i]).filter(([m]) => String(m._from) === String(n) && m._kind === 'edge' || String(m._to) === String(n)).map(([, i]) => i));
  const movesWith = id => new Set(moves.map((m, i) => [m, i]).filter(([m]) => qbCastOf(m).includes(id)).map(([, i]) => i));
  let held = null;
  const light = ms => {
    const nodesOn = new Set(), castOn = new Set();
    if (ms) for (const i of ms){ const m = moves[i]; if (m._kind === 'edge') nodesOn.add(String(m._from)); nodesOn.add(String(m._to)); for (const c of qbCastOf(m)) castOn.add(c); }
    inner.querySelectorAll('[data-qm]').forEach(el => { const on = ms && ms.has(+el.dataset.qm); el.classList.toggle('hot', !!on); el.classList.toggle('dim', !!ms && !on); });
    inner.querySelectorAll('[data-qn]').forEach(el => { const on = ms && nodesOn.has(el.dataset.qn); el.classList.toggle('hot', !!on); el.classList.toggle('dim', !!ms && !on); });
    svg.querySelectorAll('path[data-er]').forEach(p => { const on = ms && ms.has(+p.dataset.er); p.classList.toggle('hot', !!on); p.classList.toggle('dim', !!ms && !on); });
    svg.querySelectorAll('path.rail').forEach(p => p.classList.toggle('dim', !!ms));
    box.querySelectorAll('[data-cast]').forEach(ch => { const on = ms && castOn.has(ch.dataset.cast) || (held && held.cast === ch.dataset.cast); ch.classList.toggle('on', !!on); ch.classList.toggle('dim', !!ms && !on); });
  };
  const rest = () => light(held ? held.set : null);
  inner.querySelectorAll('[data-qm]').forEach(el => {
    el.onmouseenter = () => light(new Set([+el.dataset.qm]));
    el.onmouseleave = rest;
    el.onclick = e => { if (e.target.closest('[data-wq]')) return; const m = moves[+el.dataset.qm]; if (m.via === 'line') cvEditLine(m.topic, m.inam); else if (typeof sOpen === 'function'){ showView('scripts'); sOpen(m.script); } };
  });
  inner.querySelectorAll('[data-qn]').forEach(el => { el.onmouseenter = () => light(movesAt(el.dataset.qn)); el.onmouseleave = rest; });
  inner.querySelectorAll('[data-wq]').forEach(el => { el.onclick = e => { e.stopPropagation(); dOpen('quest', el.dataset.wq.toLowerCase()); }; });
  box.querySelectorAll('[data-cast]').forEach(ch => {
    ch.onclick = () => { const id = ch.dataset.cast; held = held && held.cast === id ? null : {cast: id, set: movesWith(id)}; QB.hot = held ? id : null; rest(); };
    ch.ondblclick = () => { const c = QB.cast[ch.dataset.cast]; if (c && (c.kind === 'person' || c.kind === 'creature')) dOpen('npc', c.id); };
  });
  cvPan($('#cv-canvas'));
  $('#qb-stage').onclick = () => qbStageForm(q, r);
  $('#qb-pick').onclick = () => qbCastForm(q, r);
  inner.querySelectorAll('[data-qadd]').forEach(b => b.onclick = e => { e.stopPropagation(); qbMoveForm(q, r, +b.dataset.qadd); });
}

// ---------- The map: every move as a card under the stage it sets, an arrow from the stage it starts at ----------
function qbMap(q, r){
  const box = $('#q-board');
  const frames = r.frames, moves = r.moves;
  const fits = (v, nd) => ({'=': v === nd.value, '!=': v !== nd.value, '>': v > nd.value, '>=': v >= nd.value, '<': v < nd.value, '<=': v <= nd.value})[nd.op];
  // where a move starts: the first frame its needs fit, else the start
  const from = m => { if (!m.needs.length) return 'start'; const f = frames.find(f => m.needs.every(nd => fits(f.index, nd))); return f ? f.index : 'start'; };
  for (const m of moves){ m._from = from(m); m._to = m.sets[0]; }
  const cols = ['start', ...frames.map(f => f.index)];
  if (!frames.length){ box.innerHTML = `<div class="card msg">This quest has no stages and nothing moves it.</div>`; return; }
  const cast = qbCastRow(r);
  const bad = frames.filter(f => !f.reachable).length, dead = frames.filter(f => f.deadend).length;
  const head = f => f === 'start' ? `<div class="qh start" data-qc="start"><b>Start</b><br><span class="msg">before the first entry</span></div>`
    : `<div class="qh ${f.finished ? 'fin' : ''} ${!f.reachable ? 'bad' : f.deadend ? 'dead' : ''}" data-qc="${f.index}" title="${esc(f.text)}"><button class="qbadd" data-qadd="${f.index}" title="Add what brings the player to this stage">+</button><b>${f.index}</b> ${esc(f.missing ? '(no journal entry)' : f.text.slice(0, 110))}
       ${!f.reachable ? '<span class="flag">⚠ nothing leads here</span>' : f.deadend ? '<span class="flag">⛔ nothing leads on</span>' : ''}</div>`;
  const state = f => {
    if (f === 'start') return '<div class="qbstate">—</div>';
    const s = f.state, parts = [];
    if (s.bag.length) parts.push(`<span class="hold">🎒 ${s.bag.map(b => (b.n > 1 ? b.n + ' ' : '') + esc(b.name)).join(', ')}</span>`);
    for (const [k, h] of Object.entries(s.with || {})) parts.push(`<span class="hold">${esc(qbName(k))} <b>with ${esc(h)}</b></span>`);
    if (s.dead.length) parts.push(`<span class="hold">☠ ${s.dead.map(esc).join(', ')}</span>`);
    return `<div class="qbstate" data-qs="${f.index}">${parts.join('') || '<span class="msg">nothing yet</span>'}</div>`;
  };
  const card = (m, n) => `<div class="qcard ${m.mine ? 'mine' : ''} ${m.via}" data-qcard="${n}" data-who="${esc((m.who || '').toLowerCase())}" title="${esc(m.src)}${m.via === 'script' ? ' · script ' + esc(m.script) : ''}">
      <div class="verb">${esc(qbLabel(m))}</div>
      <div class="cvt">${m.via === 'line' ? esc(m.text) || '<i>(no text)</i>' : esc(m.text || 'always')}</div>
      <div class="cvchips">${m.gives.map(g => `<span>+ ${g.n > 1 ? g.n + ' ' : ''}${esc(qbName(g.id))}</span>`).join('')}${m.takes.map(g => `<span>− ${g.n > 1 ? g.n + ' ' : ''}${esc(qbName(g.id))}</span>`).join('')}
        ${m.learns && m.learns.length ? `<span>learns ${m.learns.length}</span>` : ''}${m.choices && m.choices.length ? `<span>${m.choices.length} choices</span>` : ''}${m.other ? `<span>+${m.other} test${m.other > 1 ? 's' : ''}</span>` : ''}</div></div>`;
  let h = `<div class="qbcast" id="qb-cast">${cast || '<span class="msg">no cast read</span>'}</div>
    <div class="cvbar"><div class="seg"><button data-zoom="-1" title="Smaller">−</button><button data-zoom="0" title="Actual size">${Math.round(CV.zoom * 100)}%</button><button data-zoom="1" title="Larger">+</button></div>
    ${qbViewSeg()}
    <button class="btn sm" id="qb-tidy" title="Put every move back under its stage">↺ Tidy up</button>
    <button class="btn sm" id="qb-stage" title="A new journal entry">+ Stage</button>
    <button class="btn sm" id="qb-pick" title="Pick the people, things and places this quest is about">+ Cast</button>
    <span class="msg">Frames are the stages. Under each, what brings the player there, with an arrow from the stage it starts at. ${bad ? `<b style="color:var(--red)">${bad} nothing leads to.</b> ` : ''}${dead ? `<b style="color:var(--amber)">${dead} dead end${dead > 1 ? 's' : ''}.</b> ` : ''}${r.more ? `(${r.more} more lines not shown.)` : ''}</span></div>
    <div id="qb-form"></div>
    <div class="cvcanvas" id="cv-canvas" style="height:calc(100vh - 330px)"><div class="cvsizer" id="cv-sizer"><div class="cvinner" id="cv-inner" style="transform:scale(${CV.zoom})"><svg class="cvedges" id="cv-edges"></svg>
    <div class="qboard" style="grid-template-columns:repeat(${cols.length}, 250px)">${cols.map(c => head(c === 'start' ? 'start' : frames.find(f => f.index === c))).join('')}
    ${cols.map(c => state(c === 'start' ? 'start' : frames.find(f => f.index === c))).join('')}
    ${cols.map(c => `<div class="qcell" data-qcell="${c}">${moves.map((m, n) => m._to === c ? card(m, n) : '').join('')}</div>`).join('')}</div></div></div></div>`;
  box.innerHTML = h;
  cvBindMapBar(null, box);
  box.querySelectorAll('[data-qview]').forEach(b => b.onclick = () => qbView(q, b.dataset.qview));
  const inner = $('#cv-inner'), svg = $('#cv-edges');
  inner.querySelectorAll('.qcell').forEach(el => { el.style.height = el.offsetHeight + 'px'; });
  const saveKey = 'qboard:' + q.key;
  cvDraggable(inner, [...inner.querySelectorAll('[data-qcard]')].map(el => { const m = moves[+el.dataset.qcard]; return {el, key: m.via + '|' + (m.topic || m.script) + '|' + m.inam}; }), () => draw(), saveKey);
  const tidy = $('#qb-tidy'); if (tidy) tidy.onclick = () => { try { localStorage.removeItem(saveKey); } catch (e){} qbBoard(q); };
  draw();
  function draw(){
    const W = inner.scrollWidth, H = inner.scrollHeight; svg.setAttribute('width', W); svg.setAttribute('height', H);
    const paths = [];
    inner.querySelectorAll('[data-qcard]').forEach(el => {
      const m = moves[+el.dataset.qcard], a = cvPos(el, inner);
      const hd = inner.querySelector(`[data-qc="${m._from}"]`); if (!hd) return;
      const b = cvPos(hd, inner);
      const x1 = b.x + Math.min(40, b.w / 2), y1 = b.y + b.h, x2 = a.x, y2 = a.y + 16;
      paths.push(`<path class="set" data-er="${el.dataset.qcard}" d="M${x1},${y1} C${x1},${y1 + 60} ${x2 - 60},${y2} ${x2},${y2}"/>`);
      // and on to the frame it sets (short, into the header above its column)
      const th = inner.querySelector(`[data-qc="${m._to}"]`);
      if (th){ const t = cvPos(th, inner); const x3 = a.x + a.w, y3 = a.y + 16, x4 = t.x + t.w - 30, y4 = t.y + t.h;
        paths.push(`<path class="learn" data-er="${el.dataset.qcard}" d="M${x3},${y3} C${x3 + 30},${y3} ${x4},${y4 + 40} ${x4},${y4}"/>`); }
    });
    svg.innerHTML = paths.join('');
    cvSize();
  }
  inner.querySelectorAll('[data-qcard]').forEach(el => {
    el.onmouseenter = () => cvHot(el.dataset.qcard, null);
    el.onmouseleave = () => cvHot(null, null);
    el.onclick = () => { const m = moves[+el.dataset.qcard]; if (m.via === 'line') cvEditLine(m.topic, m.inam); else if (typeof sOpen === 'function'){ showView('scripts'); sOpen(m.script); } };
  });
  // a cast member lights the moves it is in
  box.querySelectorAll('[data-cast]').forEach(ch => {
    ch.onclick = () => {
      const id = ch.dataset.cast, on = QB.hot === id ? null : id; QB.hot = on;
      box.querySelectorAll('[data-cast]').forEach(x => { x.classList.toggle('on', x.dataset.cast === on); x.classList.toggle('dim', !!on && x.dataset.cast !== on); });
      inner.querySelectorAll('[data-qcard]').forEach(el => {
        const m = moves[+el.dataset.qcard];
        const inIt = on && qbCastOf(m).includes(on);
        el.classList.toggle('hit', !!inIt); el.style.opacity = on && !inIt ? .35 : '';
      });
    };
    ch.ondblclick = () => { const c = QB.cast[ch.dataset.cast]; if (c && (c.kind === 'person' || c.kind === 'creature')) dOpen('npc', c.id); };
  });
  cvPan($('#cv-canvas'));
  // making: a stage, the cast, a move under a stage
  $('#qb-stage').onclick = () => qbStageForm(q, r);
  $('#qb-pick').onclick = () => qbCastForm(q, r);
  inner.querySelectorAll('[data-qadd]').forEach(b => b.onclick = e => { e.stopPropagation(); qbMoveForm(q, r, +b.dataset.qadd); });
}

// ---------------------------------------------------------------- making
const QB_VERBS = [['talk', 'Talk to someone about a topic'], ['meet', 'Meet someone (their greeting)'], ['bring', 'Bring an item to someone'],
  ['show', 'Show an item to someone'], ['kill', 'Kill someone'], ['read', 'Read a book or note'], ['open', 'Open a door or chest'], ['use', 'Use a thing'],
  ['take', 'Pick an item up'], ['enter', 'Enter a place'], ['approach', 'Come near someone or something'], ['wait', 'Wait some days']];
function qbMoveForm(q, r, to){
  const box = $('#qb-form'); if (!box) return;
  const people = r.cast.filter(c => c.kind === 'person' || c.kind === 'creature'), things = r.cast.filter(c => !['person', 'creature', 'place', 'gold'].includes(c.kind));
  const items = r.cast.filter(c => ['item', 'book', 'gold'].includes(c.kind)), places = r.cast.filter(c => c.kind === 'place');
  const before = r.frames.filter(f => f.index < to);
  const opt = (lst, sel) => lst.map(c => `<option value="${esc(c.id)}" ${sel === c.id ? 'selected' : ''}>${esc(c.name)}</option>`).join('');
  const frm = before.length ? before[before.length - 1].index : 0;
  box.innerHTML = `<div class="card qbform"><div class="qbrow"><b>To stage ${to}:</b> the player
      <select class="inp" id="qm-verb">${QB_VERBS.map(([k, t]) => `<option value="${k}">${t}</option>`).join('')}</select>
      from <select class="inp" id="qm-from"><option value="0">before it starts</option>${before.map(f => `<option value="${f.index}" ${f.index === frm ? 'selected' : ''}>stage ${f.index}</option>`).join('')}</select></div>
    <div class="qbrow" data-for="talk meet bring show kill approach"><span id="qm-wholbl">Who</span> <select class="inp" id="qm-who">${opt(people)}<option value="">(type an ID)</option></select><input class="inp" id="qm-whoid" placeholder="ID" style="width:150px;display:none"></div>
    <div class="qbrow" data-for="read open use take approach">Thing <select class="inp" id="qm-thing">${opt(things)}<option value="">(type an ID)</option></select><input class="inp" id="qm-thingid" placeholder="ID" style="width:150px;display:none"></div>
    <div class="qbrow" data-for="talk bring show">Topic <input class="inp" id="qm-topic" placeholder="the words the player clicks" style="width:200px"></div>
    <div class="qbrow" data-for="bring show">Item <select class="inp" id="qm-item">${opt(items)}<option value="">(type an ID)</option></select><input class="inp" id="qm-itemid" placeholder="ID" style="width:150px;display:none"> × <input class="inp" id="qm-itemn" type="number" value="1" min="1" style="width:60px"></div>
    <div class="qbrow" data-for="talk meet bring show">They say <textarea class="inp" id="qm-say" rows="2" style="flex:1" placeholder="What they answer. Leave empty to write it later in the line editor."></textarea></div>
    <div class="qbrow" data-for="talk meet bring show">Reward <input class="inp" id="qm-give" placeholder="item ID (gold_001 for gold)" style="width:180px" list="qm-items"> × <input class="inp" id="qm-given" type="number" value="1" min="1" style="width:60px">
      <span style="margin-left:10px">Teaches topic</span> <input class="inp" id="qm-learn" placeholder="a topic to ask about next" style="width:180px"></div>
    <div class="qbrow" data-for="enter">Place <input class="inp" id="qm-place" placeholder="cell name, or its start (Vivec)" style="width:220px" list="qm-places"></div>
    <div class="qbrow" data-for="approach">Within <input class="inp" id="qm-dist" type="number" value="400" style="width:80px"> units</div>
    <div class="qbrow" data-for="wait">Days <input class="inp" id="qm-days" type="number" value="1" min="1" style="width:70px"></div>
    <datalist id="qm-items">${items.map(c => `<option value="${esc(c.id)}">${esc(c.name)}</option>`).join('')}</datalist>
    <datalist id="qm-places">${places.map(c => `<option value="${esc(c.id)}">`).join('')}</datalist>
    <div class="actions" style="margin:6px 0 0"><button class="btn primary sm" id="qm-ok">Write it</button><button class="btn sm" id="qm-no">Cancel</button><span class="msg" id="qm-note"></span></div></div>`;
  const show = () => {
    const v = $('#qm-verb').value;
    box.querySelectorAll('[data-for]').forEach(el => el.style.display = el.dataset.for.split(' ').includes(v) ? '' : 'none');
    $('#qm-wholbl').textContent = v === 'kill' ? 'Who dies' : v === 'approach' ? 'Who' : 'Who';
    $('#qm-note').textContent = {talk: 'A line of theirs on the topic, at the top, that needs the stage it starts from and sets the next.',
      meet: 'A greeting of theirs that needs the stage and sets the next.', bring: 'The line needs the item, and takes it.', show: 'The line needs the item; they keep it.',
      kill: 'A short script on them: when they die, the stage is set.', read: 'A script on the book: reading it sets the stage.', open: 'A script on it: opening it sets the stage.',
      use: 'A script on it: using it sets the stage.', take: 'A script on the item: picking it up sets the stage.', enter: "The quest's watcher script sets the stage when the player is in the place.",
      approach: "The watcher sets the stage when the player comes near.", wait: 'The watcher counts the days from reaching the stage it starts from.'}[v] || '';
  };
  $('#qm-verb').onchange = show; show();
  for (const [sel, inp] of [['#qm-who', '#qm-whoid'], ['#qm-thing', '#qm-thingid'], ['#qm-item', '#qm-itemid']]){
    const s = $(sel), i = $(inp); if (!s) continue;
    const upd = () => { i.style.display = s.value === '' ? '' : 'none'; };
    s.onchange = upd; upd();
  }
  $('#qm-no').onclick = () => { box.innerHTML = ''; };
  $('#qm-ok').onclick = async () => {
    if (!await needProject()) return;
    const v = $('#qm-verb').value, pick = (sel, inp) => $(sel).value || $(inp).value.trim();
    const mv = {verb: v, to, from: +$('#qm-from').value, who: pick('#qm-who', '#qm-whoid'), thing: pick('#qm-thing', '#qm-thingid'),
      topic: $('#qm-topic').value, say: $('#qm-say').value, place: $('#qm-place').value, dist: +$('#qm-dist').value, days: +$('#qm-days').value,
      items: [{id: pick('#qm-item', '#qm-itemid'), n: +$('#qm-itemn').value}], gives: $('#qm-give').value.trim() ? [{id: $('#qm-give').value.trim(), n: +$('#qm-given').value}] : [],
      learns: $('#qm-learn').value.trim() ? [$('#qm-learn').value.trim()] : []};
    if (['read', 'open', 'use', 'take'].includes(v)) mv.who = '';
    $('#qm-ok').disabled = true;
    try { await post('/api/quest/move', {key: q.key, move: mv}); toast('Written'); box.innerHTML = ''; await qbBoard(q); await afterChange(); }
    catch (e){ toast(e.message, true); $('#qm-ok').disabled = false; }
  };
}
function qbStageForm(q, r){
  const box = $('#qb-form'); if (!box) return;
  const last = r.frames.length ? Math.max(...r.frames.map(f => f.index)) : 0;
  box.innerHTML = `<div class="card qbform"><div class="qbrow"><b>New stage</b> <input class="inp" id="qs-index" type="number" value="${last + 10}" style="width:80px">
      <textarea class="inp" id="qs-text" rows="2" style="flex:1" placeholder="What the player writes in their journal on reaching it."></textarea>
      <label><input type="checkbox" id="qs-fin"> Finished</label></div>
    <div class="actions" style="margin:6px 0 0"><button class="btn primary sm" id="qs-ok">Add</button><button class="btn sm" id="qs-no">Cancel</button></div></div>`;
  $('#qs-no').onclick = () => { box.innerHTML = ''; };
  $('#qs-ok').onclick = async () => {
    if (!await needProject()) return;
    try { await post('/api/quest/stage', {key: q.key, index: +$('#qs-index').value, text: $('#qs-text').value, finished: $('#qs-fin').checked}); toast('Stage added'); box.innerHTML = ''; await dReload(); }
    catch (e){ toast(e.message, true); }
  };
}
function qbCastForm(q, r){
  const box = $('#qb-form'); if (!box) return;
  const pinned = r.cast.filter(c => c.pinned).map(c => c.id);
  box.innerHTML = `<div class="card qbform"><div class="qbrow"><b>Cast</b> <input class="inp" id="qc-q" placeholder="Search people, creatures, items, books, doors…" style="flex:1"><button class="btn sm" id="qc-no">Close</button></div>
    <div id="qc-hits" class="qbcast"></div><div class="msg">Click to add to the cast. People and things a move uses are in the cast already; a pick stays with the quest until a move uses it.</div></div>`;
  const inp = $('#qc-q'), hits = $('#qc-hits');
  let t = 0;
  inp.oninput = () => { clearTimeout(t); t = setTimeout(async () => {
    const qq = inp.value.trim(); if (!qq){ hits.innerHTML = ''; return; }
    try {
      const res = await api('/api/search?' + new URLSearchParams({q: qq, types: 'NPC_,CREA,MISC,BOOK,WEAP,ARMO,CLOT,ALCH,INGR,DOOR,ACTI,CONT,CELL', limit: 24}));
      hits.innerHTML = res.rows.map(x => `<span class="qbchip ${x.type === 'NPC_' ? 'person' : x.type === 'CELL' ? 'place' : ''}" data-add="${esc(x.id)}" title="${esc(x.type)}">${esc(x.name || x.id)}</span>`).join('') || '<span class="msg">nothing found</span>';
      hits.querySelectorAll('[data-add]').forEach(ch => ch.onclick = async () => {
        if (!await needProject()) return;
        const ids = [...new Set([...pinned, ch.dataset.add])];
        try { await post('/api/quest/pin', {key: q.key, ids}); toast('Added to the cast'); await qbBoard(q); qbCastForm(q, QB.last); $('#qc-q').value = qq; } catch (e){ toast(e.message, true); }
      });
    } catch (e){ hits.innerHTML = `<span class="msg err">${esc(e.message)}</span>`; }
  }, 250); };
  inp.focus();
  $('#qc-no').onclick = () => { box.innerHTML = ''; };
}


// ---------- The table of quests: every quest in the loaded data, sortable, with the Board's flags ----------
const QL = {rows: null, flags: {}, sort: 'plugin', dir: 1, q: '', plugin: '', faulty: false, token: 0};
const QL_COLS = [['id', 'Quest'], ['title', 'Title'], ['plugin', 'Plugin'], ['stages', 'Stages'], ['ends', 'Ends'], ['flags', 'Board']];

async function qlTable(){
  D.mode = 'quests'; D.key = null; D.edit = null;
  const main = $('#dmain');
  main.innerHTML = '<div class="msg" style="padding:30px"><span class="spin"></span>Loading…</div>';
  try { QL.rows = (await api('/api/quest/list')).quests; } catch (e){ main.innerHTML = `<div class="msg err" style="padding:30px">${esc(e.message)}</div>`; return; }
  for (const r of QL.rows) if (r.mine) delete QL.flags[r.key];      // (yours are read afresh: they change)
  dList();
  const plugins = [...new Set(QL.rows.map(r => r.plugin))].sort((a, b) => a.localeCompare(b));
  main.innerHTML = `<div class="dwrap cvwide"><div class="dhead"><div><div class="dt-type">Quests</div><h2>📋 All quests</h2>
      <div class="msg">${fmtN(QL.rows.length)} quests in ${plugins.length} plugin${plugins.length === 1 ? '' : 's'}. Click a column to sort, a quest to open its Board.</div></div>
      <div class="actions" style="margin:0"><button class="btn primary" id="ql-new">+ New quest</button></div></div>
    <div class="qbrow"><input class="inp" id="ql-q" placeholder="Find…" value="${esc(QL.q)}" style="width:180px">
      <select class="inp" id="ql-plugin"><option value="">Every plugin</option>${plugins.map(p => `<option value="${esc(p)}" ${QL.plugin === p ? 'selected' : ''}>${esc(p)}</option>`).join('')}</select>
      <label title="Only quests the Board flags: a stage nothing leads to, or nothing leads on from"><input type="checkbox" id="ql-faulty" ${QL.faulty ? 'checked' : ''}> Faulty only</label>
      <span class="msg" id="ql-n"></span></div>
    <div class="qltab" id="ql-rows"></div></div>`;
  $('#ql-new').onclick = dNewQuest;
  let t; $('#ql-q').oninput = () => { clearTimeout(t); t = setTimeout(() => { QL.q = $('#ql-q').value.trim().toLowerCase(); qlRows(); }, 200); };
  $('#ql-plugin').onchange = () => { QL.plugin = $('#ql-plugin').value; qlRows(); };
  $('#ql-faulty').onchange = () => { QL.faulty = $('#ql-faulty').checked; qlRows(); };
  qlRows();
  qlFill(++QL.token);
}

function qlFaults(f){ return f && !f.error ? f.unset.length + f.dead.length : -1; }
function qlFlagCell(r){
  const f = QL.flags[r.key];
  if (!f) return `<div class="fl wait" data-qf="${esc(r.key)}">…</div>`;
  if (f.error) return `<div class="fl wait" data-qf="${esc(r.key)}" title="${esc(f.error)}">?</div>`;
  const parts = [];
  if (f.unset.length) parts.push(`<span class="fl bad" title="Nothing leads to stage ${f.unset.join(', ')}">⚠ ${f.unset.length}</span>`);
  if (f.dead.length) parts.push(`<span class="fl dead" title="Nothing leads on from stage ${f.dead.join(', ')}">⛔ ${f.dead.length}</span>`);
  return `<div class="fl ${parts.length ? '' : 'ok'}" data-qf="${esc(r.key)}" title="${f.moves} move${f.moves === 1 ? '' : 's'}, ${f.cast} in the cast">${parts.join(' ') || '✓'}</div>`;
}
function qlShown(){
  let rows = QL.rows;
  if (QL.q) rows = rows.filter(r => r.key.includes(QL.q) || r.title.toLowerCase().includes(QL.q));
  if (QL.plugin) rows = rows.filter(r => r.plugin === QL.plugin);
  if (QL.faulty) rows = rows.filter(r => qlFaults(QL.flags[r.key]) > 0);
  const k = QL.sort, d = QL.dir;
  const val = r => k === 'ends' ? r.finished.length : k === 'flags' ? (QL.flags[r.key] ? qlFaults(QL.flags[r.key]) : -2) : k === 'stages' ? r.stages : (r[k] || '').toLowerCase();
  rows = rows.slice().sort((a, b) => { const x = val(a), y = val(b); return (x < y ? -1 : x > y ? 1 : 0) * d || a.key.localeCompare(b.key); });
  return rows;
}
function qlRows(){
  const box = $('#ql-rows'); if (!box) return;
  const rows = qlShown();
  box.innerHTML = `<div class="trow thead">${QL_COLS.map(([c, t]) => `<div class="sortable ${c === 'stages' || c === 'ends' ? 'num' : ''}" data-sort="${c}">${t}${QL.sort === c ? (QL.dir > 0 ? ' ▲' : ' ▼') : ''}</div>`).join('')}</div>`
    + rows.map(r => `<div class="trow" data-qlk="${esc(r.key)}"><div class="id" title="${esc(r.id)}">${r.mine ? '<b class="mine">✎</b> ' : ''}${esc(r.id)}</div><div class="ttl" title="${esc(r.title)}">${esc(r.title)}</div>
      <div title="${esc(r.plugin)}">${esc(r.plugin)}</div><div class="num">${r.stages}</div><div class="num" title="${r.finished.length ? 'Finished at stage ' + r.finished.join(', ') : 'No finishing stage'}">${r.finished.length || '–'}</div>${qlFlagCell(r)}</div>`).join('')
    || `<div class="msg" style="padding:14px">${QL.faulty && Object.keys(QL.flags).length < QL.rows.length ? 'Nothing flagged yet; the check is still running.' : 'Nothing matches.'}</div>`;
  box.querySelectorAll('[data-sort]').forEach(h => h.onclick = () => { const c = h.dataset.sort; if (QL.sort === c) QL.dir = -QL.dir; else { QL.sort = c; QL.dir = 1; } qlRows(); });
  box.querySelectorAll('[data-qlk]').forEach(r => r.onclick = () => { CV.qtab = 'board'; dOpen('quest', r.dataset.qlk); });
  qlCount(rows.length);
}
function qlCount(shown){
  const n = $('#ql-n'); if (!n) return;
  const done = QL.rows.filter(r => QL.flags[r.key]).length;
  n.textContent = (shown !== undefined && shown !== QL.rows.length ? fmtN(shown) + ' shown · ' : '') + (done < QL.rows.length ? `checking ${fmtN(done)} of ${fmtN(QL.rows.length)}…` : 'all checked');
}
async function qlFill(token){
  // the Board's flags, filled in behind the table in the order shown, 20 quests a request
  while (token === QL.token && D.mode === 'quests'){
    const todo = qlShown().filter(r => !QL.flags[r.key]).slice(0, 20);
    const batch = todo.length ? todo : QL.rows.filter(r => !QL.flags[r.key]).slice(0, 20);
    if (!batch.length) break;
    let got;
    try { got = (await api('/api/quest/flags?keys=' + encodeURIComponent(batch.map(r => r.key).join('|')))).flags; }
    catch (e){ break; }
    if (token !== QL.token) break;
    for (const r of batch) QL.flags[r.key] = got[r.key] || {error: 'not read'};
    const box = $('#ql-rows'); if (!box) break;
    for (const r of batch){ const c = box.querySelector(`[data-qf="${CSS.escape(r.key)}"]`); if (c) c.outerHTML = qlFlagCell(r); }
    if (QL.faulty || QL.sort === 'flags') qlRows(); else qlCount();
  }
}
