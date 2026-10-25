// The object window: double-click something on the map (or "Open its window" on its right-click menu) and
// a window opens over the view, the way the Construction Set's does, with the record on one side (ID,
// name, model, script and the type's own fields, as the Browse page edits them) and the placed object on
// the other (where it stands, its turn and size, who owns it, its lock, key and trap, and for a door
// where it leads and where you arrive). Save keeps all of it as one Undo step, Cancel drops the edits,
// Esc closes it. It can follow the selection, and remembers where you left it for the session.
const OW = {el: null, cell: null, k: null, ref: null, cellObj: null, rec: null, props: null, propsOrig: '', door: null,
            follow: true, pos: null, busy: false, picking: false, drag: null, shown: {}};
try { OW.pos = JSON.parse(sessionStorage.getItem('ws-objwin-pos') || 'null'); } catch (e){}
try { OW.follow = sessionStorage.getItem('ws-objwin-follow') !== '0'; } catch (e){}

function owCss(){
  if ($('#ow-css')) return;
  const c = document.createElement('style'); c.id = 'ow-css';
  c.textContent = `
  .owin{position:absolute;z-index:41;width:min(740px,calc(100% - 24px));max-height:calc(100% - 24px);display:flex;flex-direction:column;background:var(--panel);border:1px solid var(--line2);border-radius:10px;box-shadow:0 14px 44px #000b;overflow:hidden;font-size:13px}
  .owhead{display:flex;align-items:center;gap:10px;padding:7px 8px 7px 12px;background:var(--bg3-b);border-bottom:1px solid var(--line);cursor:grab;user-select:none;flex:none}
  .owhead:active{cursor:grabbing}
  .owhead .owtitle{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:600}
  .owhead .owtitle small{color:var(--faint);font-weight:400;margin-left:6px}
  .owhead label{font-size:12px;color:var(--muted);display:flex;gap:5px;align-items:center;cursor:pointer;white-space:nowrap}
  .owbody{display:grid;grid-template-columns:1fr 1fr;overflow:auto;min-height:0}
  .owin.narrow .owbody{grid-template-columns:1fr}
  .owcol{padding:10px 14px 12px;min-width:0}
  .owcol + .owcol{border-left:1px solid var(--line)}
  .owin.narrow .owcol + .owcol{border-left:0;border-top:1px solid var(--line)}
  .owcol h3{margin:4px 0 8px;font-size:12px;color:var(--gold2);letter-spacing:.06em;text-transform:uppercase}
  .owcol h4{margin:10px 0 5px;font-size:12.5px;color:var(--muted);font-weight:600}
  .owf{display:grid;grid-template-columns:minmax(76px,32%) minmax(0,1fr);gap:5px 10px;align-items:center;margin-bottom:4px}
  .owf > label{color:var(--muted);font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .owf .ro{font-size:12.5px;word-break:break-word;color:var(--text-d)}
  .owin .inp{padding:4px 7px;font-size:12.5px}
  .owin textarea.inp{min-height:64px}
  .owin .xyz label,.owin .two label{font-size:11.5px;color:var(--faint)}
  .owin .xyz,.owin .two{margin-bottom:6px}
  .owin .cfield{margin-bottom:7px}
  .owin .statgrid{font-size:12px}
  .owin details{margin:6px 0}.owin summary{cursor:pointer;color:var(--muted);font-size:12.5px}
  .owfoot{display:flex;gap:6px;align-items:center;padding:8px 12px;border-top:1px solid var(--line);flex:none;background:var(--bg2-b)}
  .owfoot .msg{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .owfoot .msg.dirty{color:var(--gold2)}
  .owin .ddlist{z-index:12}
  .owin .flag,.owin .mine-tag{margin-right:4px}`;
  document.head.appendChild(c);
}

const owDeg = v => ((v * 180 / Math.PI) % 360 + 360) % 360;
const owRef = () => (OW.cell && findRef(OW.cell, OW.k)) || OW.ref;
const owName = () => { const r = owRef(); return r ? (r.name || r.id) : ''; };

