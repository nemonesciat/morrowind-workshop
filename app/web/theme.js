// How the Workshop looks: a few themes, your own accent and background colours, and calmer
// animations. Kept in this browser (localStorage "ws-theme") and put on before the page shows, so
// there's no flash of the old colours. Settings → Appearance.
const TH_THEMES = {
  ashlands: {label: 'Ashlands', about: 'The usual: dark ash and gold', v: {}},
  telvanni: {label: 'Telvanni', about: 'Mushroom-tower purple', v: {
    bg: '#120f17', panel: '#1a1621', panel2: '#221c2b', line: '#322a3d', line2: '#45395a', text: '#e9e1f2', muted: '#a097b2', faint: '#837999',
    gold: '#b98be0', gold2: '#d9b8ff', hover: '#261f30', sel: '#33264a', deep: '#0d0b11', bg2: '#16121c', bg3: '#1c1724', line0: '#1f1a27', goldline: '#6e4f8f'}},
  redoran: {label: 'Redoran', about: 'Red-brown, like their bug-shell armour', v: {
    bg: '#150f0c', panel: '#1e1511', panel2: '#281c17', line: '#3c2a22', line2: '#523a2f', text: '#efe0d4', muted: '#a99183', faint: '#8b7467',
    gold: '#d9824f', gold2: '#f4ac7c', hover: '#2d1f19', sel: '#40271b', deep: '#100b09', bg2: '#19110e', bg3: '#211713', line0: '#251a15', goldline: '#8d5233'}},
  hlaalu: {label: 'Hlaalu', about: 'Olive and amber, like their halls in Balmora', v: {
    bg: '#11130d', panel: '#191c13', panel2: '#212519', line: '#313724', line2: '#444c31', text: '#e6e8d6', muted: '#9ea38a', faint: '#80876c',
    gold: '#d6b44a', gold2: '#f1d77e', hover: '#23271b', sel: '#333a1f', deep: '#0d0f0a', bg2: '#15180f', bg3: '#1b1f14', line0: '#1f2318', goldline: '#8a7a34'}},
  dagoth: {label: 'Dagoth', about: 'Black and crimson, from under Red Mountain', v: {
    bg: '#140a0c', panel: '#1c0f12', panel2: '#251418', line: '#3a1f25', line2: '#522b33', text: '#f0dfe1', muted: '#ab8e93', faint: '#917579',
    gold: '#d0454f', gold2: '#f07d84', hover: '#2a161a', sel: '#3f1a21', deep: '#0f0709', bg2: '#170c0e', bg3: '#1e1013', line0: '#241216', goldline: '#8a2f37',
    red: '#ff8f6b'}},
  dwemer: {label: 'Dwemer', about: 'Bronze and verdigris', v: {
    bg: '#0e1211', panel: '#151b19', panel2: '#1c2421', line: '#2b3833', line2: '#3c4d46', text: '#e1ebe5', muted: '#93a49b', faint: '#788a80',
    gold: '#c8964a', gold2: '#e8bd78', hover: '#1f2925', sel: '#2e3426', deep: '#0b0e0d', bg2: '#121816', bg3: '#18201d', line0: '#1b2420', goldline: '#7d6033'}},
  imperial: {label: 'Imperial', about: 'Light, like a page of the Pocket Guide', light: true, v: {
    bg: '#efe6d2', panel: '#f8f2e4', panel2: '#ebe1ca', line: '#d8c9a9', line2: '#c2ae88', text: '#2a2318', muted: '#66573d', faint: '#6f6147',
    gold: '#93631a', gold2: '#7a4c08', hover: '#e8dcc0', sel: '#e6d1a0', deep: '#fffaf0', bg2: '#ebe0c8', bg3: '#f1e8d4', line0: '#e3d7bd', goldline: '#b08a4c',
    red: '#b3432b', amber: '#9c6a0c', blue: '#2e5d97', green: '#4b7833'}},
  indoril: {label: 'Indoril', about: 'Light and cool: pale Mournhold stone and deep blue', light: true, v: {
    bg: '#e3e8ee', panel: '#f1f4f8', panel2: '#e4e9f0', line: '#c9d2dd', line2: '#a9b6c5', text: '#1b2430', muted: '#4b596a', faint: '#5a6879',
    gold: '#2d5d8c', gold2: '#1d4670', hover: '#dbe2ea', sel: '#cbdaea', deep: '#fbfcfe', bg2: '#dce3ea', bg3: '#e8edf2', line0: '#d5dce5', goldline: '#7f9dbd',
    red: '#ae3a2e', amber: '#8f6610', blue: '#2d5d8c', green: '#3c7647'}},
  contrast: {label: 'High contrast', about: 'Black, white and bright yellow: easiest to read', v: {
    bg: '#000000', panel: '#0a0a0a', panel2: '#161616', line: '#5c5c5c', line2: '#8c8c8c', text: '#ffffff', muted: '#e2e2e2', faint: '#bdbdbd',
    gold: '#ffd23f', gold2: '#ffe680', hover: '#232323', sel: '#3d3400', deep: '#000000', bg2: '#0a0a0a', bg3: '#111111', line0: '#333333', goldline: '#b39400'}},
};

