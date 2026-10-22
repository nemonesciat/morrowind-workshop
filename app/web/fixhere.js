// Fix here: right-click a building piece or an open tile edge in the 3D view or on the map, and the Workshop
// reads the situation at that joint and offers what the game stands there, most often first (the joint
// survey, app/joints.py). Each entry shows a see-through preview in the 3D view while the mouse is over
// it; one click lays it as one change (one Undo); "Fix every spot like this one" lays it wherever the
// place has the same situation.
const FH = {open: null};

async function fixhereMenu(cell, ref, pt, at){
  let r;
  const wait = pnlMenu(pt, [{label: '🧱 Reading what the game stands here…', disabled: true}]);
  try { r = await post('/api/fixhere/options', ref ? {cell, ref} : {cell, at}); }
  catch (e){ wait.remove(); return toast(e.message, true); }
  wait.remove();
  const items = [], sides = {N: 'north', E: 'east', S: 'south', W: 'west'};
  // (a side where the game's answers are all what stands there already says nothing: left out, unless it is the only one)
  let spots = (r.spots || []).filter(sp => sp.options.length);
  if (spots.some(sp => sp.options.some(o => !o.current && o.possible))) spots = spots.filter(sp => sp.options.some(o => !o.current && o.possible));
  if (!spots.length){ items.push({label: r.note || 'The game shows no joint like this one.', disabled: true}); }
  const many = spots.length > 1;
  for (const sp of spots){
    const now = sp.now_label ? ` · now: ${sp.now_label}` : '';
    items.push({label: `${many ? sides[sp.side] + ' side: ' : ''}${sp.situation.split(';')[0]} (${sp.n} in the game)${many ? '' : now}`, disabled: true, head: true});
    for (const o of sp.options.slice(0, many ? 3 : 4)){
      if (o.current){ items.push({label: `● ${o.label} — as it is (${Math.round(100 * o.share)}%)`, disabled: true}); continue; }
      if (!o.possible){ items.push({label: `${o.label} (${Math.round(100 * o.share)}%) — no piece of the style fits it here`, disabled: true}); continue; }
      items.push({label: `${o.label} (${Math.round(100 * o.share)}% of ${sp.n})`, ghost: o.ghost,
        act: () => fixhereApply(cell, {ops: o.ops, label: 'Fixed a joint the game\'s way: ' + o.label})});
      if (sp.key) items.push({label: `   ⟲ …and every spot like this one`, ghost: o.ghost,
        act: () => fixhereApply(cell, {everywhere: true, key: sp.key, ans: o.ans, label: 'Fixed every joint like this one the game\'s way: ' + o.label})});
    }
  }
  if (r.note && spots.length) items.push('-', {label: r.note, disabled: true});
  const m = pnlMenu(pt, items);
  FH.open = m;
  m.querySelectorAll('button').forEach((b, n) => {
    const it = items.filter(x => x !== '-')[n];
    if (!it) return;
    if (it.head) b.className = 'phd';
    if (it.ghost && typeof v3GhostAt === 'function' && V3.on){
      b.onmouseenter = () => v3GhostAt(it.ghost);
      b.onmouseleave = () => v3GhostClear();
    }
  });
  // the preview goes when the menu does (a click elsewhere, Escape)
  const tick = setInterval(() => { if (!m.isConnected){ clearInterval(tick); if (typeof v3GhostClear === 'function') v3GhostClear(); } }, 250);
}

async function fixhereApply(cell, body){
  if (!await needProject()) return;
  if (typeof v3GhostClear === 'function') v3GhostClear();
  try {
    const m = await post('/api/fixhere/apply', Object.assign({cell}, body));
    if (body.everywhere) toast(m.spots ? `Fixed ${m.spots} spot${m.spots === 1 ? '' : 's'} the game's way. One Undo takes it back.` : 'Every spot like this one is the game\'s way already.');
    else toast('Laid the game\'s way. Undo takes it back.');
    if (typeof worldReloadCell === 'function') await worldReloadCell(cell);
    if (typeof afterChange === 'function') afterChange();
    if (typeof v3Refresh === 'function' && V3.on) v3Refresh();
    if (typeof FX !== 'undefined' && FX.panel && FX.cell === cell && typeof fixitOpen === 'function') fixitOpen(cell);
  } catch (e){ toast(e.message, true); }
}