// ---------------------------------------------------------------- open, close, where it sits
async function owOpen(cell, k, quiet){
  if (!cfWorldOn()) showView('world');
  const r = findRef(cell, k);
  if (!r){ if (!quiet) toast('That object isn\'t here any more.', true); return; }
  owCss();
  if (OW.el && OW.el.isConnected && OW.cell === cell && OW.k === k){ OW.el.style.display = ''; return; }
  if (OW.el && owDirty() && !confirm('Drop the unsaved edits in the object window?')) return;
  OW.cell = cell; OW.k = k; OW.ref = r; OW.cellObj = W.cells[cell];
  OW.rec = null; OW.props = null; OW.propsOrig = ''; OW.door = null; OW.picking = false;
  owMake();
  OW.el.style.display = '';
  owPlace();
  owDrawLoading();
  await owLoad();
}
function owClose(){
  if (!OW.el) return;
  if (OW.picking) owPickCancel();
  OW.el.remove(); OW.el = null; OW.cell = OW.k = null; OW.rec = OW.props = OW.door = OW.cont = null;
}
function owMake(){
  if (OW.el && OW.el.isConnected) return;
  const el = document.createElement('div'); el.className = 'owin'; el.id = 'objwin';
  el.innerHTML = `<div class="owhead" id="ow-head"><span class="owtitle" id="ow-title"></span>
      <label title="When ticked, the window moves on to whatever you select next"><input type="checkbox" id="ow-follow" ${OW.follow ? 'checked' : ''}> Follow selection</label>
      <button class="btn sm" id="ow-close" title="Close (Esc)">✕</button></div>
    <div class="owbody"><div class="owcol" id="ow-rec"></div><div class="owcol" id="ow-ref"></div></div>
    <div class="owfoot"><span class="msg" id="ow-msg"></span><button class="btn sm primary" id="ow-save" title="Keep the record and the placed object's changes, as one Undo step">Save</button><button class="btn sm" id="ow-cancel" title="Drop the edits and close">Cancel</button></div>`;
  $('#world .mapwrap').appendChild(el);
  OW.el = el;
  el.querySelector('#ow-close').onclick = () => owClose();
  el.querySelector('#ow-cancel').onclick = () => owClose();
  el.querySelector('#ow-save').onclick = () => owSave();
  el.querySelector('#ow-follow').onchange = e => { OW.follow = e.target.checked; try { sessionStorage.setItem('ws-objwin-follow', OW.follow ? '1' : '0'); } catch (x){} };
  el.addEventListener('input', () => owMsg());
  el.addEventListener('change', () => owMsg());
  el.addEventListener('click', e => {
    const a = e.target.closest('[data-ow]'); if (a) owAction(a.dataset.ow);
    const c = e.target.closest('[data-owcopy]'); if (c){ navigator.clipboard?.writeText(c.dataset.owcopy); c.textContent = 'copied'; setTimeout(() => c.textContent = 'copy', 1200); }
  });
  // dragging by the title bar
  const head = el.querySelector('#ow-head');
  head.addEventListener('pointerdown', e => {
    if (e.button !== 0 || e.target.closest('button, input, label')) return;
    const r = el.getBoundingClientRect();
    OW.drag = {dx: e.clientX - r.left, dy: e.clientY - r.top};
    head.setPointerCapture(e.pointerId);
  });
  head.addEventListener('pointermove', e => {
    if (!OW.drag) return;
    const box = $('#world .mapwrap').getBoundingClientRect();
    OW.pos = {x: e.clientX - box.left - OW.drag.dx, y: e.clientY - box.top - OW.drag.dy};
    owPlace();
  });
  head.addEventListener('pointerup', () => { if (OW.drag){ OW.drag = null; try { sessionStorage.setItem('ws-objwin-pos', JSON.stringify(OW.pos)); } catch (e){} } });
}
// where it sits: where it was left, kept inside the view (near the top right the first time)
function owPlace(){
  const el = OW.el, box = $('#world .mapwrap'); if (!el || !box) return;
  const bw = box.clientWidth, bh = box.clientHeight;
  el.classList.toggle('narrow', bw < 760);
  const w = el.offsetWidth, h = el.offsetHeight;
  let x = OW.pos ? OW.pos.x : bw - w - 16, y = OW.pos ? OW.pos.y : 52;
  x = Math.max(0, Math.min(bw - w, x)); y = Math.max(0, Math.min(Math.max(0, bh - h), y));
  el.style.left = x + 'px'; el.style.top = y + 'px';
}

// ---------------------------------------------------------------- the data
function owDrawLoading(){
  const r = owRef();
  $('#ow-title').innerHTML = `${esc(r.name || r.id)}<small>${esc(S.typeLabels[r.type] || r.type)}</small>`;
  $('#ow-rec').innerHTML = '<div class="msg"><span class="spin"></span>Loading…</div>';
  $('#ow-ref').innerHTML = '';
  owMsg();
}
async function owLoad(){
  const cell = OW.cell, k = OW.k, r = owRef();
  const jobs = [r.ri != null ? api('/api/record?i=' + r.ri).catch(e => ({error: e.message})) : Promise.resolve(null)];
  jobs.push(r.type === 'NPC_' || r.type === 'CREA' ? Promise.resolve(null) : api('/api/ref/props?' + new URLSearchParams({cell, ref: k})).catch(e => ({error: e.message})));
  const [rec, props] = await Promise.all(jobs);
  if (!OW.el || OW.cell !== cell || OW.k !== k) return;
  OW.rec = rec; OW.props = props && !props.error ? props : null; OW.propsErr = props && props.error;
  OW.propsOrig = OW.props ? JSON.stringify(owPropsData()) : '';
  OW.door = r.type === 'DOOR' ? {target: undefined, label: '', at: null, changed: false} : null;
  OW.cont = null;
  if (r.type === 'CONT' && rec && rec.fields){
    const items = rec.fields.filter(f => f.label === 'Carries').map(f => ({id: f.value, name: '', count: Math.abs(f.count) || 1, restock: f.count < 0}));
    OW.cont = {items, orig: JSON.stringify(items)};
  }
  OW.cellObj = W.cells[cell];
  OW.shown = {p: r.p.slice(), s: r.s};       // (what the boxes show: edits are judged against it, not the live spot)
  owDraw();
}