function thGet(){ try { return Object.assign({theme: 'ashlands', accent: '', bg: '', calm: false}, JSON.parse(localStorage.getItem('ws-theme') || '{}')); } catch (e){ return {theme: 'ashlands', accent: '', bg: '', calm: false}; } }
function thSave(t){ try { localStorage.setItem('ws-theme', JSON.stringify(t)); } catch (e){} }

// a colour's brightness (0 dark, 1 light)
function thLum(hex){ const n = parseInt(hex.slice(1), 16); return (0.299 * (n >> 16 & 255) + 0.587 * (n >> 8 & 255) + 0.114 * (n & 255)) / 255; }

function thApply(t){
  t = t || thGet();
  const root = document.documentElement, base = TH_THEMES[t.theme] || TH_THEMES.ashlands;
  const names = ['bg', 'panel', 'panel2', 'line', 'line2', 'text', 'muted', 'faint', 'gold', 'gold2', 'hover', 'sel', 'deep', 'bg2', 'bg3', 'line0', 'goldline', 'red', 'amber', 'blue', 'green'];
  for (const k of names.concat(['text-b', 'text-c', 'text-d', 'muted-b', 'muted-c', 'muted-d', 'deep-b', 'deep-c', 'deep-d', 'bg2-b', 'bg3-b',
    'panel2-b', 'panel2-c', 'panel2-d', 'goldline-b', 'sel-b', 'btn-primary', 'btn-primary-hover', 'tag-mine', 'tag-flag', 'tag-flag-p', 'toast-err', 'hl'])) root.style.removeProperty('--' + k);
  const v = Object.assign({}, base.v);
  let light = !!base.light;
  // your own background: the panels, lines and text are worked out from it
  if (/^#[0-9a-f]{6}$/i.test(t.bg || '')){
    const B = t.bg; light = thLum(B) > 0.55;
    const T = light ? '#000000' : '#ffffff', mix = (p, c) => `color-mix(in srgb, ${B}, ${c || T} ${p}%)`;
    Object.assign(v, {bg: B, panel: mix(4), panel2: mix(8), line: mix(16), line2: mix(24), hover: mix(10), line0: mix(7), bg2: mix(2), bg3: mix(5),
      deep: mix(30, light ? '#ffffff' : '#000000'), text: mix(88), muted: mix(58), faint: mix(40), sel: mix(14)});
  }
  // your own accent (what's gold in the usual look)
  if (/^#[0-9a-f]{6}$/i.test(t.accent || '')){
    const A = t.accent;
    Object.assign(v, {gold: A, gold2: `color-mix(in srgb, ${A}, ${light ? '#000000' : '#ffffff'} 30%)`, goldline: `color-mix(in srgb, ${A}, ${v.bg || '#13110d'} 40%)`});
  }
  // the close shades and the button and tag colours follow the main ones; the usual look keeps its own exactly
  const fam = {text: ['text-b', 'text-c', 'text-d'], muted: ['muted-b', 'muted-c', 'muted-d'], deep: ['deep-b', 'deep-c', 'deep-d'],
               bg2: ['bg2-b'], bg3: ['bg3-b'], panel2: ['panel2-b', 'panel2-c', 'panel2-d'], goldline: ['goldline-b'], sel: ['sel-b']};
  for (const [k, kids] of Object.entries(fam)) if (v[k]) for (const c of kids) v[c] = `var(--${k})`;
  // (on a light background a paler tint, so the dark accent text on it stays easy to read)
  const tint = light ? [13, 20, 12, 12] : [30, 40, 20, 18];
  if (Object.keys(v).length) Object.assign(v, {
    'btn-primary': `color-mix(in srgb,var(--gold) ${tint[0]}%,var(--panel))`, 'btn-primary-hover': `color-mix(in srgb,var(--gold) ${tint[1]}%,var(--panel))`,
    'tag-mine': `color-mix(in srgb,var(--gold) ${tint[2]}%,var(--panel))`, 'tag-flag': `color-mix(in srgb,var(--red) ${tint[3]}%,var(--panel))`,
    'tag-flag-p': `color-mix(in srgb,var(--blue) ${tint[3]}%,var(--panel))`, 'toast-err': 'var(--red)',
    hl: `color-mix(in srgb,var(--gold) ${light ? 18 : 30}%,var(--panel))`});
  for (const [k, val] of Object.entries(v)) root.style.setProperty('--' + k, val);
  root.dataset.theme = light ? 'light' : 'dark';
  root.classList.toggle('th-calm', !!t.calm);
  let st = document.getElementById('th-css');
  if (!st){ st = document.createElement('style'); st.id = 'th-css'; document.head.appendChild(st); }
  st.textContent = `
    .th-calm *,.th-calm *::before,.th-calm *::after{transition:none!important;animation:none!important}
    html[data-theme=light] header{background:var(--bg2)!important}
    html[data-theme=light] .modal-bg{background:color-mix(in srgb,var(--text) 40%,transparent)}
    html[data-theme=light] ::-webkit-scrollbar-thumb{background-color:var(--line2)}
    html[data-theme=light] .pfloat .pgroup,html[data-theme=light] .pmenu,html[data-theme=light] .modal{box-shadow:0 10px 32px color-mix(in srgb,var(--text) 22%,transparent)}`;
}
thApply();