// the record side: the Browse page's own field definitions (fieldInput / collectEdits), in a tighter grid
function owRecHtml(){
  const r = owRef(), d = OW.rec;
  let h = `<h3>Record</h3><div class="selcard">${thumbImg(r.id, r.type, 120)}<div style="min-width:0">
      <div style="font-weight:600">${esc(r.name || r.id)}</div>
      <div class="msg" style="word-break:break-all">${esc(r.id)} <button class="copy" data-owcopy="${esc(r.id)}">copy</button></div>
      <div class="msg">${esc(S.typeLabels[r.type] || 'unknown type')} · ${r.mine ? '<span class="mine">your mod</span>' : 'from ' + esc(r.src || '')}</div></div></div>`;
  if (!d) return h + '<div class="msg">No record for this object in your load order.</div>';
  if (d.error) return h + `<div class="msg err">${esc(d.error)}</div>`;
  const flags = [];
  if (d.persistent) flags.push('<span class="flag p">Persistent</span>');
  if (d.blocked) flags.push('<span class="flag p">Blocked</span>');
  if (d.deleted) flags.push('<span class="flag">Deleted by this plugin</span>');
  if (d.mine) flags.push(`<span class="mine-tag">✎ ${d.created ? 'Created' : 'Changed'} in your mod</span>`);
  if (flags.length) h += `<div class="flags" style="margin-bottom:8px">${flags.join('')}</div>`;
  const E = d.winner && d.can_edit;
  if (!d.winner) h += `<div class="msg" style="margin-bottom:8px">Another file changes this record after ${esc(d.plugin)}; the Browse page opens the one the game uses.</div>`;
  const fi = f => d.fields.indexOf(f);
  const stats = d.fields.filter(f => f.kind === 'stat'), skills = d.fields.filter(f => f.kind === 'skill');
  const big = d.fields.filter(f => ['text', 'html', 'code'].includes(f.kind));
  const plain = d.fields.filter(f => !['stat', 'skill', 'text', 'html', 'code'].includes(f.kind) && f.label !== 'Carries');
  const carries = d.fields.filter(f => f.label === 'Carries');
  // (the fields the CS puts at the top of its dialog first: name, model, script)
  const first = ['Name', 'Model', 'Script'], rank = f => { const n = first.indexOf(f.label); return n < 0 ? 9 : n; };
  plain.sort((a, b) => rank(a) - rank(b));
  const ro = f => f.kind === 'path' ? `<span class="path ro">${esc(f.value)}</span>` : `<span class="ro">${esc(f.value) || '<span style="color:var(--faint)">(empty)</span>'}</span>`;
  h += '<div class="owf">' + plain.map(f => `<label title="${esc(f.label)}">${esc(f.label)}</label>` +
      (E && f.edit ? (f.label === 'Script' ? `<div class="dd">${fieldInput(f, fi(f))}<div class="ddlist" id="ow-script-l"></div></div>` : fieldInput(f, fi(f))) : ro(f))).join('') + '</div>';
  for (const f of big) h += `<h4>${esc(f.label)}</h4>` + (E && f.edit ? fieldInput(f, fi(f)) : `<div class="ro" style="white-space:pre-wrap;max-height:120px;overflow:auto">${esc(f.value)}</div>`);
  const statCell = f => `<div><span>${esc(f.label)}</span>${E && f.edit ? `<input class="inp" data-fi="${fi(f)}" value="${esc(f.value)}">` : `<span>${esc(f.value)}</span>`}</div>`;
  if (stats.length) h += `<details><summary>Attributes</summary><div class="statgrid">${stats.map(statCell).join('')}</div></details>`;
  if (skills.length) h += `<details><summary>Skills</summary><div class="statgrid">${skills.map(statCell).join('')}</div></details>`;
  if (OW.cont) h += '<div id="ow-cont"></div>';
  else if (carries.length) h += `<details><summary>Carries ${carries.length} kinds of thing</summary><div class="msg">${carries.map(f => `${Math.abs(f.count)} × ${esc(f.value)}`).join('<br>')}</div></details>`;
  h += `<div class="msg" style="margin-top:8px;font-size:11.5px">Every placed ${esc(r.name || r.id)} shares this record. <span class="lnk" data-ow="browse">Open it on the Browse page</span>${r.type === 'NPC_' || r.type === 'CREA' ? ` · <span class="lnk" data-ow="char">${r.type === 'CREA' ? 'Creature editor' : 'Character editor'}</span>` : ''}</div>`;
  return h + owActHtml();
}
// what can be done with this kind of thing, as it can elsewhere in the Workshop (the editors open as
// windows over the view: viewwin.js)
const OW_ITEMS = ['WEAP', 'ARMO', 'CLOT', 'ALCH', 'INGR', 'MISC', 'LIGH', 'LOCK', 'PROB', 'REPA', 'APPA', 'BOOK'];
function owActHtml(){
  const r = owRef(), t = r.type, out = [];
  const b = (a, label, title) => `<button class="btn sm" data-ow="${a}" title="${esc(title || '')}">${label}</button>`;
  if (t === 'NPC_' || t === 'CREA') out.push(b('dlg', '💬 Dialogue', 'Their greetings, topics and lines, in a window'), b('inv', '🎒 Inventory & spells', 'What they carry, sell and know'),
    b('ai', '🧭 AI & behaviour', 'Where they wander, who they follow, how they fight and greet'), b('char', t === 'CREA' ? '🐾 Creature editor' : '👤 Character editor', 'Everything about them: looks, stats, services, travel'),
    b('setup', '🧪 Test setup…', 'What you start with when you Play here: items, spells, quest stages'));
  if (OW_ITEMS.includes(t)) out.push(b('itemed', ['WEAP', 'ARMO', 'CLOT', 'BOOK'].includes(t) ? '✨ Stats & enchantment…' : t === 'ALCH' || t === 'INGR' ? '✨ Stats & effects…' : '✎ Item editor…', 'The item editor in a window: stats, looks, script, effects and enchantment'));
  if (t === 'DOOR' && r.to) out.push(b('goto', '→ Go there', 'Open the place it leads to'));
  if (t === 'LEVC' || t === 'LEVI') out.push(b('lev', '🎲 Edit the list…', 'The leveled list editor, in a window'));
  if (r.ri != null && t === 'NPC_' && typeof anShow === 'function') out.push(b('anim', '🎞 Animation & text keys…', 'How they move: the game\'s animation for their skeleton, played on their body, and its text keys'));
  if (r.ri != null && !['NPC_', 'LEVC', 'LEVI'].includes(t)) out.push(b('assets', '🧩 Model & textures…', 'What it is drawn with: the model, its textures and what else uses them; change a texture in your picture editor'));
  if (['STAT', 'ACTI', 'CONT', 'MISC', 'DOOR', 'LIGH', 'WEAP', 'ARMO', 'CLOT'].includes(t)) out.push(b('retex', '🎨 Retexture…', 'This model with other textures, as a new record'));
  if (r.arch) out.push(b('variants', '↻ Other pieces that fit', 'Pieces the game uses in the same spot'));
  if (r.ri != null) out.push(b('dupnew', '⧉ Make this one a record of its own…', 'Copy the record under a new ID and make this placed one the copy, so it can be changed without changing the others'));
  out.push(b('uses', '🔎 Every placement', 'Where it is placed, who carries it, which scripts and lines name it'), b('brush', '🖌 Add to brush', 'Paint it about with a brush'));
  return `<h4>Do with it</h4><div class="actions" style="margin-top:0;flex-wrap:wrap;gap:5px">${out.join('')}</div>`;
}
// a container's contents: kept in the window until Save
function owContDraw(){
  const box = $('#ow-cont'), K = OW.cont; if (!box || !K) return;
  const E = OW.rec && OW.rec.winner && OW.rec.can_edit;
  box.innerHTML = `<h4>🧰 Contents <span class="msg">(${K.items.length} kind${K.items.length === 1 ? '' : 's'})</span></h4>` +
    (K.items.map((it, n) => `<div style="display:flex;gap:6px;align-items:center;margin-bottom:3px"><input class="inp num" type="number" min="1" style="width:70px" data-owcn="${n}" value="${it.count}" ${E ? '' : 'disabled'}>
      <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(it.id)}">${esc(it.name || it.id)}${it.name ? ` <small style="color:var(--faint)">${esc(it.id)}</small>` : ''}</span>
      ${it.restock ? '<small class="msg" title="Comes back after it is taken (merchants\' chests)">restocks</small>' : ''}${E ? `<button class="btn sm" data-owcrm="${n}" title="Take it out">✕</button>` : ''}</div>`).join('') || '<div class="msg">Empty.</div>') +
    (E ? `<div class="dd" style="margin-top:5px"><input class="inp" id="ow-cadd" placeholder="Add… (e.g. gold, moon sugar, iron dagger, random_loot)" autocomplete="off"><div class="ddlist" id="ow-cadd-l"></div></div>` : '');
  if (!E) return;
  ddSearch('ow-cadd', 'MISC,WEAP,ARMO,CLOT,BOOK,ALCH,INGR,APPA,LOCK,PROB,REPA,LIGH,LEVI', x => {
    const i = K.items.find(y => y.id.toLowerCase() === x.id.toLowerCase());
    if (i) i.count += 1; else K.items.push({id: x.id, name: x.name || '', count: x.id.toLowerCase().startsWith('gold') ? 50 : 1});
    owContDraw(); owMsg(); setTimeout(() => { const f = $('#ow-cadd'); if (f) f.focus(); }, 0);
  });
  box.oninput = e => { const n = e.target.dataset.owcn; if (n != null){ K.items[+n].count = Math.max(1, +e.target.value || 1); owMsg(); } };
  box.onclick = e => { const x = e.target.closest('[data-owcrm]'); if (x){ K.items.splice(+x.dataset.owcrm, 1); owContDraw(); owMsg(); } };
}

// the placed object's side: the Selected panel's spot, turn and scale; Ownership & lock's fields; a door's link
function owRefHtml(){
  const r = owRef(), d = OW.props;
  const p = r.p;
  let h = `<h3>Placed object</h3>
    <div class="xyz"><div><label>X</label><input class="inp" id="ow-x" value="${p[0].toFixed(1)}"></div><div><label>Y</label><input class="inp" id="ow-y" value="${p[1].toFixed(1)}"></div><div><label>Height</label><input class="inp" id="ow-z" value="${p[2].toFixed(1)}"></div></div>
    <div class="xyz"><div><label>Turn X (degrees)</label><input class="inp" id="ow-rx" value="${owDeg(p[3]).toFixed(1)}"></div><div><label>Turn Y</label><input class="inp" id="ow-ry" value="${owDeg(p[4]).toFixed(1)}"></div><div><label>Turn Z (facing)</label><input class="inp" id="ow-rz" value="${owDeg(p[5]).toFixed(1)}"></div></div>
    <div class="two"><div><label>Scale</label><input class="inp" id="ow-s" value="${r.s}"></div><div><label>In</label><div class="ro" style="padding-top:4px">${esc(W.cells[OW.cell] ? (W.cells[OW.cell].name || W.cells[OW.cell].region || OW.cell) : OW.cell)}</div></div></div>`;
  if (d){
    const pick = (f, ph) => `<div class="dd"><input class="inp" id="ow-${f}" value="${esc(d[f] || '')}" placeholder="${ph}" autocomplete="off"><div class="ddlist" id="ow-${f}-l"></div></div>${d[f + '_missing'] ? `<small class="err">"${esc(d[f])}" doesn't exist</small>` : d[f + '_name'] && d[f + '_name'].toLowerCase() !== (d[f] || '').toLowerCase() ? `<small style="color:var(--faint)">${esc(d[f + '_name'])}</small>` : ''}`;
    if (d.can_own){
      h += `<h4>🔒 Ownership</h4><label class="cfield"><span>Belongs to</span>${pick('owner', 'a person… (search); empty: no one')}</label>
        <div class="crow"><label class="cfield" style="flex:2"><span>or to the faction</span>${pick('faction', 'a faction… (search)')}</label>
          ${d.faction ? `<label class="cfield" style="flex:1"><span>free from rank</span><select class="inp" id="ow-rank">${(d.ranks && d.ranks.length ? d.ranks : ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']).map((x, n) => `<option value="${n}" ${n === (d.rank || 0) ? 'selected' : ''}>${esc(x)}</option>`).join('')}</select></label>` : ''}</div>
        <label class="cfield"><span>Owner set by a global variable</span>${pick('global', 'a global variable… (search); usually empty')}</label>`;
    }
    if (d.can_lock){
      h += `<h4>Lock</h4><div class="crow"><label class="cfield" style="flex:1"><span>Lock level</span><input class="inp num" type="number" id="ow-lock" min="0" max="1000" value="${d.lock || 0}"><small>0: unlocked; over 100 only the key opens it.</small></label>
          <label class="cfield" style="flex:2"><span>Key</span>${pick('key', 'a key… (search)')}</label></div>
        <label class="cfield"><span>Trap</span>${pick('trap', 'a spell… (search); empty: no trap')}</label>`;
    }
    if (d.uses_label) h += `<label class="cfield"><span>${esc(d.uses_label)}</span><input class="inp num" type="number" id="ow-uses" min="0" value="${d.uses == null ? '' : d.uses}" placeholder="as new"></label>`;
    if (d.can_soul) h += `<label class="cfield"><span>Soul inside</span>${pick('soul', 'a creature… (search); for soul gems')}</label>`;
  } else if (OW.propsErr) h += `<div class="msg err">${esc(OW.propsErr)}</div>`;
  if (r.type === 'DOOR'){
    const D = OW.door || {}, to = r.to;
    const target = D.target === undefined ? (to ? to.key : null) : D.target;
    const label = D.target === undefined ? (to ? (to.cell || to.label || '') : '') : D.label;
    const at = D.at || (to ? [to.x, to.y, to.z, to.rz] : null);
    h += `<h4>🚪 Leads to</h4>
      <div class="dd"><input class="inp" id="ow-dest" value="${esc(label)}" placeholder="Nowhere: an ordinary door (search a place to make it lead there)" autocomplete="off"><div class="ddlist" id="ow-dest-l"></div></div>
      ${target ? `<div class="msg" style="margin-top:6px">You arrive at ${at ? `${Math.round(at[0])}, ${Math.round(at[1])}${at[2] == null ? '' : ', ' + Math.round(at[2])}, facing ${Math.round(owDeg(at[3] || 0))}°` : 'a spot chosen for you'}${D.changed ? ' <span class="mine">(changed)</span>' : ''}</div>
        <div class="actions" style="margin-top:6px"><button class="btn sm" data-ow="arrive" title="Open the place it leads to and click exactly where the player should arrive">📍 Pick on the map…</button><button class="btn sm" data-ow="unlink">Remove the link</button></div>
        <label class="msg" style="display:flex;gap:6px;align-items:center;margin-top:6px"><input type="checkbox" id="ow-both" ${W.relinkBoth !== false ? 'checked' : ''}> Make the door at the other end lead back here</label>` : '<div class="msg" style="margin-top:6px">Nowhere: an ordinary door that just opens and closes.</div>'}`;
  }
  return h;
}

function owDraw(){
  if (!OW.el) return;
  const r = owRef(); if (!r){ owClose(); return; }
  $('#ow-title').innerHTML = `${esc(r.name || r.id)}<small>${esc(S.typeLabels[r.type] || r.type)}</small>`;
  const rec = $('#ow-rec');
  rec.innerHTML = owRecHtml();
  if (typeof v3ThumbScan === 'function') v3ThumbScan(rec);
  // the script box searches scripts
  if (OW.rec && OW.rec.fields){
    const sf = OW.rec.fields.findIndex(f => f.label === 'Script' && f.edit);
    const inp = sf >= 0 && rec.querySelector(`[data-fi="${sf}"]`);
    if (inp && $('#ow-script-l')){ inp.id = 'ow-script'; ddSearch('ow-script', 'SCPT', x => { inp.value = x.id; owMsg(); }); }
  }
  owContDraw();
  owDrawRef(false);
}
// the placed-object side (on its own after an ownership pick or a door change, keeping what's typed in
// the spot boxes, so neither side's edits are lost)
function owDrawRef(keepTyped){
  const r = owRef(); if (!r) return;
  const keep = {}; if (keepTyped !== false) for (const id of ['ow-x', 'ow-y', 'ow-z', 'ow-rx', 'ow-ry', 'ow-rz', 'ow-s']){ const e = $('#' + id); if (e) keep[id] = e.value; }
  $('#ow-ref').innerHTML = owRefHtml();
  for (const [id, v] of Object.entries(keep)){ const e = $('#' + id); if (e) e.value = v; }
  const d = OW.props;
  if (d){
    const bind = (f, types) => {
      const inp = $('#ow-' + f); if (!inp) return;
      ddSearch('ow-' + f, types, x => { d[f] = x.id; d[f + '_name'] = x.name || ''; d[f + '_missing'] = false; if (f === 'faction') d.owner = ''; owDrawRef(); });
      inp.addEventListener('change', () => { d[f] = inp.value.trim(); d[f + '_missing'] = false; d[f + '_name'] = ''; if (f === 'faction' && !d[f]) d.rank = 0; owDrawRef(); });
    };
    bind('owner', 'NPC_'); bind('faction', 'FACT'); bind('global', 'GLOB'); bind('key', 'MISC'); bind('trap', 'SPEL'); bind('soul', 'CREA');
    const rk = $('#ow-rank'); if (rk) rk.onchange = () => { d.rank = +rk.value; };
    const lk = $('#ow-lock'); if (lk) lk.onchange = () => { d.lock = Math.max(0, +lk.value || 0); };
    const us = $('#ow-uses'); if (us) us.onchange = () => { d.uses = us.value === '' ? null : Math.max(0, +us.value || 0); };
  }
  if (r.type === 'DOOR'){
    ddSearch('ow-dest', 'CELL', async x => {
      try {
        const m = await api('/api/cellmap?i=' + x.i); OW.door = {target: m.key, label: x.name || x.id, at: null, changed: true}; owDrawRef();
        if (m.key === OW.cell) toast('Within this same place: pick where you arrive with 📍 Pick on the map…');
      }
      catch (e){ toast(e.message, true); }
    });
    const both = $('#ow-both'); if (both) both.onchange = () => { W.relinkBoth = both.checked; };
  }
  owMsg();
  owPlace();
}

// ---------------------------------------------------------------- what changed
function owPropsData(){
  const d = OW.props; if (!d) return null;
  return {owner: d.owner || '', faction: d.faction || '', rank: d.rank || 0, global: d.global || '', soul: d.soul || '', lock: d.lock || 0, key: d.key || '', trap: d.trap || '', uses: d.uses == null ? null : d.uses};
}
function owSpot(){
  const r = owRef(), num = id => parseFloat(($('#' + id) || {}).value);
  const p = r.p.slice(); p[0] = num('ow-x'); p[1] = num('ow-y'); p[2] = num('ow-z');
  p[3] = num('ow-rx') * Math.PI / 180; p[4] = num('ow-ry') * Math.PI / 180; p[5] = num('ow-rz') * Math.PI / 180;
  const s = num('ow-s');
  const bad = [p[0], p[1], p[2], p[3], p[4], p[5], s].some(isNaN);
  const was = OW.shown || {p: r.p, s: r.s};
  // (the boxes show one decimal: a box left as it was shown is no move)
  const moved = !bad && (p.slice(0, 3).some((v, n) => Math.abs(v - +was.p[n].toFixed(1)) > 1e-6) || p.slice(3).some((v, n) => Math.abs(owDeg(v) - +owDeg(was.p[n + 3]).toFixed(1)) > 1e-4) || Math.abs(s - was.s) > 1e-6);
  return {p, s, bad, moved};
}
function owChanges(){
  if (!OW.el) return null;
  const out = {rec: [], spot: null, props: false, door: false};
  if (OW.rec && OW.rec.winner && OW.rec.can_edit && OW.rec.fields) out.rec = collectEdits(OW.rec, OW.el);
  const sp = $('#ow-x') ? owSpot() : null;
  if (sp && sp.moved) out.spot = sp;
  out.bad = sp && sp.bad;
  out.props = !!OW.props && JSON.stringify(owPropsData()) !== OW.propsOrig;
  out.door = !!(OW.door && OW.door.changed);
  out.cont = !!(OW.cont && JSON.stringify(OW.cont.items.map(x => ({id: x.id, name: '', count: x.count, restock: x.restock}))) !== OW.cont.orig);
  out.any = out.rec.length > 0 || !!out.spot || out.props || out.door || out.cont;
  return out;
}
function owDirty(){ const c = owChanges(); return !!(c && c.any); }
function owMsg(){
  const m = $('#ow-msg'); if (!m || OW.busy) return;
  const c = owChanges(); if (!c) return;
  const parts = [];
  if (c.rec.length) parts.push(c.rec.length === 1 ? 'the record' : `the record (${c.rec.length} fields)`);
  if (c.spot) parts.push('the spot');
  if (c.props) parts.push('ownership');
  if (c.door) parts.push('where it leads');
  if (c.cont) parts.push('the contents');
  m.className = 'msg' + (parts.length ? ' dirty' : '');
  m.textContent = c.bad ? 'Numbers only in the spot boxes.' : parts.length ? 'Changed: ' + parts.join(', ') + ' · Save keeps it all as one Undo step' : 'Nothing changed yet.';
}

// ---------------------------------------------------------------- actions
async function owAction(a){
  const r = owRef(); if (!r) return;
  if (a === 'browse'){ if (r.ri != null){ showView('browse'); openRecord(r.ri, true); } return; }
  // (the editors come up as windows over the view: viewwin.js)
  const inWin = (v, fn) => typeof vwRun === 'function' ? vwRun(v, fn) : fn();
  if (a === 'char' || a === 'inv' || a === 'ai'){
    if (typeof cOpen !== 'function') return;
    if (a !== 'char') C.tab = a === 'inv' ? 'items' : 'ai';
    return inWin('chars', () => cOpen(r.id, a !== 'char'));
  }
  if (a === 'dlg') return inWin('dialog', () => openCharacterDialogue(r.id));
  if (a === 'itemed') return inWin('itemed', () => ieShow(r.id));
  if (a === 'lev') return inWin('lists', () => lvOpen(r.id));
  if (a === 'setup') return qolSetups();
  if (a === 'uses') return qolUses(r.id);
  if (a === 'brush') return brAddTo(r.id, r.name).catch(e => toast(e.message, true));
  if (a === 'goto') return qolThrough(OW.cell, r);
  if (a === 'retex' || a === 'variants'){
    if (!(W.sel && W.sel.cell === OW.cell && W.sel.k === OW.k)) selectRef(OW.cell, OW.k, true);
    return selAction(a);
  }
  if (a === 'dupnew') return owOwnRecord();
  if (a === 'assets') return asShow(r.ri, (r.name || r.id) + ': model & textures');
  if (a === 'anim') return anShow(r.ri, (r.name || r.id) + ': animation & text keys');
  if (a === 'unlink'){ OW.door = {target: null, label: '', at: null, changed: true}; owDrawRef(); return; }
  if (a === 'arrive'){
    const target = OW.door && OW.door.target !== undefined ? OW.door.target : (r.to && r.to.key);
    if (!target) return toast('Make the door lead somewhere first.', true);
    OW.picking = {cell: OW.cell, k: OW.k, target, opening: true};
    W.arriving = {cell: OW.cell, ref: OW.k, target, name: r.name || r.id};
    OW.el.style.display = 'none';
    try { await worldOpen(target); } finally { OW.picking.opening = false; }
    if (OW.picking) setMode('arrive');
  }
}
// a record of its own for this placed one (the Construction Set's "new ID, create a new object?"): the
// record copied under a new ID and this one swapped for the copy, one Undo step; the others keep the original
async function owOwnRecord(){
  const r = owRef(); if (!r || !OW.rec || OW.rec.error || OW.rec.i == null) return;
  if (owDirty()) return toast('Save or Cancel the edits in the window first.', true);
  if (!await needProject()) return;
  let sug = '';
  try { sug = (await api('/api/create/suggest_id?name=' + encodeURIComponent(r.name || r.id))).id; } catch (e){}
  const id = ((await askText(`A record of its own for this ${r.name || r.id}: every other one placed keeps the record it has now, and this one becomes a copy you can change on its own.\n\nThe copy's ID:`, sug || r.id + '_2')) || '').trim();
  if (!id) return;
  const cell = OW.cell, k = OW.k;
  try { await post('/api/duplicate', {i: OW.rec.i, id}); }
  catch (e){ return toast(e.message, true); }
  try {
    await post('/api/ref/swap', {cell, ref: k, id});
    try { await post('/api/fold', {n: 2, note: `Made this ${r.name || r.id} a record of its own (${id})`}); } catch (e){}
  } catch (e){ toast('Made the copy ' + id + ', but could not swap this one for it: ' + e.message, true); }
  try { if (W.cells[cell] && W.cells[cell].exists) await worldReloadCell(cell); await afterChange(); if (typeof V3 !== 'undefined' && V3.on) v3Refresh(); } catch (e){}
  toast(`This ${r.name || r.id} is now ${id}, a record of its own. One Undo takes it back.`);
  if (OW.el && OW.cell === cell && OW.k === k){ OW.ref = findRef(cell, k) || OW.ref; OW.cellObj = W.cells[cell]; await owLoad(); }
}
// the arrival spot picked on the map comes back to the window instead of being saved at once
async function owArrived(x, y, z, rz){
  const P = OW.picking; OW.picking = false; W.arriving = null;
  setMode(null);
  if (!OW.el) return;
  OW.door = Object.assign(OW.door || {target: undefined, label: ''}, {at: [x, y, z, rz || 0], changed: true});
  await worldOpen(P.cell);
  selectRef(P.cell, P.k, true);
  OW.el.style.display = ''; owDrawRef();
}
async function owPickCancel(){
  const P = OW.picking; OW.picking = false; W.arriving = null;
  if (W.mode === 'arrive') setMode(null);
  if (!OW.el) return;
  if (W.key !== P.cell) await worldOpen(P.cell);
  selectRef(P.cell, P.k, true);
  OW.el.style.display = ''; owDrawRef();
}

async function owSave(){
  if (OW.busy || !OW.el) return;
  if (!await needProject()) return;
  const c = owChanges(), r = owRef(), cell = OW.cell, k = OW.k, name = r.name || r.id;
  if (c.bad) return toast('Please enter numbers only', true);
  if (!c.any) return toast('Nothing changed.');
  if (c.props){ const d = owPropsData(); if (d.faction && d.owner) return toast('Pick either a person or a faction as the owner, not both.', true); }
  OW.busy = true; $('#ow-save').disabled = true; $('#ow-msg').textContent = 'Saving…';
  const depth = async () => { try { const s = await api('/api/status'); return (s.project || {}).undo_depth || 0; } catch (e){ return 0; } };
  const d0 = await depth(), done = [];
  let failed = null;
  try {
    let ri = OW.rec && OW.rec.i;
    if (c.rec.length){ ri = (await post('/api/edit', {i: OW.rec.i, changes: c.rec})).i; done.push('the record'); }
    if (c.cont){ await post('/api/contents', {i: ri, items: OW.cont.items.map(x => ({id: x.id, count: x.count, restock: !!x.restock}))}); done.push('the contents'); }
    if (c.spot){ await post('/api/ref/move', {cell, ref: k, p: c.spot.p, s: c.spot.s}); done.push('the spot'); }
    if (c.props){ await post('/api/ref/props', {cell, ref: k, data: owPropsData()}); done.push('ownership'); }
    if (c.door){ await post('/api/ref/relink', {cell, ref: k, target: OW.door.target, at: OW.door.at, both: W.relinkBoth !== false}); done.push('where it leads'); }
  } catch (e){ failed = e.message; }
  // (each route is one change; together they become one Undo step)
  const n = (await depth()) - d0;
  if (n > 1){ try { await post('/api/fold', {n, note: `Edited ${name} in its window (${done.join(', ')})`}); } catch (e){} }
  try {
    const cells = new Set([cell]);
    if (c.door){ if (OW.door.target) cells.add(OW.door.target); if (r.to) cells.add(r.to.key); }
    for (const ck of cells) if (W.cells[ck] && W.cells[ck].exists) await worldReloadCell(ck);
    await afterChange();
    if (typeof V3 !== 'undefined' && V3.on) v3Refresh();
    if (W.sel && W.sel.cell === cell && W.sel.k === k) renderWside();
  } catch (e){}
  OW.busy = false;
  if (OW.el){ $('#ow-save').disabled = false; }
  if (failed) toast(failed + (done.length ? ` (${done.join(' and ')} saved)` : ''), true);
  else toast(`Saved ${name}: ${done.join(', ')}` + (n > 1 ? ' (one Undo step)' : '') + (LINK.connected ? '. Already live in game.' : '.'));
  if (OW.el && OW.cell === cell && OW.k === k){ OW.ref = findRef(cell, k) || OW.ref; await owLoad(); }
}

// ---------------------------------------------------------------- hooks into the map
// double-click on the flat map, or on a row of an Objects list
cv.addEventListener('dblclick', e => {
  if (!W.key || W.mode) return;
  const hit = hitTest(e.offsetX, e.offsetY);
  if (hit) owOpen(hit[0], hit[1].k);
});
$('#world').addEventListener('dblclick', e => {
  const ok = e.target.closest('[data-ok]'); if (!ok) return;
  const r = findRef(W.key, ok.dataset.ok); if (r) owOpen(W.key, r.k);
});
// Esc: the arrival pick, an open list, then the window itself
document.addEventListener('keydown', e => {
  if (e.key !== 'Escape' || !OW.el) return;
  if (OW.picking){ if (W.mode === 'arrive'){ e.preventDefault(); e.stopPropagation(); owPickCancel(); } return; }
  if (OW.el.style.display === 'none' || document.querySelector('.modal-bg, .pmenu')) return;
  const open = OW.el.querySelector('.ddlist[style*="block"]');
  if (open){ open.style.display = 'none'; e.preventDefault(); e.stopPropagation(); return; }
  e.preventDefault(); e.stopPropagation();
  owClose();
}, true);
// following the selection
(function(){
  const orig = selectRef;
  selectRef = function(ck, k, quiet){
    orig(ck, k, quiet);
    if (!OW.el || OW.picking || OW.busy || !OW.follow) return;
    if (ck === OW.cell && k === OW.k) return;
    if (owDirty()){ const m = $('#ow-msg'); if (m){ m.className = 'msg dirty'; m.textContent = 'Not following the selection: Save or Cancel first.'; } return; }
    owOpen(ck, k, true);
  };
  const origArrive = arriveAt;
  arriveAt = function(x, y, z, rz){ return OW.picking ? owArrived(x, y, z, rz) : origArrive(x, y, z, rz); };
})();
// the place changed under the window (a drag, an Undo, a swap): shown afresh when nothing is being edited
setInterval(() => {
  if (!OW.el || OW.busy) return;
  if (OW.picking){ if (W.mode !== 'arrive' && !OW.picking.opening) owPickCancel(); return; }     // (Esc or another mode: the pick is off)
  if (!cfWorldOn()){ return; }
  const co = W.cells[OW.cell];
  if (co === OW.cellObj) return;
  OW.cellObj = co;
  const r = findRef(OW.cell, OW.k);
  if (!r){ if (!owDirty()) owClose(); return; }     // (gone, or another place opened: the window goes unless it holds edits)
  OW.ref = r;
  if (owDirty()) return;
  owLoad();
}, 400);
window.addEventListener('resize', () => owPlace());