// ---------------------------------------------------------------- Settings → Appearance
function thSection(){
  const t = thGet();
  let in3d = false; try { in3d = localStorage.getItem('ws-3d') === '1'; } catch (e){}
  return `<section class="card setsec"><h3>Appearance</h3>
    <div class="th-grid">${Object.entries(TH_THEMES).map(([k, T]) => {
      const c = Object.assign({bg: '#13110d', panel: '#1b1813', line2: '#463c2e', text: '#ebe2cf', gold: '#d2a85a', muted: '#9c917c'}, T.v);
      return `<button class="th-card ${t.theme === k && !t.bg ? 'on' : ''}" data-th="${k}" style="background:${c.bg};border-color:${t.theme === k ? c.gold : c.line2}">
        <span style="background:${c.panel};border-color:${c.line2}"><i style="background:${c.gold}"></i><i style="background:${c.muted}"></i><i style="background:${c.text}"></i></span>
        <b style="color:${c.text}">${esc(T.label)}</b><small style="color:${c.muted}">${esc(T.about)}</small></button>`; }).join('')}</div>
    <div class="setrow" style="margin-top:12px"><span>Your own accent colour</span><span><input type="color" id="th-accent" value="${t.accent || '#d2a85a'}"> <button class="btn sm" id="th-accent-x" ${t.accent ? '' : 'disabled'}>Theme's own</button></span></div>
    <div class="setrow"><span>Your own background colour</span><span><input type="color" id="th-bg" value="${t.bg || '#13110d'}"> <button class="btn sm" id="th-bg-x" ${t.bg ? '' : 'disabled'}>Theme's own</button></span></div>
    <div class="msg" style="font-size:12px">The panels, lines and text are worked out from the background, so any colour stays readable.</div>
    <label style="display:flex;gap:8px;align-items:center;margin-top:10px"><input type="checkbox" id="th-calm" ${t.calm ? 'checked' : ''}> Calmer: no fades or movement in menus and windows</label>
    <div class="msg" style="font-size:12px;margin-top:8px">Bigger or smaller: hold Ctrl and turn the mouse wheel (Ctrl+0 for the usual size).</div></section>

  <section class="card setsec"><h3>Working</h3>
    <div class="setrow"><span>The World map opens in</span><span><select id="th-3d" style="width:auto;margin:0"><option value="0" ${in3d ? '' : 'selected'}>the flat map</option><option value="1" ${in3d ? 'selected' : ''}>3D</option></select></span></div>
    <div class="setrow"><span>Keyboard shortcuts</span><span><button class="btn sm" id="th-keys">Change them… (Ctrl+/)</button></span></div>
    <div class="setrow"><span>Panels on every page</span><span><button class="btn sm" id="th-panels">Back to the starting layouts</button></span></div>
    <div class="setrow"><span>Who Play here starts as</span><span><button class="btn sm" id="th-playas">👤 ${esc((typeof QOL !== 'undefined' && QOL.playAs) || 'A new character')}…</button></span></div></section>`;
}
function thBind(w){
  thCss();
  const t = thGet(), upd = ch => { Object.assign(t, ch); thSave(t); thApply(t); renderSettings(); };
  w.querySelectorAll('[data-th]').forEach(b => b.onclick = () => upd({theme: b.dataset.th, bg: '', accent: ''}));
  const ac = w.querySelector('#th-accent'), bgc = w.querySelector('#th-bg');
  ac.oninput = () => { t.accent = ac.value; thSave(t); thApply(t); };
  ac.onchange = () => upd({accent: ac.value});
  bgc.oninput = () => { t.bg = bgc.value; thSave(t); thApply(t); };
  bgc.onchange = () => upd({bg: bgc.value});
  w.querySelector('#th-accent-x').onclick = () => upd({accent: ''});
  w.querySelector('#th-bg-x').onclick = () => upd({bg: ''});
  w.querySelector('#th-calm').onchange = e => upd({calm: e.target.checked});
  w.querySelector('#th-3d').onchange = e => { try { localStorage.setItem('ws-3d', e.target.value); } catch (x){} toast(e.target.value === '1' ? 'The World map opens in 3D from now on.' : 'The World map opens flat from now on.'); };
  w.querySelector('#th-keys').onclick = () => cfKeysModal();
  w.querySelector('#th-playas').onclick = () => qsPlayAs();
  w.querySelector('#th-panels').onclick = () => {
    if (!confirm('Put the panels on every page back where they started? (Your saved layouts stay in the Panels menu.)')) return;
    for (const [name, sp] of Object.entries(PNL.spaces)) PNL.useLayout(name, sp.opts.presets[sp.opts.start]);
    try { for (const k of Object.keys(localStorage)) if (k.startsWith('ws-panels-') && !Object.keys(PNL.spaces).includes(k.slice(10))) localStorage.removeItem(k); } catch (e){}
    toast('Panels are back where they started.');
  };
}
function thCss(){
  if (document.getElementById('th-css2')) return;
  const c = document.createElement('style'); c.id = 'th-css2';
  c.textContent = `
  .th-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
  .th-card{display:flex;flex-direction:column;gap:3px;text-align:left;border:2px solid;border-radius:10px;padding:10px;cursor:pointer;font:inherit}
  .th-card.on{box-shadow:0 0 0 2px var(--gold)}
  .th-card span{display:flex;gap:4px;border:1px solid;border-radius:6px;padding:6px;margin-bottom:4px}
  .th-card i{display:block;width:18px;height:10px;border-radius:3px}
  .th-card b{font-size:13px}.th-card small{font-size:11px;line-height:1.35}
  input[type=color]{width:44px;height:28px;padding:0;border:1px solid var(--line2);border-radius:6px;background:none;cursor:pointer;vertical-align:middle}`;
  document.head.appendChild(c);
}
